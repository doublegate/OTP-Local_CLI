# Phase 3 private operator checkpoints — 2026-10-12

Status: Checkpoints A and B passed on operator attestation, 2026-10-12. Private
pilot ledger confirmation and batch migration outcomes remain pending. [Project status](../../PROJECT-STATUS.md) records observed progress.
Mocks, successful builds and this checklist cannot complete Phase 3.

Use the [migration procedure](../specs/07-migration-and-recovery.md) and keep detailed
evidence in an external encrypted ledger following the
[blank private ledger](../templates/private-ledger-template.md). Do not populate that template
inside the repository. The agent must not receive identities, service names,
scope IDs, OTPs, seeds, QR images, recovery material or security-page output.

## Checkpoint A: installation and disposable acceptance

First pass all offline software gates. Review the installer's concrete paths,
hashes, conflicts and rollback footprint, then explicitly authorize that reviewed
host installation before apply. Installation approval does not authorize account
changes. See [installation](../specs/06-installation-and-instantiation.md).

Privately perform the following in a new fish terminal:

1. Check the installed release and wrapper resolution; confirm the expected
   `otp1p`, `otp1pc` and `otp1pf` functions, with no unexpected aliases or functions.
2. Confirm desktop unlock, intended CLI approval, synchronized clock and intended
   account/vault scope. Prior readiness is dated evidence, not a permanent guarantee.
3. Create a disposable synthetic Login item through the native 1Password UI using
   non-production TOTP material. Keep even this item and its locators out of agent
   tools. Follow the [native OTP guide](https://support.1password.com/one-time-passwords/).
4. Run installed `show` with explicit item/account/vault IDs privately. Verify the
   accepted account-ID shape and compare output against the native UI in the same
   time window; repeat in a later window. A synthetic unit test cannot establish
   compatibility with this installed CLI configuration.
5. Run scoped selection privately, confirm the intended item, then cancel a second
   selection. Cancellation must not retrieve a code or modify the clipboard.
6. Explicitly run copy and selection-with-copy. Paste only into a trusted private
   destination and compare privately. Confirm no OTP appears on command stdout.
   Inspect local clipboard-manager behavior privately; normal copy does not promise
   paste-once, history erasure or automatic clearing.
7. Check wrapper success and cancellation exit propagation. Remove the disposable
   item only through a separately deliberate native UI action if desired.
8. Open `otp-local tui` privately. Repeat doctor, hidden scope entry, show, copy,
   selection and cancellation with the disposable item. Confirm code dismissal
   erases its display, preview does not write, and the migration guide performs
   no account actions. Exit and verify the terminal is usable normally.

If any check fails, stop before real accounts. Report only the failed stage,
static exit class and non-secret software versions. Do not paste provider output.
Record pass/fail/pending for each check, date and versions privately; return only
aggregate pass/fail to the project. The
[CLI integration guide](https://www.1password.dev/cli/app-integration) explains
native desktop authorization; do not alter authentication services as a repair.

### Recorded Checkpoint A evidence

The operator confirmed all installed CLI/TUI/fish synthetic checks passed after
the encoding repair. Terminal restoration and unchanged installation preview were
also reported. Versions: companion 0.1.0.dev0, op 2.39.0, fish 4.9.3, fzf 0.74.5,
wl-clipboard 2.3.0. This is human-attested disposable acceptance; no real-account
migration or independent agent verification of private checks is claimed.

After the terminal-session repair, the operator repeated TUI Show twice in the
same terminal. Both requests succeeded and the second required no GUI approval.
This confirms authorization reuse for the tested path on operator attestation;
authorization expiry and app locking were not separately retested.

## Checkpoint B: one-account pilot

Choose exactly one low-impact ordinary TOTP account privately. Before action,
record the concrete account and intended enrollment change in the private ledger
and authorize that scope locally. Tell the agent only that the opaque pilot batch
label has one authorized account; the label must not encode an identity or service.

Verify independent recovery access, account credentials, a retained authenticated
session and the provider's current official enrollment/recovery instructions.
The general runbook supplies no substitute for provider-specific instructions.
Do not proceed with unknown recovery or unsupported proprietary conversion.

Perform the [one-account transaction](../specs/07-migration-and-recovery.md) manually.
Enrollment must succeed, a separate fresh login must pass, required desktop,
mobile, browser and scoped terminal paths must work, and independent recovery
must remain accessible afterward. Record dated evidence privately for each gate.
Code generation alone is insufficient. An alternate recovery method must remain
usable; do not consume the last recovery option as a test.

Reconcile the pilot outcome before authorizing another batch. Authy entry deletion
is a separate per-account gate after all verification. Seed rotation may invalidate
the old Authy enrollment immediately; merely retaining its entry is not rollback.

### Recorded Checkpoint B evidence

Operator report for pilot-001, 2026-10-12: concrete scope authorized privately;
independent recovery before change, enrollment, fresh login, desktop/mobile/browser/
CLI access and post-change recovery all passed. No stop condition encountered.
Pilot total 1; migrated 1; blocked 0; pending 0. This is operator-attested evidence.
Dated external ledger recording still requires confirmation. Full inventory totals
and Authy dependency are unknown; no retirement is authorized by this report.

## Checkpoint C: bounded batches

After a passed pilot, classify the entire private inventory and authorize each
batch separately. Use at most three accounts per batch; handle high-impact accounts
individually. Keep actual scope and per-account authorization private. Use an
opaque batch label for conversation and report only counts.

For every account, repeat recovery verification, current official procedure,
enrollment, fresh login, required access-path checks and post-change recovery
confirmation. Stop and reconcile after each batch. Preserve required Authy access
for proprietary or unresolved services; never force an unsupported conversion.

Stop immediately on failed login, missing recovery, ambiguous scope, uncertain
clock, unexpected prompt or exposure. Preserve the working session, use the
preverified independent recovery route, and pause subsequent accounts. Do not
retry challenges blindly or rotate again as a default CLI repair. An incident
remains blocked or pending in aggregate accounting until resolved; keep incident
details exclusively in the private ledger.

## Aggregate reconciliation and completion

Use the [blank batch report](../templates/migration-batch-template.md) after every checkpoint.
Each unique inventoried account has exactly one current disposition:

| Disposition | Required interpretation |
| --- | --- |
| Migrated | Enrollment, fresh login, required access paths and independent recovery all have dated private evidence |
| Blocked | A required gate failed or cannot safely be met; retain private next action and review date |
| Retained | Deliberate documented decision to keep the current method, including required Authy dependence |
| Excluded | Explicitly outside the agreed migration scope with private rationale |
| Pending | No final disposition yet, including incomplete verification |

Reconcile `total = migrated + blocked + retained + excluded + pending` after
deduplicating the private inventory. Report cumulative totals separately from
the current batch counts; their denominators differ. Authy-dependent is a separate
overlapping count, not an additional disposition. Never count retained, excluded
or blocked accounts as successful migrations.

Phase 3 can close only after disposable acceptance and the pilot pass, every
inventory entry has a final disposition, pending is zero, totals reconcile and
every migrated account has its own dated fresh-login and recovery evidence.
Blocked/retained/excluded exceptions require a deliberate private disposition
and aggregate acknowledgment; completion of accounting does not imply complete
migration or zero Authy dependency. Report actual migrated coverage and exceptions.

The operator attests these results; the agent cannot independently establish them
from counts. Keep Phase 3 unchecked while any required evidence is missing.
Authy application/device/account retirement requires a separate final decision
after all dependent accounts reconcile, as described in
[operations and completion](../specs/09-operations-and-completion.md).
