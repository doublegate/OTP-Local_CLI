# Phase 7: Windows DPAPI and Native Cross-Platform Shell Ecosystem

Status: Planned for release v1.2.0. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Deliver complete native Microsoft Windows platform parity by implementing the Windows Data Protection API (DPAPI) and Windows Credential Manager storage backend, Windows Hello biometric container binding, native PowerShell (`Microsoft.PowerShell`) and NuShell (`nu`) shell wrappers, Windows Terminal profile integration, and seamless WSL2 inter-process communication.

## Entry Conditions and Dependencies

- Base CLI, Textual TUI, and macOS Keychain backend operational (Phase 0–6 and v1.1.0 completed).
- Windows system APIs accessible via standard C runtime (`ctypes`) or Windows platform libraries (`win32crypt`, `win32cred`).
- Windows shell execution environments (PowerShell 7+, NuShell 0.90+) available for integration testing.

## Sprint Sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-7.1](sprints/7.1.md) | Windows DPAPI and Credential Manager backend | See sprint entry gate |
| [S-AUTH-7.2](sprints/7.2.md) | Windows shell ecosystem, PowerShell/NuShell wrappers, and WSL2 interop | S-AUTH-7.1 |

All tasks in each sprint must have automated synthetic test verification before closing.

## Deliverables and Evidence

- Windows DPAPI backend module in `src/authy_local/backends/dpapi.py` utilizing `CryptProtectData` and `CryptUnprotectData`.
- Windows Credential Manager integration for persistent encrypted credential blobs.
- Windows doctor automated capability detection and remediation via `winget` and `scoop`.
- PowerShell profile integration script in `shell/otp-local.ps1` with tab completions.
- NuShell integration script in `shell/otp-local.nu`.
- WSL2 named pipe / UNIX socket interop bridge in `src/authy_local/wsl_bridge.py`.
- Unit and adversarial test suites: `tests/test_dpapi_backend.py` and `tests/test_windows_shells.py`.
- Architectural decision record [ADR 0009](../docs/adr/0009-windows-dpapi-backend.md) and [Specification](../docs/specs/14-windows-dpapi.md).

## Exit Criteria

- 100% test pass rate across synthetic Windows DPAPI and shell test suites.
- Zero unencrypted secrets written to registry, Windows event logs, or temporary files.
- Verified Windows Doctor capability reporting and automated remediation logic.
