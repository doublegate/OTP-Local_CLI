# Windows DPAPI and Cross-Platform Shell Specification

Status: Planned for release v1.2.0.
Extends [Architecture](02-architecture.md), [CLI Specification](03-cli-specification.md), and [Desktop Integration](13-desktop-integration.md).

## 1. Overview and Requirements

To achieve complete cross-platform parity across Linux, macOS, and Microsoft Windows, OTP-Local CLI implements native Windows credential management using the Windows Data Protection API (DPAPI) and Windows Credential Manager.

Key requirements:

1. Native DPAPI encryption: Protect credentials at rest without requiring external gpg or pass packages on Windows.
2. Windows Hello integration: Bind decryption authorization to Windows Hello PIN or biometric factors.
3. Windows shells: Native PowerShell (`Microsoft.PowerShell`) profile module and NuShell integration.
4. WSL2 Interop: Enable Linux processes running inside WSL2 to access Windows DPAPI credentials over a secure local named pipe.
5. Windows package management: Doctor automated remediation using `winget` and `scoop`.

## 2. Windows DPAPI Architecture

### 2.1 CryptProtectData and CryptUnprotectData

Windows DPAPI provides user-context encryption derived from the Windows login credentials:

- C function: `CryptProtectData` in `Crypt32.dll`.
- Parameters:
  - `pDataIn`: Raw secret bytes (UTF-16LE or UTF-8).
  - `szDataDescr`: Optional descriptive label (e.g. `"OTP-Local Token: <Service> (<Account>)"`).
  - `pOptionalEntropy`: 32-byte application-specific salt derived from host machine GUID and user security identifier (SID).
  - `dwFlags`: `CRYPTPROTECT_UI_FORBIDDEN` (or `CRYPTPROTECT_LOCAL_MACHINE` if host-scoped).
- Storage: Encrypted ciphertext blobs stored inside Windows Credential Manager or local encrypted JSON under `%LOCALAPPDATA%\OTP-Local\credentials.dpapi`.

### 2.2 Windows Credential Manager

Interfacing directly with `advapi32.dll`:

- Target name format: `OTP-Local:<Service>:<Account>`.
- Type: `CRED_TYPE_GENERIC`.
- Persistence: `CRED_PERSIST_LOCAL_MACHINE` or `CRED_PERSIST_ENTERPRISE`.

## 3. Windows Shell Ecosystem

### 3.1 PowerShell Integration (`shell/otp-local.ps1`)

The PowerShell script exposes:

- Tab completion for enrolled services and accounts.
- Pipeline support: `otp-local show github | Set-Clipboard`.
- Aliases: `otp`, `totp`.

### 3.2 NuShell Integration (`shell/otp-local.nu`)

Structured data output:

- Returns table records: `[{service: "github", account: "alice", code: "123456", remaining_seconds: 24}]`.
- Direct integration with NuShell completions.

### 3.3 WSL2 Inter-Process Communication Bridge

WSL2 virtual machines communicate with the Windows host via UNIX-to-named-pipe bridges:

- Windows Host runs a background named pipe server: `\\.\pipe\otp-local-bridge-$USER`.
- WSL2 guest connects using a UNIX socket mapped via `socat` or `/mnt/c/` binary invoker.
- Caller identity verification: The bridge asserts that the Windows user SID matches the WSL2 active user context.

## 4. Security Boundaries and Audit

1. DPAPI blobs are non-exportable and inaccessible to other user accounts on the same machine.
2. Memory zeroing: Decrypted bytearrays in Python are cleared immediately with `ctypes.memset`.
3. Doctor diagnostics: `otp-local doctor` checks for DPAPI availability, Windows Credential Manager accessibility, and PowerShell execution policies.
