# Phase 1 implementation boundary — 2026-10-12

This note records the implemented design, not a declaration that all operational
gates have passed. [Project status](../../PROJECT-STATUS.md) is authoritative for
completion, measured test results and remaining later-phase acceptance checks.

## Implemented behavior

The Python 3.14 standard-library package provides `otp-local doctor [--json]`,
`show ITEM_ID --account ACCOUNT_ID --vault VAULT_ID [--allow-pipe]`, help and
version. It has no third-party runtime dependencies and no TOTP algorithm.
It delegates OTP generation to the installed 1Password CLI.

Doctor checks Linux/Python support, bounded CLI version output, optional tool
presence and synchronized-clock state. It never authenticates or enumerates
accounts/items. A missing session bus produces an unknown clock, not a fabricated
host failure. Authentication is always reported unknown.

Show validates all three IDs as exactly 26 ASCII alphanumeric characters before
launch. Account addresses/shorthands are deliberately unsupported. A controlling
terminal and interactive stdin are required; non-terminal stdout additionally
requires `--allow-pipe`. This reduces mistakes and does not restrict an agent
capable of allocating a PTY. Agents must not retrieve real codes.

The adapter resolves `op` once for its version check and uses the returned path
for the fixed scoped OTP request. It accepts bounded `2.MINOR.PATCH` versions
with MINOR at least 39; 2.39.0 is the observed baseline. Live compatibility of
newer accepted versions remains a human/provider acceptance gate.

Retrieval uses `--otp`, explicit account/vault scope, human-readable output,
no color, cache disabled, UTF-8 encoding and debug disabled. Child environments
strip inherited `OP_*` settings and enable desktop integration explicitly.
Service/Connect/session authentication override names block retrieval.

## Failure and disclosure controls

- Subprocesses launch through argv lists, without a shell or inherited stdin.
- Streaming caps bound both pipes; stderr is counted and immediately discarded.
- Monotonic deadlines and owned process-group cleanup handle timeout, overflow
  and cancellation without killing unrelated processes.
- Backend success is checked before accepting six/eight ASCII digits; leading
  zeros are preserved and one output newline is emitted only after validation.
- Usage and backend errors use static diagnostics. Raw arguments, vendor stderr
  and tracebacks do not appear in normal failure output.
- There is no automatic retry, persistence, account mutation or clipboard write.

The [CLI specification](../specs/03-cli-specification.md) contains the exact resource
limits and exit codes. Python strings cannot promise secure memory erasure;
same-user malware, root and vendor-local state remain outside this boundary.

## Developer validation

Pinned tools and a project virtual environment support an editable developer
installation. The [development guide](../specs/05-development-and-testing.md) defines the
repeatable aggregate gate: synthetic unit/subprocess tests, branch coverage,
Ruff lint/format, ShellCheck, Markdown lint, link/task/checksum checks and builds.
Tests select fake executables explicitly and cannot fall through to live `op`.

The coverage floor is 90% aggregate; scope/code validation and the adapter have
a 100% scoped gate plus semantic boundary tests. Counts and final measured coverage
belong in the completion report after independent verification, not this note.

## Deferred and unresolved

Phase 2 supplies clipboard, scoped selection, fish wrappers, home installation,
upgrade and uninstall. Current parsing rejects those unimplemented commands.
Optional stores and service migration remain later phases.

The operator attested that desktop unlock, scoped CLI approval, a private ledger
location and the independent-recovery checklist were ready on 2026-10-12. A
human-controlled synthetic item must still establish live account-selector format
and companion/provider compatibility before real use. Offline fake-tool success
proves local behavior; the readiness checks rely on the operator's attestation.

No real-account code, seed, credential or inventory was used for implementation.
No home helper installation, account migration, commit or remote publication is
part of this Phase 1 developer build.
