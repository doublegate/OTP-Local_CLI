# Phase 22: Sovereign Identity and Passkey/WebAuthn Terminal Bridge (v3.0.0 LTS)

Status: Planned; milestone for release v3.0.0 LTS. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Deliver the pinnacle of modern decentralized authentication by promoting OTP-Local CLI to a sovereign identity orchestrator. Phase 22 implements a software FIDO2 / WebAuthn passkey authenticator capable of creating and storing resident credentials, paired with a local IPC assertion bridge allowing terminal and browser clients to resolve WebAuthn authentication challenges with zero cloud dependency.

## Entry Conditions and Dependencies

- Phase 21 completed and verified.
- Universal async core, memory protection, and hardware key foundations operational.

## Sprint Sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-22.1](sprints/22.1.md) | FIDO2 Passkey software authenticator (resident keys, assertions) | Entry gate |
| [S-AUTH-22.2](sprints/22.2.md) | WebAuthn assertion bridge, v3.0.0 LTS API freeze, and release | S-AUTH-22.1 |

All tasks in each sprint must have automated synthetic test verification before closing.

## Deliverables and Evidence

- Passkey authenticator engine in `src/authy_local/passkeys.py` implementing CTAP2.1 authenticator makeCredential and getAssertion operations.
- Resident credential storage with AES-256-GCM / hardware-backed key encryption.
- WebAuthn bridge in `src/authy_local/webauthn_bridge.py` forwarding browser and CLI WebAuthn requests via local socket / virtual USB HID.
- CLI commands `otp-local passkey create`, `otp-local passkey list`, `otp-local passkey assert`.
- Frozen v3.0.0 LTS public API specification and deprecation cleanup.
- Comprehensive automated test suite in `tests/test_passkeys.py` and `tests/test_webauthn_bridge.py`.
- Architectural specification in [docs/specs/23-passkey-and-webauthn-bridge.md](../docs/specs/23-passkey-and-webauthn-bridge.md).

## Exit Criteria

- Successful WebAuthn registration and authentication against live W3C WebAuthn conformance test suite.
- Zero private key leakage across process boundaries.
- 100% test pass rate across all 22 project phases and quality gates.
