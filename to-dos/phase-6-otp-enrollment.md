# Phase 6: Interactive OTP Enrollment and Multi-Backend Onboarding

Status: Candidate implemented and verified; documentation and verification complete.
See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Deliver an integrated, operator-centric enrollment workflow enabling direct addition of new two-factor authentication credentials from alphanumeric strings (Base32/URI) or screen-captured QR codes into 1Password (Login category tagged `"OTP"`), pass-otp, and totpm.

## Entry Conditions and Dependencies

- Base CLI and Textual TUI operational (Phase 0–5 completed).
- External tools `/usr/bin/zbarimg` and `/usr/bin/wl-paste` present for QR decoding and Wayland clipboard support.

## Sprint Sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-6.1](sprints/6.1.md) | Enrollment engine, QR decoding, and multi-backend persistence | See sprint entry gate |
| [S-AUTH-6.2](sprints/6.2.md) | Textual TUI AddOtpModal, live TOTP preview, and challenge verification | S-AUTH-6.1 |

All tasks in each sprint must have explicit automated test verification before closing.

## Deliverables and Evidence

- Pure-Python RFC 6238 TOTP computation and Base32 normalizer in `src/authy_local/enrollment.py`.
- Secure stdin streaming interface to `zbarimg` avoiding unencrypted temporary file creation.
- 1Password backend enrollment tagging new items with `"OTP"`.
- Textual TUI Action 5 (`AddOtpModal`) with reactive countdown and clipboard test code copying.
- Unit and adversarial test suites: `tests/test_enrollment.py`, `tests/test_onepassword_enrollment.py`, `tests/test_tui_enrollment.py`.
- Architectural decision record [ADR 0008](../docs/adr/0008-interactive-otp-enrollment.md) and [Specification](../docs/specs/12-otp-enrollment.md).

## Exit Criteria

- 100% test pass rate across all unit, integration, and UI tests.
- Zero plaintext secret leakage in logs, temporary files, or exceptions.
- Cryptographic memory wiping of secret buffers upon modal dismissal.
