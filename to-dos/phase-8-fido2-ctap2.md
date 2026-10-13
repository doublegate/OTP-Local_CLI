# Phase 8: FIDO2 and WebAuthn CTAP2.1 Hardware Engine

Status: Planned for release v1.3.0. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Deliver hardware-enforced zero-trust two-factor authentication by integrating physical FIDO2 / WebAuthn security keys (YubiKey 5 Series, SoloKey, Nitrokey) via the CTAP 2.1 protocol, utilizing the `hmac-secret` and WebAuthn PRF extensions so that TOTP seed material is dynamically decrypted or derived only upon physical user touch presence and PIN assertion, eliminating unencrypted seed persistence on disk.

## Entry Conditions and Dependencies

- Base CLI, Textual TUI, and multi-backend storage operational (Phase 0–7 completed).
- Host USB/NFC HID access configured (e.g. `udev` rules on Linux, WebAuthn API on Windows, Secure Enclave/HID on macOS).
- Python library `python-fido2` (or C library `libfido2`) available for hardware interaction.

## Sprint Sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-8.1](sprints/8.1.md) | FIDO2 CTAP2.1 hardware key core and HMAC-secret derivation | See sprint entry gate |
| [S-AUTH-8.2](sprints/8.2.md) | FIDO2 interactive enrollment, touch presence, and TUI integration | S-AUTH-8.1 |

All tasks in each sprint must have automated synthetic test verification before closing.

## Deliverables and Evidence

- FIDO2 hardware backend module in `src/authy_local/backends/fido2.py` utilizing CTAP 2.1 `hmac-secret` and PRF extension.
- Physical token discovery, device enumeration, and touch presence assertion handler.
- Multi-token pairing and redundant backup token enrollment architecture.
- Textual TUI touch prompt reactive modal and visual pulsing state widget in `src/authy_local/tui.py`.
- Unit and synthetic hardware emulation test suites: `tests/test_fido2_backend.py` and `tests/test_fido2_tui.py`.
- Architectural decision record [ADR 0010](../docs/adr/0010-fido2-ctap2-hardware-tokens.md) and [Specification](../docs/specs/15-fido2-hardware.md).

## Exit Criteria

- 100% test pass rate across synthetic CTAP2 device emulation tests.
- Absolute verification that seeds are never persisted in plaintext without FIDO2 hardware binding.
- Graceful timeout and user-actionable diagnostics when physical tokens are disconnected or touched out of time.
