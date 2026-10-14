# 20. Specification: Freedesktop Secret Service and Platform Biometrics

## 1. Overview

This specification establishes native Linux desktop integration via the D-Bus Freedesktop Secret Service specification (`org.freedesktop.secrets`) and multi-platform hardware biometric gating (Apple Touch ID, Windows Hello, Linux `fprintd` / PAM).

## 2. D-Bus Secret Service Architecture

### 2.1 Interface Contracts

The daemon implements three primary D-Bus interfaces under object path `/org/freedesktop/secrets`:

- `org.freedesktop.Secret.Service`: Top-level collection enumeration, session negotiation, and search.
- `org.freedesktop.Secret.Collection`: Default collection containing OTP items with unlock protection.
- `org.freedesktop.Secret.Item`: Secret container holding token attributes and value.

### 2.2 Cryptographic Session Negotiation

Clients negotiate an encryption session prior to secret retrieval:

- `plain`: Unencrypted session over local UNIX socket (trusted local transport).
- `dh-ietf1024-sha256-aes128-cbc-pkcs7`: Ephemeral Diffie-Hellman key exchange deriving a shared secret for AES-128-CBC encryption.

## 3. Platform Biometrics

### 3.1 macOS Touch ID

- Framework: `LocalAuthentication.framework` via PyObjC.
- Policy: `LAPolicyDeviceOwnerAuthenticationWithBiometrics`.
- Fallback: Local device passcode if biometrics fail or are unconfigured.

### 3.2 Windows Hello

- API: `Windows.Security.Credentials.UI.UserConsentVerifier`.
- Verification Level: Verifies presence via fingerprint, facial recognition, or PIN challenge.

### 3.3 Linux Biometrics

- D-Bus Service: `net.reactivated.Fprint.Device`.
- Interaction: Prompts user to touch enrolled fingerprint sensor, failing closed upon three failed attempts.

## 4. Security Invariants

- Secrets are never transmitted in plaintext across unencrypted sessions.
- Biometric challenges require physical user presence and cannot be satisfied by synthetic software events.
- Failed biometric attempts lock the session for 30 seconds to prevent rapid brute-force attacks.
