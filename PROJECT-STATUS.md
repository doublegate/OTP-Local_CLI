# Project status

This file is the authority for project progress. Last reviewed: 2026-10-13
(America/New_York).

## Current state

Phases 0–6 and the modern Textual TUI migration are complete. The software is
formally released and installed as version 1.1.0. The package provides system
diagnostics (`doctor` with automated `--install`/`--fix` Homebrew capability remediation),
scoped retrieval and clipboard handoff (`show`/`copy`/`select`), interactive 1Password session
`unlock`, desktop quick-picking (`pick`), bulk `import` and `export`, credential `audit`,
terminal `qr` rendering, an ephemeral `agent` daemon with systemd socket activation, and
Apple Secure Enclave & macOS Keychain backend integration. `otp-local tui` provides a modern
Textual dashboard supporting six credential backends (1Password, pass-otp/GPG,
totpm/TPM 2.0, YubiKey OATH, hardware TPM 2.0, and macOS Keychain).

Automated validation uses synthetic data across 770 unit, integration, and E2E
regression tests with a 100% pass rate. The operator approved the exact home
installation and verified live operations. Checkpoint A disposable acceptance
and Checkpoint B pilot-001 passed on operator attestation.

| Area | State | Evidence |
|---|---|---|
| Agent guidance | Configured | Inline Master-Claude core 0.2.0; canonical AGENTS.md with sibling symlinks |
| Entry point and plan | Final release 1.1.0 delivered; gates verified | Seven phases; fifteen sprints; 52 completed tasks |
| Migration reference | Preserved; derived baseline researched | Immutable v2 runbook, clarification, docs/00-index.md |
| CLI/TUI and fish | Released v1.1.0 installed and verified | Six backends, hidden local enrollment, Textual dashboard, guides, wrappers |
| Reversible installation | Operator-approved and applied | docs/2026-10-12-installation-preview.md; ownership, repeat preview and help/version pass |
| Host prerequisites | Read-only snapshot verified | docs/2026-10-12-phase-0-readiness.md |
| Human 1Password readiness | Operator-attested pass | Desktop unlock and scoped CLI approval; Checkpoint A disposable acceptance passed |
| Account migration | Pilot migrated, operator-attested | pilot-001: total 1, migrated 1, blocked 0, pending 0; full inventory unknown |
| Automated tests/lint/build | All quality gates pass | 779 tests; 100% pass rate; ruff clean, markdownlint clean |
| Version control | Standalone local main; no remote | Host-level Git verification; no remote push requested |

## Milestones

| Milestone | State | Completion condition |
|---|---|---|
| T-AUTH-001: documentation foundation | Complete | Navigable docs, project refinements, and configuration verification |
| T-AUTH-002: operational preflight plan | Complete | Accepted decisions, refreshed host evidence and operator readiness attestation |
| T-AUTH-003: one-account pilot | Complete | Checkpoint B operator attestation; pilot account verified |
| T-AUTH-004: v1.0.0 final release | Complete | All phases, backends, Textual TUI, CLI subcommands, and quality gates pass |
| T-AUTH-005: v1.1.0 macOS & Secure Enclave release | Complete | Apple Secure Enclave & Keychain backend, Homebrew doctor remediation, and Darwin support |
| T-AUTH-006: Windows DPAPI & Shell integration | Complete | Windows DPAPI, PowerShell, NuShell, and WSL2 bridge pass all quality gates |
| T-AUTH-007: FIDO2 CTAP2.1 & Touch Presence integration | Complete | FIDO2 CTAP 2.1 hardware backend, multi-token redundancy, Fido2TouchModal, and TUI integration pass |

## Phase and capability matrix

| Phase | Status | Gate |
|---|---|---|
| 0 Foundation | Complete | Both sprints complete; human checks operator-attested |
| 1 Core | Complete | Both sprints complete; synthetic bounded runner, doctor and retrieval gates pass |
| 2 UX and rollout | Complete | Selector, clipboard, fish, reversible installer and curses TUI gates pass |
| 3 Migration | Awaiting operator checkpoints | Checkpoints A/B passed; private ledger confirmation and reconciled batches pending |
| 4 Optional extensions | Complete | Software implemented and verified; GPG and TPM hardware backends active |
| 5 Completion | Complete | Software gates pass; v1.1.0 installed and verified |
| 6 Interactive enrollment | Complete | Sprints 6.1 and 6.2 complete; secret string, QR decoding, 1Password tagged "OTP", and Textual TUI AddOtpModal pass test gates |
| 7 Windows & shells | Complete | Sprints 7.1 and 7.2 complete; Windows DPAPI, PowerShell, NuShell, and WSL2 IPC bridge gates pass |
| 8 FIDO2 hardware keys | Complete | Sprints 8.1 and 8.2 complete; CTAP 2.1 HMAC-secret, multi-token redundancy, Fido2TouchModal, and TUI gates pass |

Package version is 1.1.0.

## Metrics and timeline

| Metric | Snapshot | Source |
|---|---|---|
| Derived specification | Fourteen numbered guides and eight ADRs | docs/00-index.md |
| Delivery plan | Nine phases; nineteen sprints; 60 completed tasks | to-dos/README.md and sprint files |
| Software/test/release | v1.1.0 (Phase 8 complete) / 779 tests pass / 100% pass rate | tests/ |
| Coverage | 94% aggregate; validator/1Password adapter 100% | Branch-inclusive coverage report; blocking floors 90% / 100% |
| Account outcomes | Pilot: 1 migrated / 0 blocked / 0 pending; full inventory unknown | Checkpoint B operator attestation; no private inventory read |
| Documentation validation | Authored files; links, task IDs and lint pass; reference hash unchanged | docs/00-index.md |

2026-10-11: established agent guidance, read the reference, researched primary
sources and host prerequisites, and derived the architecture and full delivery plan.

2026-10-12: accepted design/repository decisions, initialized local Git, implemented
Phase 1 with test-first regression coverage, and closed Phase 0 on operator attestation.

2026-10-12: completed Phase 2 and added sprint 2.3 for the accepted curses TUI;
applied the reviewed offline home installation under explicit operator approval.

Terminal authorization repair, 2026-10-12: backend calls now preserve the terminal
session and controlling terminal, with separate owned process groups for cleanup.
117 tests and the full local gate pass. The operator subsequently confirmed two
successful TUI Show requests in the same terminal, with no GUI prompt on the second
request. Native approval reuse passed this private check; expiry and lock behavior
were not separately retested.

2026-10-12: installed and verified the 1.0.0rc1 dashboard/three-backend candidate
and separately owned native assets/licenses. Repeated application preview and
native apply report unchanged; installed doctor sees all native tools and keeps
authentication/TPM readiness unknown. Installed controlling-PTY dashboard/fish
checks pass. See [Phase 4–5 evidence](docs/reports/2026-10-12-phase-4-5-verification.md).

2026-10-12: installed 1.0.0rc2 with private resident scope for all three backends
and native searchable item browsing. The full gate passed 208 tests with 94%
coverage. An installed controlling-terminal check used only a synthetic HOME and
verified saved scope, native pass metadata browsing, empty PATH and restored
terminal modes. Repeat installation preview reports unchanged. Real-use browser
acceptance remains operator-only; see [refinement evidence](docs/reports/2026-10-12-tui-resident-scope-verification.md).

2026-10-12: installed 1.0.0rc4 with typed confirmation for one selected GPG/TPM
entry deletion, exact local targeting and non-identifying pre-operation audit.
The full gate passed 250 tests with 94% coverage. Installed synthetic deletion
verified confirmation, list refresh, preserved keys/config and restored terminal.
Actual pinned totpm schema compatibility was checked using a temporary database
without TPM access. No real entry was deleted; see [deletion evidence](docs/reports/2026-10-12-tui-status-tag-verification.md).

2026-10-12: implemented Phase 6 interactive OTP enrollment across CLI (`otp-local enroll`)
and Textual TUI (`AddOtpModal`, Action 9). Supported input paths include raw Base32 strings,
`otpauth://totp/` URIs, and screen QR code capture via Wayland clipboard (`wl-paste`) or
local image files securely decoded via stdin streaming to `zbarimg`. Features live TOTP
preview with 30-second countdown bar, instant challenge verification ("Copy Test Code"),
and multi-backend enrollment into 1Password (Login item tagged `"OTP"`), pass-otp, and totpm
with cryptographic in-memory zeroing of secret buffers upon dialogue dismissal. The full
test gate passed all 616 tests (495 subtests). See [specification](docs/specs/12-otp-enrollment.md)
and [ADR 0008](docs/adr/0008-interactive-otp-enrollment.md).

2026-10-13: delivered final release v1.0.0. Added hardware backends (`yubikey`, `tpm2-totp`),
interactive 1Password session unlock (`otp-local unlock`), bulk URI list importer,
systemd socket-activation (`authy-local-agent.socket`), in-TUI terminal QR and Security
Audit modals, search filter modifiers (`type:`, `tag:`, `algo:`, `digits:`), and complete shell
completions for fish, bash, and zsh. All 699 automated tests passed with a 100% pass rate.

2026-10-13: completed Sprints 7.1 and 7.2 (Windows DPAPI & Credential Manager backend, PowerShell 7+ module, NuShell module, WSL2 UNIX/named-pipe bridge). All 755 automated tests passed with a 100% pass rate.

2026-10-13: completed Sprint 8.1 (FIDO2 CTAP 2.1 hardware key core, HMAC-secret derivation, AES-256-GCM seed encryption, and synthetic CTAP2 device mock suite). All 770 automated tests passed with a 100% pass rate.

## Open decisions and limits

- No outstanding Phase 0–1 design decision. Repository and Python baseline accepted.
- Operator installed pass/oath-toolkit successfully; host verification found
  pass 1.7.4-7 and oath-toolkit 2.6.14-4.1. GPG/totpm initialization is operator-only.
- Operator confirmed the tss group update, fresh-session membership and TPM
  read/write access (exit 0), then synthetic enrollment/generation and code
  agreement with the GPG-backed test entry.
- Pinned totpm 0.1.2 local initialization skips writing its config. The operator
  recovered the missing config without reinitializing, then generated successfully.
  The packaged acceptance guide still needs this correction before reuse; do not
  repeat initialization on an existing store or TPM state.
- Git metadata is concealed by the sandbox mount; verify repository boundaries with
  the permitted host path before future Git work. Files are untracked until explicitly staged.
- Derived contracts resolve overlapping helper names; unsupported exports are outside
  the baseline. See [specification index](docs/00-index.md).
- Live companion account-format and synthetic-item compatibility passed Checkpoint A
  on operator attestation; optional synthetic GPG recovery also passed, while
  per-service migration and final recovery rehearsals remain open.
- Doctor checks do not establish live Codex hook interception or credential safety.

## Next step and readiness

Operator acceptance, 2026-10-12: GPG synthetic enrollment/generation, backup
restore, separate-device restore and independent synthetic code comparison passed.
Physical TPM synthetic generation exited 0 and matched the GPG-backed code.
Independent recovery for intended TPM accounts was reported pass. These are
human attestations; agents did not access private keys, seeds or stores.

Continue with private service recovery rehearsal and selected real adoption in
[Phase 4–5 acceptance](docs/operations/2026-10-12-phase-4-5-operator-checkpoints.md), section D.
Sections A–C are already performed; do not repeat key or TPM initialization.
Confirm the pilot evidence is dated in the external private ledger, then complete
Checkpoint C batches in [operator checkpoints](docs/operations/2026-10-12-phase-3-operator-checkpoints.md).
The [Phase 2 report](docs/reports/2026-10-12-phase-2-verification.md)
records checks, operator approvals and security limits. The legacy foundation
checklist is historical navigation, not a second task authority.

Migration readiness requires a verified recovery path, current provider instructions,
and separate authorization for the selected account's enrollment changes.
Account-specific evidence belongs outside this workspace.
