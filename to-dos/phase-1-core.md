# Phase 1: Core helper implementation

Status: complete, 2026-10-12. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Build a small Python stdlib retrieval boundary with reproducible synthetic tests.

## Entry conditions and dependencies

S-AUTH-0.1; live installation additionally requires S-AUTH-0.2.
This plan authorizes no execution by itself. Planning does not authorize host installation,
secret access, service MFA changes, commits, or publication.

## Sprint sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-1.1](sprints/1.1.md) | Synthetic harness and doctor | See sprint entry gate |
| [S-AUTH-1.2](sprints/1.2.md) | OTP retrieval and safe errors | See sprint entry gate |

Run the second sprint only after its dependencies pass; Phase 4 alternatives may be
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

doctor and show pass their bounded subprocess, explicit-scoping, output, and sanitized-error contracts with fake tools.

Phase review includes a gap analysis and checks that docs, implementation, and status agree.
A green agent doctor proves guidance consistency only, not host or migration readiness.
Version, tag, and release preparation may be recorded, but commits and publication require
an explicit separate request; no phase ceremony grants that authorization.

## Failure, rollback, and stop

Keep changes local and source-only until tests pass; do not use real vault output to diagnose failures. Revert only session changes with preserved snapshots when needed.

Leave blocked work unchecked. Record what was observed and the smallest safe continuation.
Do not infer completion from installed tools, generated codes, or aggregate counts alone.

## Scheduling

Sprint estimates represent active effort; human authorization, service procedures, and
recovery waits determine elapsed time. There are no automatic calendar deadlines.

## Completion evidence

Both sprints complete within synthetic-software scope. Live companion
compatibility and home installation remain later-phase gates.
See the [verification report](../docs/reports/2026-10-12-phase-0-1-verification.md).
