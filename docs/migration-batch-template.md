# Blank aggregate migration batch report

This is an unpopulated schema. Keep per-account records in the external private
ledger. Report counts and pass/fail/pending only; omit identities, services,
scope IDs, codes, recovery details and provider output. An opaque batch label
must not encode private metadata. See the
[operator checkpoints](2026-10-12-phase-3-operator-checkpoints.md).

## Checkpoint attestations

| Field | Blank value |
| --- | --- |
| Date | |
| Opaque batch label | |
| Kind: synthetic / pilot / batch / final reconciliation | |
| Concrete scope authorized privately: pass / fail / pending | |
| Installed software and wrapper acceptance: pass / fail / pending | |
| Disposable synthetic compatibility: pass / fail / pending | |
| Independent recovery before changes: pass / fail / pending | |
| Every migrated account has fresh-login evidence: pass / fail / pending | |
| Every migrated account has required access-path evidence: pass / fail / pending | |
| Every migrated account has post-change recovery evidence: pass / fail / pending | |
| Stop condition encountered: yes / no | |
| Continue gate: pass / fail / pending | |

A synthetic checkpoint covers zero real accounts. Do not count its item as an
inventoried account or successful migration. For a failed batch, mark the continue
gate fail and stop; a partially migrated batch is not a passed batch.

## Current batch dispositions

Record the current disposition of each account in the authorized batch exactly
once. Ordinary batches contain at most three accounts; high-impact batches and
the pilot contain one. Fields below contain nonnegative integers only.

| Count | Blank value |
| --- | --- |
| Batch total | |
| Migrated | |
| Blocked | |
| Retained | |
| Excluded | |
| Pending | |

Require `batch total = migrated + blocked + retained + excluded + pending`.
These are batch outcomes, not additions to cumulative totals: an account reported
in a previous checkpoint must not be counted twice.

## Cumulative inventory reconciliation

| Count | Blank value |
| --- | --- |
| Unique inventory total | |
| Migrated | |
| Blocked | |
| Retained | |
| Excluded | |
| Pending | |
| Still Authy-dependent, overlapping the dispositions above | |

Require `inventory total = migrated + blocked + retained + excluded + pending`.
Authy-dependent must be between zero and inventory total; never add it to the
disposition sum. Before final closure, pending must be zero and every exception
must have a deliberate private disposition, next action or review decision.

Keep exception reasons private. An aggregate count does not authorize deletion,
application retirement or a new batch. Each next concrete scope is authorized
privately before action. Record only non-secret aggregate evidence in project
status after the operator supplies it.
