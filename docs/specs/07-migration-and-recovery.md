# Migration and recovery procedure

Status: operator procedure for future authorized account changes. Keep all service
identities, recovery material and detailed evidence in the private ledger described
in [security and data](04-security-and-data.md).

## Account state machine

`discovered → classified → recovery-ready → enrolled → login-verified → reconciled`

An account may instead become `blocked`, `excluded` or `incident`. Record the
reason and next action privately. An exclusion is never counted as migrated.
The repo records aggregate counts only, including any accounts requiring Authy.

## Classification and preparation

Determine whether the service supports ordinary TOTP re-enrollment, proprietary
Authy approval, SMS/voice-only authentication, or a stronger supported method.
Use that service's current official instructions at execution time; the general
runbook cannot prescribe every provider's enrollment or recovery behavior.

Before changing MFA, verify an independent recovery path: usable recovery codes,
an alternate enrolled factor, or a tested provider recovery process. Merely having
a file named recovery-codes is insufficient. Preserve the current authenticated
session and confirm the account password is accessible independently of Authy.
Do not consume the last recovery option as a test without replacing it.

Choose one low-impact ordinary TOTP account for the pilot. Establish a stopping
point before starting, including how to regain access if enrollment fails.

## One-account transaction

1. Open the official account security settings in a trusted browser session.
2. Verify recovery and review any service-specific disable/re-enable consequences.
3. Enroll 1Password through its native QR/manual flow. No agent screenshots,
   terminal seed arguments, saved QR images or plaintext exports.
4. Complete the provider's enrollment challenge using the new factor.
5. In a separate fresh login session, verify password plus the new factor. Preserve
   the original session until this succeeds; avoid destroying the last working path.
6. Check native desktop/mobile access and operator-run CLI access when required.
   A later time window can distinguish generation from a stale copied code.
7. Confirm recovery remains usable after the change; replace consumed codes.
8. Reconcile the private ledger. Only then consider removing the obsolete Authy entry.

Keep old entries until verification, but do not rely on them for rollback: when a
provider rotates its seed, the previous Authy code may become invalid immediately.
Recovery means an independent factor/session or provider recovery, not an assumed
working copy of the old seed.

## Failure handling

| Failure | Safe response |
|---|---|
| New enrollment rejected | Remain in current session; check official format/time requirements; do not repeat blindly |
| Fresh login fails | Keep original session; use alternate factor/recovery; classify blocked |
| CLI fails but UI works | Preserve enrollment; diagnose helper scope/auth separately; no seed rotation as default repair |
| Clipboard uncertain | Use native UI or explicit terminal display; do not infer history was cleared |
| Clock uncertain | Verify host synchronization before further challenges; avoid lockout retries |
| Proprietary Authy integration | Retain required Authy access; document exception or provider-supported replacement |
| Suspected seed exposure | Use a trusted device/session to rotate the factor and regenerate recovery material |

Never paste backend errors or account security pages into project evidence.
Summarize errors by stage, exit class and versions without account names.

## Batches and checkpointing

After the pilot, group small batches by recovery risk and stop after each batch to
reconcile counts. High-value accounts require independent recovery verification
and deliberate scheduling. No unattended bulk enrollment or automatic deletion.

Private ledger invariants: each discovered account has exactly one current state;
verified + blocked + excluded + pending equals total in scope. Reconcile duplicates
and renamed entries before declaring completion. Counts must not hide exceptions.

## Retirement gate

Retire an Authy entry only after successful fresh login, required access-path
checks and recovery confirmation. Retiring the Authy application/device/account
requires a separate final decision after all dependent services are reconciled.
Retain Authy if any proprietary or unresolved account still needs it; report partial
retirement. Do not remove backup devices or revoke sessions as a cleanup shortcut.

For ongoing operations and final evidence, see [completion](09-operations-and-completion.md).
