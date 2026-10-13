# CLI and adapter contract

The package implements `doctor`, `show`, `copy`, `select`, `enroll`, `guide`, help and version.
The cohesive curses interface is specified in [TUI](11-tui.md). Operational
installation and live acceptance are tracked separately in project status.

The TUI can save operator-configured backend scope in its private resident
profiles and browse scoped metadata with curses. This does not change CLI
`show`, `copy` or `select`: their scope flags remain explicit and TUI profiles
are never implicit CLI defaults. See [resident scope and browsing](11-tui.md).
The TUI also supports explicitly confirmed deletion of a single selected local
pass-otp or totpm entry. There is no public CLI `delete` command and no 1Password
deletion capability; see [local deletion](11-tui.md#confirmed-local-entry-deletion).
TPM-backed deletion uses an exact transactional database operation rather than
the native substring-matching delete command. It requires the pinned totpm 0.1.2
SQLite schema version 1, local presence verification `none`, and validated private
absolute configuration, user-data and database paths. It uses `BEGIN IMMEDIATE`
and exact `BINARY` service/account matching, requires exactly one affected row,
and rejects unknown schema, triggers and views. It never reads decrypted seeds
or performs a TPM operation.

## Public commands

```text
otp-local doctor [--json] [--install|--fix]
otp-local show ITEM_ID --account ACCOUNT_ID --vault VAULT_ID [--allow-pipe]
otp-local tui
otp-local --version
```

Additional commands:

```text
otp-local copy ITEM_ID --account ACCOUNT_ID --vault VAULT_ID
otp-local select --account ACCOUNT_ID --vault VAULT_ID [--copy]
otp-local unlock [--account ACCOUNT]
otp-local enroll [--apply] [--title ...] [--digits ...] [--period ...]
otp-local pick [--launcher auto|wofi|rofi|fzf] [--no-notify] [--stdout]
otp-local import SOURCE [--format auto|aegis|bitwarden|google-migration|uri-list] [--dry-run] [--apply]
otp-local export [--format uri|aegis|csv] [--output PATH] [--encrypt-gpg KEY_ID]
otp-local audit [--json]
otp-local qr ITEM_ID [--allow-pipe]
otp-local agent {status,start,stop,lock} [--timeout SECONDS]
otp-local guide {optional,setup,acceptance,migration,recovery,tui}
```

`show`, `copy`, `select`, `enroll`, `pick`, `import`, `export`, `audit`, and `qr` accept explicit
`--backend onepassword|pass-otp|totpm|yubikey|tpm2-totp|keychain`; 1Password is the default.
`unlock` interactively authenticates or unlocks the 1Password session without command-line secret exposure.
Local scope flags and hidden enrollment with explicit `--apply` are defined in
[optional backends](08-optional-backends.md). Mixed scope flags fail closed. `guide` reads bundled
public Markdown without a checkout or authentication. It does not update a private ledger or assert readiness.

`doctor` and help/version never authenticate. Doctor returns presence, version and
capability states `available`, `missing`, `unknown`, `not-applicable`; unknown clock/session checks
must remain unknown. `--json` is available only for this non-secret report.
Current doctor probes Python/OS platform support (Linux, macOS Darwin), the `op` version, optional tool
presence, Apple Secure Enclave & macOS Keychain, and clock synchronization. Authentication always remains `unknown`.
On macOS Darwin, Linux PC TPM 2.0 components are categorized as `not-applicable`.
`--install` or `--fix` automatically invokes Homebrew package management on macOS for missing capabilities.
Missing optional tools and unknown clock do not alone fail it; unsupported core
capabilities or an observed unsynchronized clock return 3.

`show` emits one ASCII decimal code and one newline. Standard baseline accepts six
or eight digits, preserving leading zeros. Other formats require a documented
service compatibility decision, not a relaxed catch-all parser. It requires a
controlling terminal and interactive stdin; non-terminal stdout additionally needs
`--allow-pipe`. This is an accident guard, not a privilege boundary against an agent
able to allocate a PTY. Operator policy prohibits real retrieval in agent tools.

`copy` and `select` require a controlling terminal; copy also requires a usable
Wayland session. Successful copy emits no stdout; a generic notice may use stderr.
Selection defaults to show; `--copy` selects the clipboard sink. Unknown flags,
unexpected positional arguments and missing scope fail before any backend call.

## Inputs and backend calls

All three scope IDs currently require exactly 26 ASCII alphanumeric characters.
This conservative account policy excludes shorthands and addresses accepted by
the underlying vendor CLI. Verify the intended account ID in the human synthetic
pilot; account-format uncertainty blocks live use. Empty, option-like, control,
non-ASCII and other malformed values fail before any backend invocation.

Launch with an argv list, `shell=False`, no eval and no caller-supplied op flags.
Resolve required executables through PATH and report only their non-secret paths
in doctor; do not silently prefer a second installation after a failure.

```text
op item get ITEM_ID --account ACCOUNT_ID --vault VAULT_ID --otp
  --format human-readable --no-color --cache=false --debug=false
```

Metadata call for selection:

```text
op item list --account ACCOUNT_ID --vault VAULT_ID --categories Login
  --format json --no-color --cache=false --debug=false
```

TUI browsing appends `--tags TAG` when its saved optional tag filter is nonempty.
The default is `OTP`, including when loading legacy account/vault-only profiles.
Key 8 or p edits the tag; clearing it disables filtering. The vendor matches
nested tags too. CLI `select` keeps the unfiltered command above and does not
read TUI profiles. Tags are operator-maintained metadata, not verified OTP-field
presence; no full-item or bulk OTP reads are introduced.

Use the CLI's UTF-8 default; CLI 2.39.0 rejects explicit `--encoding UTF-8`.
Inherited `OP_ENCODING` is removed with the other `OP_*` options below.

The installed CLI 2.39.0 help and [official item reference](https://www.1password.dev/cli/reference/management-commands/item)
support these operations. The list response is metadata, not proof of an OTP field.
Never issue `op read`, `get --fields`, unqualified `get`, `--reveal`, create/edit/delete,
or exports. Current version parsing requires `2.MINOR.PATCH`, with 1–4 decimal
digits per component and MINOR at least 39: `2.39 <= version < 3` within that
bounded shape. Version 2.39.0 is the tested local baseline; accepting a newer
2.x version does not independently prove its live compatibility.

Child environment: preserve normal desktop session transport and locale variables,
strip every inherited `OP_*` variable, then set `OP_BIOMETRIC_UNLOCK_ENABLED=true`.
Reject presence of `OP_SERVICE_ACCOUNT_TOKEN`, `OP_CONNECT_TOKEN`, `OP_CONNECT_HOST`,
`OP_SESSION` or any `OP_SESSION_*` before retrieval without printing values.
Version/clock probes also use sanitized children. The parent shell is unchanged.
Desktop integration is the only supported retrieval authentication mode.

## Resource and error contract

| Operation | Deadline | Stdout cap | Stderr cap |
|---|---|---|---|
| op code retrieval | 120 seconds including human prompt | 64 bytes | 64 KiB |
| op metadata listing | 120 seconds | 4 MiB / 5,000 rows | 64 KiB |
| fzf selection | 300 seconds | 128 bytes | 64 KiB |
| wl-copy handoff | 5 seconds | 1 KiB | 64 KiB |
| non-secret version/capability probe | 5 seconds | 8 KiB | 8 KiB |
| fzf help capability probe | 5 seconds | 64 KiB | 8 KiB |

Use streaming reads with caps; `capture_output` followed by truncation does not
bound memory. On cap/deadline/interrupt, terminate the child process group, wait
briefly, then kill remaining owned children. Never kill unrelated processes.
The interactive fzf child stays in the foreground terminal process group so it
can open `/dev/tty`; cleanup terminates that direct child only. No selector execute,
preview, reload or shell hooks are configured. 1Password children preserve the
caller's session and controlling terminal while leading separate process groups
for bounded cleanup. This allows normal desktop authorization reuse; locking or
authorization expiry still requires approval. The vendor additionally imposes
10 minutes of inactivity and a 12-hour hard limit, per account and terminal,
even while the app remains unlocked; see [authorization model](https://www.1password.dev/cli/app-integration-security).
There is no background polling or keepalive to extend authorization.
Other bounded children keep isolated
process-group cleanup. Clipboard handoff discards stdout/stderr to `/dev/null`,
waits at most five seconds for the parent, and preserves successful background
serving. Failed handoff cleans up its owned group; clipboard state cannot be rolled
back or assumed unchanged once handoff has begun.

Exactly one optional trailing LF or CRLF is accepted for a code; spaces, extra
lines, ANSI escapes, URI text, non-ASCII digits and success-with-empty-output fail.
Check process status before trusting stdout. No raw backend stderr reaches users,
logs, tracebacks or test failure snapshots; map failures to static messages.

| Exit | Meaning |
|---|---|
| 0 | Complete requested operation |
| 2 | Usage or invalid input |
| 3 | Missing capability or unsupported environment |
| 4 | Backend unavailable, refused, or no usable OTP; diagnostic intentionally generic |
| 5 | Invalid or oversized backend response |
| 6 | Clipboard or selector failure |
| 7 | Deadline exceeded |
| 130 | Operator interrupted or cancelled selection |

Do not infer a specific authorization failure from unstable English stderr.
Backend-specific nonzero exits normalize to 4; the human can inspect native app
state privately. Preserve cancellation at the CLI boundary, no automatic retry.

## Selector and clipboard

The following fzf contract applies to CLI `select`. TUI actions 4 and 5 use a
native curses metadata browser with the same validated backend scope and bounded
listing contracts. TUI search filters current metadata locally; refresh and code
retrieval require explicit operator actions. Neither interface probes every
listed Login for OTP support. The TUI's optional saved tag filters candidates
through list metadata; it does not verify field presence. Only the selected item
is retrieved, and a Login
without an OTP returns the static backend error.

Validate JSON root/list and required ID/title/vault fields; ignore unrelated metadata.
Reject malformed IDs and unexpected vault scope. Construct display rows with an
internal numeric index, escaped control characters, bounded 160-character title,
and ID suffixes. The visible numeric index also distinguishes colliding labels.
Use tab-delimited rows with a numeric first field
and explicitly configure fzf `--delimiter` and `--accept-nth=1` for index-only
stdout. Verify these flags in the supported fzf release; absence fails the capability
gate. Parse only the chosen index and look it up in memory; never execute or trust
a returned title. Test long Unicode labels against the 128-byte output cap.
Disable inherited FZF_DEFAULT_OPTS and
FZF_DEFAULT_COMMAND and FZF_DEFAULT_OPTS_FILE in the child so preview/execute or
history options cannot be injected through inherited configuration. No preview.

Clipboard receives a validated code over stdin, never argv or environment. Default
is `wl-copy --type text/plain`; completion means handoff, not history erasure.
An optional paste-once mode may be added only after testing compositor/browser
behavior. No delayed unconditional clearing that could erase a later user copy.
An external clipboard manager may persist the code; see [security](04-security-and-data.md).

## Fish façade

`otp1p` forwards to show; `otp1pc` to copy; `otp1pf` to select. Preserve argument
boundaries and exit status; no pipeline-based retrieval or logging. A generic `otp`
alias is opt-in and collision checked. Do not overwrite an existing function.
