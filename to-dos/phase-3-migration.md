# Phase 3: Human-operated migration

Status: Checkpoints A/B passed; awaiting pilot ledger confirmation and migration batches. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Validate one pilot, then migrate supported accounts in bounded risk-ordered batches.

## Entry conditions and dependencies

Phases 0–2 complete; concrete human account/batch authorization and independent recovery required.
The reviewed helper must be installed under separate authorization and pass the
human synthetic-item acceptance check before the real-account pilot begins.
This plan authorizes no execution by itself. Planning does not authorize host installation,
secret access, service MFA changes, commits, or publication.

## Sprint sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-3.1](sprints/3.1.md) | Human-operated pilot | See sprint entry gate |
| [S-AUTH-3.2](sprints/3.2.md) | Staged migration and exceptions | See sprint entry gate |

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

Every privately inventoried account has a documented migrated, blocked, or retained disposition; every migrated account has fresh-login and recovery evidence.

Phase review includes a gap analysis and checks that docs, implementation, and status agree.
A green agent doctor proves guidance consistency only, not host or migration readiness.
Version, tag, and release preparation may be recorded, but commits and publication require
an explicit separate request; no phase ceremony grants that authorization.

## Failure, rollback, and stop

Stop batches immediately on access failure. Old Authy entries may contain invalidated seeds after rotation; recover with preverified independent methods rather than assuming Authy rollback.

Leave blocked work unchecked. Record what was observed and the smallest safe continuation.
Do not infer completion from installed tools, generated codes, or aggregate counts alone.

## Scheduling

Sprint estimates represent active effort; human authorization, service procedures, and
recovery waits determine elapsed time. There are no automatic calendar deadlines.

## Current checkpoint

The [Phase 2 report](../docs/reports/2026-10-12-phase-2-verification.md) records completed
software gates and approved home installation. Follow the
[private operator checkpoints](../docs/operations/2026-10-12-phase-3-operator-checkpoints.md)
and [aggregate template](../docs/templates/migration-batch-template.md). Pilot tasks T-AUTH-034–036 are complete on operator attestation. Private ledger
confirmation (T-AUTH-037) and all batch tasks remain pending.
