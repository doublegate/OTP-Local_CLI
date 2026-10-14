# Implementation specification

Status: design baseline expanded for both local backends and dashboard delivery, 2026-10-12.
Live installation and migration evidence remain separate from implementation.
See [project status](../PROJECT-STATUS.md) for verified completion and blockers.

| Read | Purpose |
|---|---|
| [Requirements](specs/01-requirements.md) | Scope, requirement IDs, acceptance and traceability |
| [Architecture](specs/02-architecture.md) | Components, dependencies, flows and proposed files |
| [CLI specification](specs/03-cli-specification.md) | Commands, validation, subprocess and error contracts |
| [Security and data](specs/04-security-and-data.md) | Threat boundaries, private ledger, secret lifecycle |
| [Development and testing](specs/05-development-and-testing.md) | Toolchain, fixtures, gates and implementation order |
| [Instantiation](specs/06-installation-and-instantiation.md) | Host preparation, install, upgrade and uninstall |
| [Security architecture](specs/06-security-architecture.md) | Runtime defense-in-depth boundaries and audit waivers |
| [Migration and recovery](specs/07-migration-and-recovery.md) | Human account workflow and failure handling |
| [Optional backends](specs/08-optional-backends.md) | pass-otp, totpm, compatibility and skip gates |
| [Operations and completion](specs/09-operations-and-completion.md) | Maintenance, incidents, final acceptance |
| [Research and host evidence](specs/10-research-and-host-evidence.md) | Dated observations, primary sources and open checks |
| [Curses TUI](specs/11-tui.md) | Resident backend scope, native item browsing, transient codes and installation preview |
| [Resident TUI verification](reports/2026-10-12-tui-resident-scope-verification.md) | Installed rc2, private profile safeguards and synthetic browser evidence |
| [Operator checkpoints](operations/2026-10-12-phase-3-operator-checkpoints.md) | Private synthetic acceptance, pilot and bounded batches |
| [Phase 4–5 private acceptance](operations/2026-10-12-phase-4-5-operator-checkpoints.md) | Dedicated GPG recovery, physical TPM and operational closure |
| [Phase 4–5 software evidence](reports/2026-10-12-phase-4-5-verification.md) | Candidate, quality gates, native synthetic results and remaining limits |
| [Installer implementation](operations/2026-10-12-installer.md) | Preview/apply API, ownership, recovery and limits |
| [Aggregate batch template](templates/migration-batch-template.md) | Non-identifying migration evidence and reconciliation |
| [ADRs](adr/0001-default-store.md) | Store choice; linked follow-on decisions |
| [Local deletion verification](reports/2026-10-12-tui-deletion-verification.md) | Installed rc3, exact targeting and confirmed synthetic deletion |
| [TUI status and tag verification](reports/2026-10-12-tui-status-tag-verification.md) | Installed rc4, retained Doctor status and optional OTP metadata filter |
| [Local deletion decision](adr/0007-confirmed-local-item-deletion.md) | Typed confirmation, resident scope and exact local deletion boundaries |
| [OTP Enrollment](specs/12-otp-enrollment.md) | Interactive addition via Base32/URI strings and screen QR codes |
| [OTP enrollment decision](adr/0008-interactive-otp-enrollment.md) | Interactive enrollment, live verification challenge, and multi-backend storage |
| [Desktop integration](specs/13-desktop-integration.md) | macOS Keychain, Darwin capabilities, and desktop environments |
| [Windows DPAPI](specs/14-windows-dpapi.md) | Windows DPAPI backend, PowerShell/NuShell, and WSL2 interop |
| [Windows DPAPI decision](adr/0009-windows-dpapi-backend.md) | Native Windows DPAPI, Credential Manager, and WSL2 pipe bridge |
| [FIDO2 hardware](specs/15-fido2-hardware.md) | FIDO2 / CTAP2.1 HMAC-secret hardware tokens and touch presence |
| [FIDO2 hardware decision](adr/0010-fido2-ctap2-hardware-tokens.md) | Hardware-enforced isolation via CTAP 2.1 HMAC-secret extension |
| [PAM and IPC](specs/16-pam-and-ipc.md) | Low-latency UNIX socket daemon, shared memory, and Linux PAM module |
| [PAM and IPC decision](adr/0011-pam-module-and-low-latency-ipc.md) | Resident socket daemon, shared memory IPC, and native Linux PAM |
| [Vault federation](specs/17-vault-federation.md) | Enterprise Bitwarden CLI and KeePassXC KDBX4 direct engine |
| [Vault federation decision](adr/0012-federated-multi-vault-architecture.md) | Enterprise multi-vault federation and open password formats |
| [Security auditor v2](specs/18-security-auditor-v2.md) | Memory forensics (mlock/MADV_DONTDUMP), entropy analysis, and rotation |
| [Memory forensics decision](adr/0013-memory-forensics-and-process-isolation.md) | Runtime memory forensics hardening and process isolation |
| [v2 architecture](specs/19-v2-architecture.md) | Universal async core, extensible plugin engine, and public API freeze |
| [v2 async core decision](adr/0014-v2-async-core-and-plugin-system.md) | Universal async core, extensible plugin hook engine, and v2.0.0 freeze |
| [Secret service and biometrics](specs/20-secret-service-and-biometrics.md) | Freedesktop Secret Service (D-Bus) and platform biometrics |
| [Specialized OTP protocols](specs/21-specialized-otp-protocols.md) | Steam Guard, Blizzard, Yandex, and RFC 4226 HOTP counter sync |
| [Encrypted backup and sync](specs/22-encrypted-backup-and-sync.md) | Zero-knowledge Age container and WebDAV / S3 sync protocols |
| [Passkeys and WebAuthn](specs/23-passkey-and-webauthn-bridge.md) | Sovereign identity, FIDO2 passkeys, and WebAuthn assertion bridge |

Start delivery at the [roadmap](../ROADMAP.md) and [phase/sprint index](../to-dos/README.md).
[PROJECT-STATUS.md](../PROJECT-STATUS.md) remains the single authority for progress.
The [dated validation report](reports/2026-10-11-specification-validation.md) records
documentation checks and their limits.

The [Phase 0 readiness refresh](operations/2026-10-12-phase-0-readiness.md) records current
prerequisites and completed operator attestations. The
[Phase 1 implementation note](operations/2026-10-12-phase-1-implementation.md) describes
the implemented boundary. A [blank private-ledger template](templates/private-ledger-template.md)
must be populated only in private storage outside the project.

The [TUI decision](adr/0004-cohesive-terminal-interface.md) records the accepted
standard-library approach and shared interface boundary. The
[local backend decision](adr/0005-explicit-local-backends.md),
[dashboard decision](adr/0006-dashboard-interface.md) and
[optional setup preview](operations/2026-10-12-optional-setup.md) specify the selected extensions.

The [original runbook](../ref-docs/Authy-to-1Password-and-Local-CLI-TOTP-Migration-Runbook-v2.md)
is background reference. The [first clarification](operations/2026-10-11-runbook-clarification.md)
and these derived specifications resolve its inconsistencies. New evidence is
recorded in dated supplements; do not rewrite the reference.

Specification precedence: explicit user decisions, project security refinements,
accepted ADRs, these implementation contracts, then historical examples. ADRs
marked proposed are recommendations until their phase gate is satisfied.

Planning includes all required delivery phases and optional branches. Authorization
to write this plan does not authorize installing packages, reading vault contents,
enrolling MFA, removing Authy devices, committing, or publishing.
