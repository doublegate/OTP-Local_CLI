# FIDO2 CTAP2.1 Hardware Engine Specification

Status: Planned for release v1.3.0.
Extends [Architecture](02-architecture.md), [Security and Data](04-security-and-data.md), and [Optional Backends](08-optional-backends.md).

## 1. Overview and Requirements

Hardware tokens (YubiKey 5 Series, SoloKey, Nitrokey, Google Titan) provide physical isolation for cryptographic credentials. This specification details the integration of physical FIDO2 / WebAuthn authenticators using the CTAP 2.1 protocol.

Key requirements:

1. Seedless storage: Plaintext TOTP seeds are never persisted to disk.
2. Hardware HMAC-secret: The authenticator derives a 256-bit symmetric key upon physical user touch presence and PIN entry.
3. Multi-token redundancy: Support primary and backup security keys with synchronized salt configurations.
4. TUI touch notification: Visual pulsing touch prompt in the Textual TUI during CTAP2 assertions.

## 2. Cryptographic Protocol: CTAP 2.1 HMAC-Secret Extension

### 2.1 Credential Creation (`hmacCreateSecret`)

During enrollment:

1. The client sends `authenticatorMakeCredential` requesting the `hmac-secret` extension (`{"hmacCreateSecret": true}`).
2. The authenticator generates a resident or discoverable credential keypair and initializes a hardware-bound symmetric secret tied to the credential ID.
3. The credential ID and public key are saved in the local metadata ledger.

### 2.2 Assertion and Key Derivation (`HMACGetSecretInput`)

When generating a TOTP code:

1. Client generates a deterministic salt:
   `Salt = HMAC-SHA-256("OTP-Local-Salt-v1", service_name + ":" + account_name)`
2. Client sends `authenticatorGetAssertion` with `HMACGetSecretInput` containing `Salt`.
3. Authenticator prompts for User Presence (UP - touch gesture) and User Verification (UV - PIN or biometric).
4. Authenticator computes `HMAC-SHA-256(HardwareSecret, Salt)` and returns the encrypted result to the client.
5. Client uses the hardware output as a key-derivation key (KDK) to decrypt the encrypted TOTP seed stored in the local vault.
6. The derived seed is loaded into a protected bytearray, the RFC 6238 TOTP code is computed, and the bytearray is immediately wiped with `ctypes.memset`.

### 2.3 WebAuthn PRF Compatibility

For platforms utilizing system WebAuthn APIs (such as Windows 10/11 or macOS Safari/Chrome WebAuthn shims), the implementation maps HMAC-secret calls to the W3C WebAuthn PRF (Pseudo-Random Function) extension:
`Salt_PRF = SHA256(b"WebAuthn PRF\x00" + Salt)`

## 3. Textual TUI Integration: Touch Notification

During assertion, the Textual TUI launches a modal dialog:

- Widget: `Fido2TouchModal`.
- Visual state: Pulsing amber badge with `"Touch Authenticator..."`.
- Timeout: 30-second countdown bar.
- On touch success: Dialog automatically dismisses, code is copied or displayed.
- On disconnect or timeout: Informative error toast displayed without application crash.

## 4. Security Invariants

1. Physical touch presence (UP) is mandatory for every decryption operation.
2. Even in the event of full filesystem compromise, stored encrypted seeds cannot be decrypted without the physical hardware token.
3. PIN caching: PIN is cached in memory for a maximum of 30 seconds, guarded by `mlock()`, and wiped upon timer expiration.
