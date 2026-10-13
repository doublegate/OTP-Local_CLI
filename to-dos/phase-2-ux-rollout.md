# Phase 2: User experience and reversible rollout

Status: complete. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Deliver selection, clipboard, fish wrappers, ownership-aware installation and a
cohesive standard-library curses TUI.

## Entry conditions and dependencies

Phase 1 complete.
This plan authorizes no execution by itself. Planning does not authorize host installation,
secret access, service MFA changes, commits, or publication.

## Sprint sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-2.1](sprints/2.1.md) | Selector and clipboard | See sprint entry gate |
| [S-AUTH-2.2](sprints/2.2.md) | Fish wrappers and installer | See sprint entry gate |
| [S-AUTH-2.3](sprints/2.3.md) | Cohesive curses TUI | 2.1 and 2.2 |

Run each sprint only after its dependencies pass; Phase 4 alternatives may be
selected independently and may both be skipped with recorded reasons.
All four tasks in each selected sprint must have explicit evidence before closing it.

## Deliverables and evidence

- Sprint outputs and their requirement/acceptance references.
- Current aggregate progress in [PROJECT-STATUS.md](../PROJECT-STATUS.md).
- Test/validation report identifying passed, failed, skipped, and unknown checks.
- Explicit blocker and exception dispositions, without account identities or secrets.

Private per-account evidence stays outside the workspace. Synthetic fixtures are the only
credentials allowed in tests. Never put backend output containing secrets in reports.

## Exit criteria

Selector/copy failure cases pass; fish syntax passes; isolated-home install, repeat
install, rollback and uninstall are proven; concrete host dry-run is reviewable.
TUI navigation, ephemeral display and shared CLI/installer integration pass.

Phase review includes a gap analysis and checks that docs, implementation, and status agree.
A green agent doctor proves guidance consistency only, not host or migration readiness.
Version, tag, and release preparation may be recorded, but commits and publication require
an explicit separate request; no phase ceremony grants that authorization.

## Failure, rollback, and stop

Use the manifest and per-file hashes to restore owned changes; refuse modified or unowned files. Never remove user packages, password stores, vaults, or colliding shell functions.

Leave blocked work unchecked. Record what was observed and the smallest safe continuation.
Do not infer completion from installed tools, generated codes, or aggregate counts alone.

## Scheduling

Sprint estimates represent active effort; human authorization, service procedures, and
recovery waits determine elapsed time. There are no automatic calendar deadlines.

## Completion evidence

All three sprints passed the [verification report](../docs/reports/2026-10-12-phase-2-verification.md).
The concrete home installation was separately approved and verified without backend
access. Human disposable acceptance remains before the Phase 3 pilot.
