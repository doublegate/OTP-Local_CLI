# ADR 0009: Windows DPAPI and Credential Manager Storage Backend

- Status: Proposed for release v1.2.0 (Phase 7)
- Supersedes: None; extends Explicit Local Backends (ADR 0005)

## Context

To achieve complete cross-platform parity across Linux, macOS, and Windows without introducing dependencies on external third-party software, Windows installations require a secure, local-first storage mechanism.

On Linux, GPG (`pass-otp`) and TPM 2.0 (`totpm`) serve as local storage; on macOS, the Keychain (`/usr/bin/security`) and Secure Enclave provide native protection. On Microsoft Windows, the Data Protection API (DPAPI) and Windows Credential Manager provide native, user-bound hardware and OS-level key protection.

## Decision

1. Implement `WindowsDpapiBackend` in `src/authy_local/backends/dpapi.py` utilizing `CryptProtectData` and `CryptUnprotectData` via `ctypes` or `win32crypt`.
2. Apply application-specific entropy derived from machine GUID and user SID to prevent arbitrary same-user process decryption.
3. Integrate Windows Credential Manager (`advapi32.dll`) to store encrypted credential blobs under `OTP-Local:<Service>:<Account>`.
4. Provide PowerShell profile completions (`shell/otp-local.ps1`) and NuShell integration (`shell/otp-local.nu`).
5. Expose a named pipe bridge (`\\.\pipe\otp-local-bridge-$USER`) allowing WSL2 Linux instances to query host DPAPI secrets without transferring master keys into the virtual machine.

## Consequences

- Delivers complete Windows platform parity without requiring GPG or WSL-only setups.
- Keeps Windows credentials isolated to the logged-in user profile or Windows Hello biometrics.
- WSL2 developer environments gain access to host credentials seamlessly over local named pipes.
- Windows doctor module can detect and remediate missing dependencies using `winget` and `scoop`.
