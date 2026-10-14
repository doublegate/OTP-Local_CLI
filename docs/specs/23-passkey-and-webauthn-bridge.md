# 23. Specification: Passkey and WebAuthn Assertion Bridge (v3.0.0)

## 1. Overview

This specification establishes the software FIDO2 / WebAuthn passkey authenticator and local assertion bridge, elevating OTP-Local CLI to a sovereign identity orchestrator. The engine implements CTAP2.1 authenticator operations (`authenticatorMakeCredential` and `authenticatorGetAssertion`) with resident key storage, paired with an assertion forwarding proxy for browser WebAuthn challenges.

## 2. Passkey Authenticator Architecture

### 2.1 Cryptographic Algorithms

The passkey engine supports modern public-key signature algorithms:

- Ed25519 (COSE algorithm -8).
- ES256: ECDSA over NIST P-256 with SHA-256 (COSE algorithm -7).
- RS256: RSASSA-PKCS1-v1_5 with SHA-256 (COSE algorithm -257).

### 2.2 Resident Credential Storage

- Discoverable credentials (resident keys) stored locally in encrypted storage.
- Private keys encrypted with AES-256-GCM using hardware-backed keys (Apple Secure Enclave, Windows DPAPI, TPM2, or master passphrase).
- User presence verification via platform biometrics or hardware security key touch.

## 3. WebAuthn Assertion Bridge

### 3.1 IPC Bridge Protocol

- Transports: Local UNIX domain socket (`/run/user/$UID/webauthn-bridge.sock`) or named pipe.
- Challenge forwarding: Intercepts WebAuthn assertion requests from browser extensions or CLI clients (`ssh`, `gh`, `aws-vault`).
- Authenticator Data: Constructs valid W3C WebAuthn `authenticatorData` flags (User Present `UP=1`, User Verified `UV=1`).

### 3.2 CLI and API Contracts

- `otp-local passkey create <relying-party-id> --user <username>`: Generates and enrolls a new resident passkey.
- `otp-local passkey list`: Enumerates stored passkeys with relying party identifiers.
- `otp-local passkey assert <relying-party-id>`: Computes and returns signed authentication assertion.

## 4. Security Boundaries and Invariants

- Private signature keys never leave the host machine; private keys are never transmitted over network protocols.
- Assertion signing requires explicit user confirmation and biometric presence check.
- Cryptographic memory pinning and zeroization enforced for all private key operations.
