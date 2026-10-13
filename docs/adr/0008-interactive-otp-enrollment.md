# ADR 0008: Interactive OTP Enrollment from Secret Strings and Screen QR Codes

- Status: Accepted by explicit operator request, 2026-10-12
- Supersedes: None; extends Dashboard Interface (ADR 0006) and Explicit Local Backends (ADR 0005)

## Context

Operators need an intuitive, unified workflow at the primary TUI dashboard (Action 5: "Add OTP entry") and command-line interface (`otp-local enroll`) to onboard new two-factor authentication credentials directly into storage backends without manual command assembly or toolchain switching.

Adding an OTP credential requires supporting two primary input ingestion formats:

1. Alphanumeric input: Raw Base32 secret strings or standard `otpauth://totp/...` URIs.
2. Visual QR code input: Captured directly from service setup screens into the Wayland clipboard (`wl-paste`) or selected from local image files.

Furthermore, enrollment carries high operational risk if the generated TOTP code does not match service expectations before the setup session expires. Operators require live visual verification of the derived TOTP code with real-time countdown progress and an immediate "Copy Test Code" action to confirm against the service challenge prompt prior to persistent storage.

Finally, operators must be able to target any or all of the three supported backends in a single transaction:

- 1Password: Created as a `Login` category item tagged with `"OTP"` and user tags, with `"one-time password[otp]=<uri>"`.
- GPG (`pass-otp`): Stored as an encrypted GPG file under the password store hierarchy.
- TPM (`totpm`): Stored securely in the hardware TPM 2.0 encrypted NV storage.

## Decision

1. **Modular Enrollment Engine**: Implement `src/authy_local/enrollment.py` providing pure-Python RFC 6238 TOTP computation matching canonical test vectors, strict Base32 normalization (stripping spaces, hyphens, and enforcing uppercase alphabet), and URI parameter extraction.
2. **Secure QR Ingestion**: Interface directly with `/usr/bin/zbarimg` using standard input streaming (`zbarimg -q --raw -`). Never write clipboard image bytes or decrypted secrets to unencrypted temporary files on disk.
3. **Wayland Native Clipboard**: Interface directly with `/usr/bin/wl-paste` requesting `image/png` (with fallback to `image/jpeg`) for screen snips, and `--no-newline` for text strings.
4. **Interactive Textual Modal**: Implement `AddOtpModal` in `src/authy_local/tui.py` bound to Action 5 (`"Add OTP entry"`, hotkeys `5`, `a`, `e`):
   - Dual-input design: Text field for manual secret/URI entry alongside "Paste QR from Clipboard" and "Load QR Image File" action triggers.
   - Live Reactive Preview: A 1-second reactive tick updates the derived 6-digit TOTP code, accompanied by a dynamic 30-second `CountdownBar`.
   - "Copy Test Code": Copies the currently active test code to the Wayland/X11 clipboard for instant service confirmation.
   - Target Backend Selection: Independent checkboxes for 1Password, pass-otp, and totpm.
   - Strict Input Sanitization: Validate entry and service names against the local label regex `[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z`.
5. **Memory Zeroing**: Provide cryptographic zeroing functions (`ctypes.memset`) to wipe secret byte buffers from memory immediately upon modal unmount or worker exit.
6. **Backend Enrollment Integration**:
   - Extend `OnePasswordBackend.enroll(...)` to create Login items tagged with `"OTP"` using `op item create --category Login` or update existing items using `op item edit`.
   - Integrate existing `PassOtpBackend.enroll(...)` and `TotpmBackend.enroll(...)` with label sanitation.

## Consequences

- Direct enrollment is accessible from both TUI (Action 5) and CLI (`otp-local enroll`).
- Eliminates file leakage risks for QR screenshots by streaming image bytes directly across process pipes.
- Enforces tag parity in 1Password by automatically applying the `"OTP"` tag to newly enrolled items.
- In-memory secret scrubbing minimizes exposure in long-running TUI processes.
- Does not modify existing Authy extraction boundaries; Authy retention policies remain unchanged.
