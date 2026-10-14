# Phase 13: Freedesktop Secret Service (D-Bus) and Platform Biometrics (v2.1.0)

Status: Planned; milestone for release v2.1.0. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Deliver native Linux desktop session integration by implementing a D-Bus Freedesktop Secret Service provider (`org.freedesktop.secrets`) allowing desktop clients (browsers, IDEs, git credential helpers) to query OTP secrets directly, paired with hardware-backed platform biometric authorization (macOS Touch ID, Windows Hello, Linux `fprintd` / PAM).

## Entry Conditions and Dependencies

- v2.0.0 LTS core release and public API baseline verified green.
- Universal async core (`src/authy_local/async_core.py`) and plugin engine operational.
- Platform capability diagnostics validated in `otp-local doctor`.

## Sprint Sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-13.1](sprints/13.1.md) | Freedesktop Secret Service D-Bus provider and session negotiation | Entry gate |
| [S-AUTH-13.2](sprints/13.2.md) | Platform biometric authorization (Touch ID, Windows Hello, fprintd) | S-AUTH-13.1 |

All tasks in each sprint must have automated synthetic test verification before closing.

## Deliverables and Evidence

- D-Bus Secret Service provider module in `src/authy_local/secret_service.py` implementing `org.freedesktop.Secret.Service`, `org.freedesktop.Secret.Collection`, and `org.freedesktop.Secret.Item`.
- Cryptographic session negotiation supporting `plain` and `dh-ietf1024-sha256-aes128-cbc-pkcs7` encryption algorithms over D-Bus.
- Platform biometric module in `src/authy_local/biometrics.py` supporting macOS `LAContext`, Windows `UserConsentVerifier`, and Linux `net.reactivated.Fprint`.
- CLI and configuration options for `--biometric` enforcement on sensitive token reads.
- Automated synthetic unit and mock integration test suites in `tests/test_secret_service.py` and `tests/test_biometrics.py`.
- Architectural specification in [docs/specs/20-secret-service-and-biometrics.md](../docs/specs/20-secret-service-and-biometrics.md).

## Exit Criteria

- D-Bus Secret Service specification compliance verified using `secret-tool` and standard desktop client mock harness.
- Platform biometric challenges fail closed upon sensor timeout or cancellation.
- 100% test pass rate with zero regression in CLI and TUI workflows.
