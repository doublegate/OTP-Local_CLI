# Phase 4: Optional independent backends

Status: both backends selected and implemented; private acceptance pending.
See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Select pass-otp or totpm only where their distinct resilience or machine-binding benefits justify added ownership.

The operator selected both capabilities, a dedicated GPG key and totpm local mode.
Only a privately selected subset is duplicated after recovery acceptance. See
[the decision](../docs/adr/0005-explicit-local-backends.md) and
[remaining private checkpoints](../docs/2026-10-12-phase-4-5-operator-checkpoints.md).

## Entry conditions and dependencies

Pilot complete; each backend needs a documented need and separate installation/enrollment authorization.
This plan authorizes no execution by itself. Planning does not authorize host installation,
secret access, service MFA changes, commits, or publication.

## Sprint sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-4.1](sprints/4.1.md) | Optional pass-otp fallback | See sprint entry gate |
| [S-AUTH-4.2](sprints/4.2.md) | Optional TPM-backed fallback | See sprint entry gate |

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

Each optional sprint is either explicitly skipped with rationale or validated with synthetic functional and independent recovery evidence. No optional backend gates base delivery.

Phase review includes a gap analysis and checks that docs, implementation, and status agree.
A green agent doctor proves guidance consistency only, not host or migration readiness.
Version, tag, and release preparation may be recorded, but commits and publication require
an explicit separate request; no phase ceremony grants that authorization.

## Failure, rollback, and stop

Preserve independent service recovery before adoption. Remove only explicitly owned helper artifacts; encrypted stores and TPM secrets require separate disposition authorization.

Leave blocked work unchecked. Record what was observed and the smallest safe continuation.
Do not infer completion from installed tools, generated codes, or aggregate counts alone.

## Scheduling

Sprint estimates represent active effort; human authorization, service procedures, and
recovery waits determine elapsed time. There are no automatic calendar deadlines.
