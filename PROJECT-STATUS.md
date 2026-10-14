# Project status

This file is the authority for project progress. Last reviewed: 2026-10-14
(America/New_York).

## Current state

Phases 0–12 are complete, and Phases 13–22 are scaffolded for the v2.1.0–v3.0.0 LTS
strategic roadmap. The software is formally released and verified as version 2.0.1 LTS.
The package provides cross-platform system diagnostics (`doctor` with automated `--install`/`--fix`
capability remediation for macOS Homebrew, Linux `apt`/`pacman`/`dnf`, and Windows `winget`/`scoop`),
scoped retrieval and clipboard handoff (`show`/`copy`/`select`/`list`/`search`), interactive 1Password session
`unlock`, desktop quick-picking (`pick`), bulk `import` and `export` with TOCTOU-free `O_NOFOLLOW` symlink defense,
autonomous credential `audit` (`SEC-001` through `SEC-007` with `--rotate`), terminal `qr` rendering, a 16-worker
resident UNIX socket `daemon` with zero-copy POSIX shared-memory seqlock ring buffers (`~2.2 us`), native Linux PAM
integration (`pam_otp_local.so`), a non-blocking `asyncio` federation engine (`3.75x` speedup), and a `pluggy`
plugin hook architecture. `otp-local tui` provides a modern Textual dashboard supporting nine credential backends
(`onepassword`, `bitwarden`, `keepass`, `pass-otp`, `totpm`, `yubikey`, `tpm2-totp`, `keychain`, `dpapi`, `fido2`)
plus unified multi-vault `federated` resolution.

Automated validation uses synthetic data across 1,258 tests (1,140 unit/integration and 118 opaque-box E2E
tests, plus 852 subtests) with a 100% pass rate and 7 authentic microbenchmarks meeting all SLAs. The operator
approved the exact home installation and verified live operations. Checkpoint A disposable acceptance
and Checkpoint B pilot-001 passed on operator attestation.

| Area | State | Evidence |
|---|---|---|
| Agent guidance | Configured | Inline Master-Claude core 0.2.0; canonical AGENTS.md with sibling symlinks |
| Entry point and plan | Released v2.0.1 LTS delivered; v3.0 roadmap scaffolded | 22 phases (0–12 complete, 13–22 planned); 45 sprints; 188 allocated tasks |
| Migration reference | Preserved; derived baseline researched | Immutable v2 runbook, clarification, docs/00-index.md |
| CLI/TUI and shells | Released v2.0.1 installed and verified | 9 backends + federated resolver, Textual TUI, fish/bash/zsh/pwsh/nu wrappers |
| Reversible installation | Operator-approved and applied | docs/operations/2026-10-12-installation-preview.md; wheelhouse staging & smoke pass |
| Host prerequisites | Read-only snapshot verified | docs/operations/2026-10-12-phase-0-readiness.md |
| Human 1Password readiness | Operator-attested pass | Desktop unlock and scoped CLI approval; Checkpoint A disposable acceptance passed |
| Account migration | Pilot migrated, operator-attested | pilot-001: total 1, migrated 1, blocked 0, pending 0; full inventory unknown |
| Automated tests/lint/build | All quality gates pass | 1,258 tests (1,140 unit/integration + 118 E2E); 7/7 benchmarks; ruff & markdownlint clean |
| Version control | GitHub `doublegate/OTP-Local_CLI` synced | Tagged releases through v2.0.1; GitHub Actions CI & Release workflows green |

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
| T-AUTH-008: High-speed daemon IPC & shared memory | Complete | S-AUTH-9.1 complete; resident daemon, CBOR IPC, and POSIX SHM ring buffer pass |
| T-AUTH-009: Linux PAM integration & v1.4.0 release | Complete | S-AUTH-9.2 complete; native C PAM module, Makefile, and doctor --pam pass |
| T-AUTH-010: Bitwarden & KeePassXC Multi-Vault Federation | Complete | S-AUTH-10.1 and S-AUTH-10.2 complete; Bitwarden, KeePassXC, and FederatedResolver pass |
| T-AUTH-011: Memory Forensics Hardening & Security Auditor v2 | Complete | S-AUTH-11.1 and S-AUTH-11.2 complete; mlock, madvise_dontdump, SecureBuffer, and Auditor v2 pass |
| T-AUTH-012: Universal Async Core, Plugin Engine & v2.0.0 LTS | Complete | S-AUTH-12.1 and S-AUTH-12.2 complete; AsyncCore, JSON-RPC, pluggy plugins, and frozen API pass |
| T-AUTH-013: v2.0.1 CI Repair, Security Hardening & Performance Release | Complete | Milestones M1–M5 & Victory Audit pass; 1,258 tests, 7 benchmarks, and v2.1–v3.0 roadmap complete |

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
| 9 Daemon IPC & PAM | Complete | Sprints 9.1 and 9.2 complete; resident daemon, CBOR IPC, SHM ring buffer, and Linux PAM module pass |
| 10 Multi-Vault Federation | Complete | Sprints 10.1 and 10.2 complete; Bitwarden, KeePassXC, and multi-vault federation pass |
| 11 Security auditor v2 | Complete | Sprints 11.1 and 11.2 complete; memory forensics hardening, entropy analysis, and rotation advisor pass |
| 12 Universal async & plugins | Complete | Sprints 12.1 and 12.2 complete; non-blocking async core, pluggy plugin engine, and public API freeze pass |
| 13–22 v2.1.0 – v3.0.0 LTS Roadmap | Planned (Scaffolded) | Sprints 13.1–22.2 (`T-AUTH-130`–`T-AUTH-227`) and Specs 20–23 scaffolded and verified |

Package version is 2.0.1.

## Metrics and timeline

| Metric | Snapshot | Source |
|---|---|---|
| Derived specification | Twenty-four numbered specs and fourteen ADRs | docs/00-index.md |
| Delivery plan | Twenty-three phases (0–22); forty-five sprints; 188 allocated tasks | to-dos/README.md and sprint files |
| Software/test/release | v2.0.1 LTS / 1,258 tests pass (1,140 unit/integration + 118 E2E) / 100% pass rate | tests/ |
| Coverage & benchmarks | 80%+ branch coverage (100% on critical modules); 7/7 microbenchmarks pass | scripts/check.sh and benchmarks/run_all.py |
| Account outcomes | Pilot: 1 migrated / 0 blocked / 0 pending; full inventory unknown | Checkpoint B operator attestation; no private inventory read |
| Documentation validation | 140 authored files; links, task IDs and lint pass; reference hash unchanged | scripts/check_docs.py |

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

2026-10-13: delivered final release v1.0.0 through v2.0.0 LTS across Phases 7–12:
Windows DPAPI & Credential Manager (`v1.2.0`), FIDO2 CTAP 2.1 hardware keys with touch presence (`v1.3.0`),
resident UNIX socket daemon, POSIX shared memory ring buffer, and Linux PAM module (`v1.4.0`),
Bitwarden and KeePassXC multi-vault federation (`v1.5.0`), runtime memory forensics (`mlock`/`MADV_DONTDUMP`)
and Autonomous Security Auditor v2 (`v1.6.0`), and Universal Async Core, Pluggy plugin engine, and
public API freeze (`v2.0.0 LTS`).

2026-10-14: delivered release v2.0.1 LTS and scaffolded the v2.1.0–v3.0.0 LTS roadmap (Phases 13–22,
Sprints 13.1–22.2, `T-AUTH-130`–`T-AUTH-227`, Specs 20–23). Resolved all GitHub Actions CI runner gaps
(`libpam0g-dev`, Node.js 22 LTS, wheel dependency regex for `fido2` and `pluggy`), hardened filesystem and
memory boundaries (`O_NOFOLLOW` TOCTOU defense, `field(repr=False)` secret shielding, daemon `pid <= 0` bounds,
C PAM RFC 8259 JSON escaping and stack zeroization, Textual modal unmount zeroization), optimized hot-paths
(`2.2 us` seqlock SHM reads, `31 us` 16-worker IPC, `3.75x` `asyncio.as_completed` federation, `1.5 ms` TUI
debounced search), and added CLI `list`, `search`, `daemon restart`, `daemon clean`, and multi-distro Linux
`doctor --install` remediation. Verified across 1,258 passing tests (1,140 unit/integration + 118 E2E) and
7 authentic microbenchmarks.

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
