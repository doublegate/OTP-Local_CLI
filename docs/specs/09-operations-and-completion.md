# Operations and completion

## Normal operations

Use explicit account/vault scope and item IDs. Moving an item between vaults can
change its ID; update the operator's invocation after checking the intended item
in the native UI. Do not recover a missing ID by silently searching every account.

Keep the desktop app, CLI and operating system maintained through the existing
package process. After a relevant upgrade, run offline regression tests, doctor,
then an operator-controlled synthetic-item smoke test. Record versions and aggregate
results. Do not schedule OTP generation or store generated codes as health checks.

Review recovery after device replacement, account-security changes and optional
store changes. Check that mobile/browser access and an independent recovery path
remain available. Offline availability is a human-tested property of a particular
device/session, not an assumed vendor guarantee.

## Incident playbook

| Incident | Response |
|---|---|
| Helper regression | Use native app; roll back verified helper release; retain enrollment |
| Desktop/CLI locked or unavailable | Use another verified factor/device; diagnose authentication separately |
| Lost workstation | Revoke relevant sessions from a trusted device; recover through verified independent access |
| Suspected seed/recovery exposure | Rotate affected factor and recovery material through official service UI |
| Optional-store loss | Use independent factor; restore only through tested backend procedure |
| Uncertain clipboard history | Treat copied code as exposed for its validity window; investigate local history policy |

Do not claim that deleting a file or clearing a clipboard reverses disclosure.
If underlying source seeds were exposed, expiry of one generated code does not
remediate the seed. Never send private diagnostic payloads to remote reviewers.

## Evidence model

`PROJECT-STATUS.md` owns progress. Per-sprint plans contain acceptance criteria;
completion reports contain date, revision or artifact hashes, tool versions,
commands, result counts, failures and skipped checks. Store scratch reports under
`/tmp/Authy-to-1Password_Local/`; promote sanitized durable summaries only.

Private operator evidence includes account-specific verification and recovery
results. The repo receives only aggregate counts and unresolved categories. No
screenshots, OTPs, QR images, item names or exported vault metadata.

## Final acceptance matrix

| Gate | Evidence | Requirements |
|---|---|---|
| Design | Specs, ADR disposition, task/requirement traceability, valid links | R-01, R-11, R-14 |
| Software | Format/lint/tests, failure matrix, allowed-command review | R-02–R-08, R-13 |
| Installed helper | Manifest/rollback test and human synthetic desktop check | R-02–R-08 |
| Pilot | Fresh login, access checks and independent recovery | R-09, R-12 |
| Migration | Private ledger reconciles; every account has a disposition | R-09, R-10, R-14 |
| Optional stores | Adopted with recovery evidence or explicitly skipped | R-11 |
| Closure | Exceptions disclosed, recovery checked, retirement decision recorded | R-10, R-12 |

No software gate is satisfied merely by writing this document. A skipped optional
branch is acceptable; a skipped mandatory verification remains a blocker.

## Release and retirement

For the first local helper release, select a SemVer version only after implementation
and acceptance. Update the changelog, README support statements and status together.
Do not publish, tag, commit or create a remote without explicit authorization.
Packaging must remain reproducible from documented pinned inputs.

Retirement is a distinct human action. Verify every Authy-dependent account before
removing entries, devices or the Authy account. If an exception still needs Authy,
close the software milestone and report migration/retirement as partial. Do not
hide a proprietary integration by reducing the inventory count.

Completion report must state separately: design status, software status, migration
counts, optional-backend decisions, recovery coverage, retirement status and known
limitations. Retain the immutable reference and sanitized implementation evidence.
