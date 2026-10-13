# OTP Enrollment Specification

Status: Implemented and verified for CLI and Textual TUI dashboard delivery, 2026-10-12.
Extends [Architecture](02-architecture.md), [CLI Specification](03-cli-specification.md), and [Textual TUI](11-tui.md).

## 1. Overview & Requirements

Operators require a direct, interactive method to onboard new two-factor authentication credentials from service setup screens into their designated credential stores:

- **1Password**: Primary local/cloud hybrid vault (`Login` item tagged with `"OTP"`).
- **pass-otp**: Unix password store with GPG encryption.
- **totpm**: Hardware-backed TPM 2.0 encrypted storage.

Enrollment supports two input paths:

1. Alphanumeric secret input: Raw Base32 string or standard `otpauth://totp/` URI.
2. QR code screen capture: Decoded directly from the Wayland clipboard (`wl-paste`) or a local image file.

Prior to committing secrets to disk or remote vaults, operators must be able to visually verify the live derived TOTP code and copy it to their clipboard to complete the service setup challenge.

## 2. Input Ingestion and Normalization

### 2.1 Base32 Secret Cleaning

- All whitespace, tabs, and hyphens (`-`) are stripped.
- Characters are converted to uppercase.
- Secret lengths must satisfy RFC 4648 Base32 constraints (multiples of 8 characters after padding, or unpadded equivalent).
- Padding (`=`) is normalized.

### 2.2 URI Parsing

- Standard RFC 6238 URI format: `otpauth://totp/[issuer:]account?secret=...&issuer=...&period=...&digits=...`
- Protocol validation: Scheme must be `otpauth` and authority must be `totp`.
- Parameter bounds:
  - `digits`: Integer, clamped to [6, 8] (default 6).
  - `period`: Integer, clamped to [10, 120] (default 30).
  - `algorithm`: Supported algorithms include `SHA1`, `SHA256`, `SHA512` (default `SHA1`).

### 2.3 QR Code Decoding

- External decoder: `/usr/bin/zbarimg`.
- Execution contract: Invoked with `-q --raw -` via `subprocess.Popen`.
- Security invariant: Image bytes are streamed directly via standard input. Decoded secrets and raw image data are never written to unencrypted temporary files on disk.

### 2.4 Wayland Native Clipboard Integration

- Image capture: `/usr/bin/wl-paste -t image/png` (fallback: `-t image/jpeg`).
- Text capture: `/usr/bin/wl-paste --no-newline`.
- Environment detection: Validates presence of `WAYLAND_DISPLAY` or `DISPLAY`.

## 3. Interactive TUI Interface (AddOtpModal)

### 3.1 Access and Hotkeys

- Bound to Action 5 on the main dashboard (`DashboardScreen`).
- Trigger hotkeys: `5`, `a`, or `e`.

### 3.2 Modal Controls

- **Entry / Account Label**: User-editable account identifier.
- **Service / Issuer Label**: User-editable service identifier.
- **Secret / URI Input**: Alphanumeric text input field supporting either raw Base32 or `otpauth://` URIs.
- **Paste QR from Clipboard**: Triggers Wayland clipboard image capture and `zbarimg` decoding in a worker thread.
- **Load QR Image File**: Prompts for file path and decodes image.
- **Live Preview Display**:
  - Derived 6-digit TOTP code displayed prominently in monospace bold text.
  - Active 30-second `CountdownBar` showing time remaining in current time window.
  - Periodic 1-second update interval.
- **Copy Test Code Button**: Immediately writes the currently displayed 6-digit code to the system clipboard for setup verification.
- **Backend Target Checkboxes**:
  - `1Password` (checked by default).
  - `pass-otp`.
  - `totpm`.
- **Enroll & Save Button**: Commits the secret to all selected backends.
- **Cancel Button**: Dismisses modal without writing.

### 3.3 Label Sanitization

All entry and service labels must conform to the local store naming regex:
`^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$`
Characters outside this set (such as `/` in `issuer:account`) are automatically normalized to underscores or hyphens.

## 4. Backend Persistence Contracts

### 4.1 1Password

- CLI tool: `/usr/bin/op` or native CLI.
- Creation:

  ```bash
  op item create --category Login \
    --title "<Service> (<Account>)" \
    --vault "<Vault>" \
    --tags "OTP,<UserTags>" \
    "one-time password[otp]=<URI>"
  ```

- Update:

  ```bash
  op item edit "<Item-ID>" \
    --tags "OTP,<UserTags>" \
    "one-time password[otp]=<URI>"
  ```

### 4.2 pass-otp

- Ingestion: Invokes `pass otp insert -f <entry>` streaming secret via stdin.

### 4.3 totpm

- Ingestion: Invokes `totpm add --service <service> --account <account>` streaming secret via stdin.

## 5. Security and Memory Hygiene

1. **In-Memory Zeroing**: Sensitive secret strings, URI buffers, and bytearrays are zeroed out via `ctypes.memset` or zero-byte overwrites in `finally` blocks and upon modal `on_unmount`.
2. **Zero Plaintext Disk Writes**: Image bytes and QR secrets flow through process pipes directly into decoder and store subprocesses.
3. **No Secret Leakage**: Exceptions, error toasts, and logs must redact or omit the secret value, reporting only format validity or backend execution status.
