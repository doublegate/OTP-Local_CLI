# Private migration ledger template

This is a blank schema and checklist, not a live account ledger. Do not fill it
in within this repository. Create the working ledger in a private encrypted
location outside the workspace, its Git history, backups shared with agents and
agent-accessible logs. Do not disclose its populated contents to an agent.

Account names and progress are private metadata even when no seed is present.
The live ledger must never contain seeds, passwords, OTPs, QR images, plaintext
exports, recovery-code values or vault contents. Record the location of protected
recovery material without copying its contents; protect that location metadata.

## Private ledger fields

Copy this table privately. Leave cells blank until a human supplies local facts.

| Field | Value |
| --- | --- |
| Private service/account reference | |
| State: inventory / recovery-ready / pilot / verified / exception / retired | |
| Owner and verification date | |
| Intended 1Password account/vault/item references | |
| MFA type and supported migration route | |
| Recovery method and protected external location reference | |
| Independent recovery access verified date | |
| Previous enrollment validity: current / rotated / unknown | |
| New enrollment confirmed date | |
| Fresh-login verification date | |
| Next-window verification date, if applicable | |
| Mobile/browser/CLI paths actually checked | |
| Authy retirement approval and date | |
| Exception, next action and review date | |

Missing evidence stays blank or pending. Do not infer that an old Authy entry
remains usable after a service rotates its seed. Unknown or proprietary MFA
flows remain exceptions until their service-specific recovery path is verified.

## Independent recovery checklist

- [ ] Recovery access exists independently of the authenticator being replaced.
- [ ] Necessary account credentials and protected recovery material are reachable.
- [ ] A locked, lost or unavailable desktop does not remove all recovery access.
- [ ] The planned pilot preserves the current authenticated session until a fresh
  login succeeds; no last session is deliberately destroyed.
- [ ] Service-specific MFA recovery instructions have been checked for the pilot.
- [ ] Rotation consequences are understood; an invalid old seed is not a rollback.
- [ ] Recovery evidence was recorded privately without copying protected values.

Actual use of recovery codes can consume them or alter account state. This
preflight checklist does not authorize that action; plan any recovery drill
separately before executing it.

## Host and authorization attestations

| Gate | Status: pending / pass / fail | Date |
| --- | --- | --- |
| Current synchronized host clock | | |
| Desktop system-authentication unlock | | |
| Intended terminal CLI approval witnessed | | |
| Intended account and vault selected privately | | |
| Independent recovery access confirmed | | |
| Live synthetic-item companion check, when implemented | | |

Use [the dated readiness procedure](../operations/2026-10-12-phase-0-readiness.md) for the unlock
and approval checks. No real OTP should be requested through this conversation.
Only aggregate counts and dated pass/fail/pending attestations may return to
[project status](../../PROJECT-STATUS.md). Omit live account references and reasons
that could identify a service or disclose protected recovery information.

## Migration stop conditions

Stop before enrollment changes when recovery is uncertain, clock readiness is
unknown, the intended account/vault cannot be confirmed, or required software
gates fail. Stop before retirement when a fresh login fails or any required
access path remains unverified. Keep exceptions visible; do not count them as
completed migrations.
