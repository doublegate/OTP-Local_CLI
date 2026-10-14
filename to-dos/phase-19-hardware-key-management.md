# Phase 19: Advanced Hardware Security Key Management (v2.7.0)

Status: Planned; milestone for release v2.7.0. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Elevate physical hardware security key capabilities by implementing full credential lifecycle management across YubiKey OATH slots (`ykman`), configurable touch policies (`ALWAYS`, `CACHED`), hardware PIN and lockout mitigation, SoloKeys and Nitrokey firmware support, and an in-process virtual CTAP2 authenticator loopback for automated CI testing.

## Entry Conditions and Dependencies

- Phase 18 completed and verified.
- FIDO2 CTAP2 foundation in `src/authy_local/backends/fido2.py` operational.

## Sprint Sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-19.1](sprints/19.1.md) | Hardware key credential lifecycle and touch-policy enforcement | Entry gate |
| [S-AUTH-19.2](sprints/19.2.md) | Multi-vendor key support and virtual CTAP2 test loopback | S-AUTH-19.1 |

All tasks in each sprint must have automated synthetic test verification before closing.

## Deliverables and Evidence

- Hardware key manager in `src/authy_local/hardware_keys.py` managing YubiKey OATH application slots, touch policies, credential deletion, and PIN verification.
- Multi-vendor support supporting SoloKeys (Somu/Solo2) and Nitrokey 3 over CTAP2.1.
- In-process virtual CTAP2 authenticator in `src/authy_local/testing/virtual_authenticator.py` enabling complete hardware key simulation in CI without physical USB devices.
- CLI commands `otp-local key list`, `otp-local key enroll`, `otp-local key reset-pin`, `otp-local key touch-policy`.
- Comprehensive automated test suite in `tests/test_hardware_keys.py`.
- Operational guide in `docs/operations/hardware-keys.md`.

## Exit Criteria

- Full OATH credential lifecycle (add, calculate, touch, delete) passing against both physical YubiKeys and virtual test authenticators.
- Virtual authenticator integrated into CI pipeline ensuring zero skipped hardware tests on Linux/macOS runners.
- Touch timeout handling tested with visual countdown prompts in both CLI and TUI.
