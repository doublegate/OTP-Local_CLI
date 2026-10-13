# Delivery roadmap

Status: Software complete and formally released at v1.0.0. All development phases
(0–6) complete; all quality gates verified with 699 passed tests. Progress belongs in
[PROJECT-STATUS.md](PROJECT-STATUS.md); task checkboxes close only when
their evidence exists. [Requirements](docs/01-requirements.md) map acceptance to
sprints. [Plan index](to-dos/README.md) links the complete phase/sprint documents.

## Milestone aliases

Existing IDs are retained: T-AUTH-001 = documentation foundation;
T-AUTH-002 = operational preflight (phase 0); T-AUTH-003 = human pilot (sprint 3.1);
T-AUTH-004 = v1.0.0 final release.
They are milestones, not reused implementation task IDs.

## Delivery sequence

| Sprint | Outcome | Task IDs | Dependency |
|---|---|---|---|
| [0.1](to-dos/sprints/0.1.md) | Design decisions and repository policy | T-AUTH-010–013 | Specification baseline |
| [0.2](to-dos/sprints/0.2.md) | Host and human authentication readiness | T-AUTH-014–017 | 0.1 |
| [1.1](to-dos/sprints/1.1.md) | Fake harness, bounded runner and doctor | T-AUTH-018–021 | 0.1; may proceed while human readiness pending |
| [1.2](to-dos/sprints/1.2.md) | Scoped retrieval and errors | T-AUTH-022–025 | 1.1 |
| [2.1](to-dos/sprints/2.1.md) | Safe selector and clipboard | T-AUTH-026–029 | 1.2 |
| [2.2](to-dos/sprints/2.2.md) | Fish wrappers, reversible installer | T-AUTH-030–033 | 2.1; host readiness for live checks |
| [2.3](to-dos/sprints/2.3.md) | Cohesive curses TUI | T-AUTH-058–061 | 2.1, 2.2; added 2026-10-12 |
| [3.1](to-dos/sprints/3.1.md) | Human pilot | T-AUTH-034–037 | 0.2, 2.3; authorized install + human CLI/TUI synthetic check; pilot authorization |
| [3.2](to-dos/sprints/3.2.md) | Migration batches and exception reconciliation | T-AUTH-038–041 | Successful pilot |
| [4.1](to-dos/sprints/4.1.md) | Optional GPG store adopted or skipped | T-AUTH-042–045 | Baseline proven; explicit need |
| [4.2](to-dos/sprints/4.2.md) | Optional TPM store adopted or skipped | T-AUTH-046–049 | Baseline proven; independent of 4.1 |
| [5.1](to-dos/sprints/5.1.md) | Recovery and hardening acceptance | T-AUTH-050–053 | 3.2; optional dispositions recorded |
| [5.2](to-dos/sprints/5.2.md) | Evidence closure and retirement decision | T-AUTH-054–057 | 5.1 |
| [6.1](to-dos/sprints/6.1.md) | Enrollment engine, QR decoding, and multi-backend persistence | T-AUTH-070–073 | Phase 0–5 |
| [6.2](to-dos/sprints/6.2.md) | Textual TUI AddOtpModal, live TOTP preview, and challenge verification | T-AUTH-074–077 | 6.1 |

No fixed calendar dates are imposed: human recovery and enrollment gates control
the schedule. Phase 4 can be explicitly skipped; its absence does not block the
baseline. Account exceptions can prevent full retirement while software is complete.

## Release gates and stopping points

- Phase 0 ends with decisions/readiness evidence, before actual enrollment.
- Phases 1–2 end with tested local software and reversible installation evidence.
- Phase 3 ends with verified accounts and openly recorded unresolved categories.
- Phase 4 ends with adopted/skipped decisions and evidence for adopted stores.
- Phase 5 ends with the completion matrix and a separate human retirement decision.

Sprint completion requires its deliverables, passing applicable gates and a sanitized
report. Do not check tasks merely because a plan exists. At a failed gate, preserve
working access and stop dependent actions. Release/commit/publication requires
explicit authorization; no automatic deployment or host changes follow from this plan.
