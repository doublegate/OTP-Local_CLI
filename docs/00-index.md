# Implementation specification

Status: design baseline expanded for both local backends and dashboard delivery, 2026-10-12.
Live installation and migration evidence remain separate from implementation.
See [project status](../PROJECT-STATUS.md) for verified completion and blockers.

| Read | Purpose |
|---|---|
| [Requirements](01-requirements.md) | Scope, requirement IDs, acceptance and traceability |
| [Architecture](02-architecture.md) | Components, dependencies, flows and proposed files |
| [CLI specification](03-cli-specification.md) | Commands, validation, subprocess and error contracts |
| [Security and data](04-security-and-data.md) | Threat boundaries, private ledger, secret lifecycle |
| [Development and testing](05-development-and-testing.md) | Toolchain, fixtures, gates and implementation order |
| [Instantiation](06-installation-and-instantiation.md) | Host preparation, install, upgrade and uninstall |
| [Migration and recovery](07-migration-and-recovery.md) | Human account workflow and failure handling |
| [Optional backends](08-optional-backends.md) | pass-otp, totpm, compatibility and skip gates |
| [Operations and completion](09-operations-and-completion.md) | Maintenance, incidents, final acceptance |
| [Research and host evidence](10-research-and-host-evidence.md) | Dated observations, primary sources and open checks |
| [Curses TUI](11-tui.md) | Resident backend scope, native item browsing, transient codes and installation preview |
| [Resident TUI verification](2026-10-12-tui-resident-scope-verification.md) | Installed rc2, private profile safeguards and synthetic browser evidence |
| [Operator checkpoints](2026-10-12-phase-3-operator-checkpoints.md) | Private synthetic acceptance, pilot and bounded batches |
| [Phase 4–5 private acceptance](2026-10-12-phase-4-5-operator-checkpoints.md) | Dedicated GPG recovery, physical TPM and operational closure |
| [Phase 4–5 software evidence](2026-10-12-phase-4-5-verification.md) | Candidate, quality gates, native synthetic results and remaining limits |
| [Installer implementation](2026-10-12-installer.md) | Preview/apply API, ownership, recovery and limits |
| [Aggregate batch template](migration-batch-template.md) | Non-identifying migration evidence and reconciliation |
| [ADRs](adr/0001-default-store.md) | Store choice; linked follow-on decisions |
| [Local deletion verification](2026-10-12-tui-deletion-verification.md) | Installed rc3, exact targeting and confirmed synthetic deletion |
| [TUI status and tag verification](2026-10-12-tui-status-tag-verification.md) | Installed rc4, retained Doctor status and optional OTP metadata filter |
| [Local deletion decision](adr/0007-confirmed-local-item-deletion.md) | Typed confirmation, resident scope and exact local deletion boundaries |
| [OTP Enrollment](12-otp-enrollment.md) | Interactive addition via Base32/URI strings and screen QR codes |
| [OTP enrollment decision](adr/0008-interactive-otp-enrollment.md) | Interactive enrollment, live verification challenge, and multi-backend storage |

Start delivery at the [roadmap](../ROADMAP.md) and [phase/sprint index](../to-dos/README.md).
[PROJECT-STATUS.md](../PROJECT-STATUS.md) remains the single authority for progress.
The [dated validation report](2026-10-11-specification-validation.md) records
documentation checks and their limits.

The [Phase 0 readiness refresh](2026-10-12-phase-0-readiness.md) records current
prerequisites and completed operator attestations. The
[Phase 1 implementation note](2026-10-12-phase-1-implementation.md) describes
the implemented boundary. A [blank private-ledger template](private-ledger-template.md)
must be populated only in private storage outside the project.

The [TUI decision](adr/0004-cohesive-terminal-interface.md) records the accepted
standard-library approach and shared interface boundary. The
[local backend decision](adr/0005-explicit-local-backends.md),
[dashboard decision](adr/0006-dashboard-interface.md) and
[optional setup preview](2026-10-12-optional-setup.md) specify the selected extensions.

The [original runbook](../ref-docs/Authy-to-1Password-and-Local-CLI-TOTP-Migration-Runbook-v2.md)
is background reference. The [first clarification](2026-10-11-runbook-clarification.md)
and these derived specifications resolve its inconsistencies. New evidence is
recorded in dated supplements; do not rewrite the reference.

Specification precedence: explicit user decisions, project security refinements,
accepted ADRs, these implementation contracts, then historical examples. ADRs
marked proposed are recommendations until their phase gate is satisfied.

Planning includes all required delivery phases and optional branches. Authorization
to write this plan does not authorize installing packages, reading vault contents,
enrolling MFA, removing Authy devices, committing, or publishing.
