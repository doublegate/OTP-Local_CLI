# Phase 5: Recovery, hardening, and completion

Status: software candidate installed and hardening verified; private closure pending.
Authy remains retained. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Close delivery with recovery evidence, quality checks, and conditional Authy retirement.

## Entry conditions and dependencies

Migration coverage reconciled; Phase 4 completed or explicitly skipped.
This plan authorizes no execution by itself. Planning does not authorize host installation,
secret access, service MFA changes, commits, or publication.

## Sprint sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-5.1](sprints/5.1.md) | Recovery drill and hardening | See sprint entry gate |
| [S-AUTH-5.2](sprints/5.2.md) | Completion and conditional Authy retirement | See sprint entry gate |

Software validation and candidate preparation proceed under the implementation
request; operational closure still requires the dependencies to pass.
All four tasks in each selected sprint must have explicit evidence before closing it.

## Deliverables and evidence

- Sprint outputs and their requirement/acceptance references.
- Current aggregate progress in [PROJECT-STATUS.md](../PROJECT-STATUS.md).
- Test/validation report identifying passed, failed, skipped, and unknown checks.
- Explicit blocker and exception dispositions, without account identities or secrets.

Private per-account evidence stays outside the workspace. Synthetic fixtures are the only
credentials allowed in tests. Never put backend output containing secrets in reports.

## Exit criteria

Base implementation and supported-account outcomes are evidenced; recovery and hardening limits recorded; full Authy retirement declared only with zero unresolved dependency and explicit retirement authorization.

Phase review includes a gap analysis and checks that docs, implementation, and status agree.
A green agent doctor proves guidance consistency only, not host or migration readiness.
Version, tag, and release preparation may be recorded, but commits and publication require
an explicit separate request; no phase ceremony grants that authorization.

## Failure, rollback, and stop

Preserve known-working access and installation rollback inputs. Halt retirement on any exception; retained proprietary Authy use remains an explicit supported exception, not hidden completion.

Leave blocked work unchecked. Record what was observed and the smallest safe continuation.
Do not infer completion from installed tools, generated codes, or aggregate counts alone.

## Scheduling

Sprint estimates represent active effort; human authorization, service procedures, and
recovery waits determine elapsed time. There are no automatic calendar deadlines.
