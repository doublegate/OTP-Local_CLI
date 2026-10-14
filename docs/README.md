# Documentation Index

This directory contains the complete technical specification, architectural decision records, operational procedures, verification reports, and testing infrastructure for OTP-Local CLI.

See [PROJECT-STATUS.md](../PROJECT-STATUS.md) for current implementation verification and [ROADMAP.md](../ROADMAP.md) for the phased delivery sequence.

---

## Directory Organization

```text
docs/
├── specs/       Core architectural, system, security, and interface specifications (01–23)
├── adr/         Architectural Decision Records (ADRs 0001–0014)
├── operations/  Operator checkpoints, runbook clarifications, and setup procedures
├── reports/     Verification, validation, and empirical testing reports
├── templates/   Reusable migration batch and private ledger templates
└── testing/     Testing infrastructure, tiered model, and modernization records
```

---

## 1. Core Specifications (`specs/`)

| Specification | Focus & Scope |
|---|---|
| [01: Requirements](specs/01-requirements.md) | Scope, requirement IDs, acceptance criteria, and traceability |
| [02: Architecture](specs/02-architecture.md) | Subsystems, components, data flows, and proposed boundaries |
| [03: CLI Specification](specs/03-cli-specification.md) | Commands, flags, validation rules, subprocess contracts, and error exit codes |
| [04: Security & Data](specs/04-security-and-data.md) | Threat model, memory lifecycle, private ledger storage, and credential isolation |
| [05: Development & Testing](specs/05-development-and-testing.md) | Toolchain, synthetic test fixtures, quality gates, and TDD workflow |
| [06: Instantiation](specs/06-installation-and-instantiation.md) | Host preparation, pipx / uv tool install, upgrade, and reversible uninstall |
| [06b: Security Architecture](specs/06-security-architecture.md) | Defense-in-depth runtime memory/filesystem isolation and audit waivers |
| [07: Migration & Recovery](specs/07-migration-and-recovery.md) | Human account migration batches, emergency recovery, and reconciliation |
| [08: Optional Backends](specs/08-optional-backends.md) | Hardware TPM (`totpm`) and GPG (`pass-otp`) stores, skip criteria, and fallbacks |
| [09: Operations & Completion](specs/09-operations-and-completion.md) | Maintenance, incident response, operational closure, and final acceptance |
| [10: Research & Host Evidence](specs/10-research-and-host-evidence.md) | Empirical tool observations, capability probes, and platform evidence |
| [11: Textual TUI](specs/11-tui.md) | Textual TUI layout, screens, keybindings, countdown progress, and fuzzy search |
| [12: OTP Enrollment](specs/12-otp-enrollment.md) | Direct addition from Base32/URI strings and screen QR codes |
| [13: Desktop Integration](specs/13-desktop-integration.md) | macOS Keychain, Darwin capabilities, desktop files, and systemd units |
| [14: Windows DPAPI](specs/14-windows-dpapi.md) | Windows DPAPI, Credential Manager, PowerShell/NuShell, and WSL2 interop |
| [15: FIDO2 Hardware](specs/15-fido2-hardware.md) | FIDO2 CTAP 2.1 HMAC-secret hardware keys, WebAuthn PRF, and touch presence |
| [16: PAM & Low-Latency IPC](specs/16-pam-and-ipc.md) | Sub-millisecond UNIX socket daemon, shared memory ring buffers, and Linux PAM |
| [17: Vault Federation](specs/17-vault-federation.md) | Bitwarden CLI (`bw`), direct KeePassXC `.kdbx4` engine, and unified search |
| [18: Security Auditor v2](specs/18-security-auditor-v2.md) | Memory locking (`mlock`), `MADV_DONTDUMP`, entropy analysis, and secret rotation |
| [19: v2 Architecture](specs/19-v2-architecture.md) | Universal async core (`asyncio`), pluggy plugin engine, and public API freeze |
| [20: Secret Service & Biometrics](specs/20-secret-service-and-biometrics.md) | D-Bus Secret Service provider and platform biometrics (Touch ID, Windows Hello) |
| [21: Specialized OTP Protocols](specs/21-specialized-otp-protocols.md) | Steam Guard, Blizzard, Yandex, and RFC 4226 HOTP counter synchronization |
| [22: Encrypted Backup & Sync](specs/22-encrypted-backup-and-sync.md) | Sovereign Age container format and decentralized WebDAV / S3 sync transports |
| [23: Passkeys & WebAuthn](specs/23-passkey-and-webauthn-bridge.md) | Sovereign identity, FIDO2 passkey software engine, and WebAuthn assertion bridge |

---

## 2. Architectural Decision Records (`adr/`)

| ADR | Title & Status | Key Decision Summary |
|---|---|---|
| [ADR 0001](adr/0001-default-store.md) | Default Store | 1Password as baseline; pass-otp and totpm as optional hardware/GPG stores |
| [ADR 0002](adr/0002-implementation-boundary.md) | Implementation Boundary | Standard subprocess boundary; no secret seeds passed via CLI argv |
| [ADR 0003](adr/0003-migration-and-optional-stores.md) | Migration & Optional Stores | Independent adoption of hardware stores without blocking baseline |
| [ADR 0004](adr/0004-cohesive-terminal-interface.md) | Cohesive Terminal Interface | Textual TUI terminal interface with responsive layouts and fuzzy filtering |
| [ADR 0005](adr/0005-explicit-local-backends.md) | Explicit Local Backends | Isolated backend modules (`onepassword`, `pass_otp`, `totpm`, `keychain`) |
| [ADR 0006](adr/0006-dashboard-interface.md) | Dashboard Interface | Unified dashboard view with live capability status badges and action triggers |
| [ADR 0007](adr/0007-confirmed-local-item-deletion.md) | Confirmed Local Deletion | Two-step case-sensitive typed `"DELETE"` confirmation modal |
| [ADR 0008](adr/0008-interactive-otp-enrollment.md) | Interactive OTP Enrollment | Ingestion from Base32, URI, and Wayland clipboard QR images via `zbarimg` |
| [ADR 0009](adr/0009-windows-dpapi-backend.md) | Windows DPAPI Backend | Native Windows Data Protection API, Credential Manager, and WSL2 pipe bridge |
| [ADR 0010](adr/0010-fido2-ctap2-hardware-tokens.md) | FIDO2 CTAP2 Hardware Tokens | Seedless zero-trust storage via FIDO2 CTAP 2.1 HMAC-secret extension |
| [ADR 0011](adr/0011-pam-module-and-low-latency-ipc.md) | PAM Module & Low-Latency IPC | Resident daemon with shared-memory ring buffers and native Linux PAM module |
| [ADR 0012](adr/0012-federated-multi-vault-architecture.md) | Federated Multi-Vault | Bitwarden CLI, KeePassXC KDBX4 direct parsing, and cross-vault deduplication |
| [ADR 0013](adr/0013-memory-forensics-and-process-isolation.md) | Memory Forensics Hardening | Process memory locking (`mlock`), `MADV_DONTDUMP`, and signal zeroization |
| [ADR 0014](adr/0014-v2-async-core-and-plugin-system.md) | v2.0 Async Core & Plugin System | Universal async coroutines, pluggy plugin engine, and frozen public API |

---

## 3. Operational Guides & Checkpoints (`operations/`)

| Document | Purpose |
|---|---|
| [2026-10-11 Runbook Clarification](operations/2026-10-11-runbook-clarification.md) | Initial runbook reconciliation and policy baseline |
| [2026-10-12 Phase 0 Readiness](operations/2026-10-12-phase-0-readiness.md) | Operator prerequisites, credential setup, and host readiness |
| [2026-10-12 Phase 1 Implementation](operations/2026-10-12-phase-1-implementation.md) | Implemented boundary and doctor module validation |
| [2026-10-12 Phase 3 Checkpoints](operations/2026-10-12-phase-3-operator-checkpoints.md) | Private pilot execution, batch migration, and exception handling |
| [2026-10-12 Phase 4–5 Checkpoints](operations/2026-10-12-phase-4-5-operator-checkpoints.md) | Dedicated GPG key recovery, physical TPM validation, and Authy retirement |
| [2026-10-12 Installer Implementation](operations/2026-10-12-installer.md) | Reversible installation script, symlink management, and wheel builds |
| [2026-10-12 Installation Preview](operations/2026-10-12-installation-preview.md) | Dry-run installation verification and safety bounds |
| [2026-10-12 Candidate Installation](operations/2026-10-12-candidate-installation.md) | Candidate wheel installation and live environment validation |
| [2026-10-12 Optional Setup](operations/2026-10-12-optional-setup.md) | Optional TPM 2.0 and GPG setup guides |

---

## 4. Verification & Validation Reports (`reports/`)

| Report | Verification Focus |
|---|---|
| [2026-10-11 Specification Validation](reports/2026-10-11-specification-validation.md) | Specification consistency and reference audit |
| [2026-10-12 Phase 0–1 Verification](reports/2026-10-12-phase-0-1-verification.md) | Phase 0 and Phase 1 test execution report |
| [2026-10-12 Phase 2 Verification](reports/2026-10-12-phase-2-verification.md) | Phase 2 UX, CLI, and reversible installer verification |
| [2026-10-12 Phase 4–5 Verification](reports/2026-10-12-phase-4-5-verification.md) | Phase 4 and Phase 5 native backend and completion evidence |
| [2026-10-12 TUI Resident Scope Verification](reports/2026-10-12-tui-resident-scope-verification.md) | Textual TUI browser, scope file isolation, and transient display |
| [2026-10-12 TUI Deletion Verification](reports/2026-10-12-tui-deletion-verification.md) | Case-sensitive confirmation and backend deletion refusal verification |
| [2026-10-12 TUI Status Tag Verification](reports/2026-10-12-tui-status-tag-verification.md) | Real-time doctor capability badges and metadata tag filtering |

---

## 5. Templates (`templates/`)

| Template | Usage |
|---|---|
| [Migration Batch Template](templates/migration-batch-template.md) | Standard non-identifying template for tracking account migration batches |
| [Private Ledger Template](templates/private-ledger-template.md) | Schema for private off-repo credential ledger |

---

## 6. Testing Infrastructure (`testing/`)

| Document | Coverage & Standards |
|---|---|
| [Testing Infrastructure](testing/infrastructure.md) | Architecture of the 4-tier opaque-box test suite and feature inventory |
| [Testing Readiness](testing/readiness.md) | 100% pass verification and readiness report for test suites |
| [Project Modernization](testing/project-modernization.md) | Modernization roadmap and milestone inventory |
