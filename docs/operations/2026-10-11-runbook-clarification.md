# Runbook clarification: 2026-10-11

This supplement records a local consistency review of the
[original v2 runbook](../../ref-docs/Authy-to-1Password-and-Local-CLI-TOTP-Migration-Runbook-v2.md).
The reference is preserved unchanged. This review does not verify upstream product
behavior, package availability, live host state, or successful migration.

## Operating-model precedence

The executive-summary diagram calls `pass-otp` the recommended default, and section
24 puts ordinary accounts in `pass-otp`. Sections 3, 38, and 46 instead prefer
1Password with `op` for ordinary accounts.

For this project, follow the existing AGENTS.md refinement: 1Password is the planned
authoritative store, and CLI access uses that same store. Treat secondary seed
stores as optional. Confirm the choice before implementation or migration.

## Helper examples

The runbook defines `otp` for both 1Password and `pass-otp`. Do not install all
examples together: select one backend or use distinct function names. Clipboard
helpers also need error-path review before adoption; a pipeline must not report
success merely because the clipboard command succeeded after OTP retrieval failed.

Future helper work must use synthetic inputs and cover missing dependencies,
authentication failure, missing OTP fields, cancellation, and output handling.
No helper is implemented or installed by this documentation pass.

## Secret handling and account safety

The project-specific rule against seeds and export passwords in environment
variables overrides the shared core's general environment-variable recommendation.
Avoid transmitting real credentials through tool arguments, model context, terminal
recordings, or logs. Keep operational account records outside the project too.

Runbook commands for package installation, re-enrollment, export, device removal,
and deletion describe candidate procedures. They require current verification and
authorization for the concrete operation before use. Never treat agent setup or a
completed planning checklist as evidence of a working recovery path or migration.

## Review coverage

Master-Claude's dependency, license, code-lint, and fuzz audit tiers do not apply to
the current documentation-only tree. This review covered instruction consistency
and proposed secret-handling workflows. It is not an application security audit or
a release-readiness result.
