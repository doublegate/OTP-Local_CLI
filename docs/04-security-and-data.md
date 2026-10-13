# Security, data and trust boundaries

## Assets and adversaries

Protect long-lived enrollment seeds, recovery methods, vault authentication,
ephemeral codes, service/account metadata, and operator access continuity.

| Boundary | Attack or accident | Mitigation and residual limit |
|---|---|---|
| Service to native enrollment UI | Phishing QR or wrong account | Operator verifies origin/account; no agent capture |
| Companion to op | Wrong account/default or flag injection | Explicit scope, fixed argv, narrow commands |
| Backend stdout/stderr to terminal | URI, secret, ANSI or traceback leak | Validate full response; static errors; no raw stderr |
| Metadata to fzf | Terminal controls or injected execute/preview options | Escape labels; index mapping; clean fzf child environment |
| Metadata to curses browser | Hostile labels or accidental bulk retrieval | Sanitize bounded labels; index mapping; explicit listing/refresh and selected-item-only OTP retrieval |
| Resident TUI scope to backend | Tampered scope or unintended disclosure | Owned 0600 profile in 0700 directory, validated scope, symlink refusal and static errors |
| Local browser to entry deletion | Wrong entry or accidental loss | Named single-entry confirmation requiring DELETE, validated exact target, pre-deletion audit and cancellation on resize |
| Code to clipboard | History/clipboard reader captures it | Explicit copy only, operator history policy; no secrecy guarantee |
| Project to home functions | Overwrites user work | Dry-run, manifest/hash ownership, backup and conflict refusal |
| Hidden enrollment to native tool | Seed leaks through argv, environment or diagnostics | Human-only repeated hidden input, fixed commands, stdin transport, captured static errors |
| Native extension to oathtool | Unsafe upstream version comparison selects argv transport | Fingerprinted locally hardened extension, stdin-only generation and native regression |
| Disk/backup to recovery | Host or TPM loss | Independent recovery methods and restore drill |

Same-user malware and root can often read process memory, observe UI, or request
codes. Python references cannot guarantee memory zeroization. Full-disk encryption
does not protect an unlocked machine. A duplicate seed improves availability but
does not add a second independent MFA factor.

## Data classes

| Class | Allowed location | Project policy |
|---|---|---|
| Specs, code, synthetic fixtures | Repository | Review and version when authorized |
| Aggregate totals and blockers | PROJECT-STATUS.md | No identifying service/account details |
| Item/account/vault IDs, service mapping | Operator-managed private ledger; account/vault scope also in private TUI profiles | No project files, logs or model context; no persisted item inventory |
| Seeds, QR, recovery codes, passwords | Native secret store or approved independent recovery medium | Never agent tools, argv, env or project artifacts |
| Current code | Process memory then explicit human sink | No log, cache, file or automated transcript |
| Installation ownership metadata | Private application state directory | Paths/hashes only, no account data |
| Resident backend scope | `~/.config/authy-local/tui-profiles.json` | Account/vault IDs, local store paths and optional metadata tag filter only; owned 0600 file in 0700 directory |
| Local deletion intent audit | `~/.local/state/authy-local/deletions.jsonl` | Owned 0600 file; UTC time, UID, backend, action and coarse scope only; no identifying entry data |

No `.env` with real values is created. Seed/password prompts must be operated by
the human outside the agent session. Even a redaction failure in a screenshot is
unacceptable; do not capture enrollment or vault windows during research.

Resident scope is an explicit operator convenience, not a secret store or an
authentication cache. It never contains seeds, OTPs, item titles, selected item
IDs or service inventories. The TUI lists metadata only after an explicit browse
action, and keeps it in session memory without background polling. Profile
errors fail closed; no fallback to another account or backend occurs. Uninstall
preserves this operator configuration, so its cleanup is a separate deliberate
action. Same-user access and terminal capture remain residual risks.

The optional 1Password tag filter defaults to `OTP` and uses only list metadata.
It does not inspect OTP fields, read full items or retrieve codes in bulk.
Operator-maintained tags may omit an OTP item or include an item without an OTP;
they are a browsing convenience rather than an authorization or readiness gate.
Session Status retains the latest explicit Doctor capability check only within
the current TUI session. It does not cache authentication or prove backend access.

## Private operator ledger specification

Use a trusted private store chosen by the operator; do not create its live instance
in this repository. Per-record fields: opaque record ID, service/account label,
token class (standard/proprietary/unknown), risk tier, selected backend(s), private
item locator, recovery availability, enrollment state, verification dates, exception
reason, and retirement authorization/outcome. No seed or current OTP field.

Allowed states and guards are defined in [migration](07-migration-and-recovery.md).
Store verification booleans and timestamps rather than codes or screenshots.
Repository progress contains total discovered, eligible, verified, deferred,
excluded and retired counts only. The operator reconciles totals; the agent need
not inspect the ledger. Recovery material should have failure independence from
the store that it recovers, including the password manager's own MFA.

## Runtime discipline

No debug mode, shell tracing, crash-value serialization or telemetry in the
companion. Exception handlers render a static category and correlation-free local
exit code; do not interpolate external data. Unit tests deliberately inject
secret-shaped sentinels and assert absence from logs and failure output.

Use a private non-synchronized scratch location for synthetic development output.
If a separately authorized contingency ever requires real export material, create
a unique operator-owned directory with mode 0700 and files 0600; verify tmpfs and
swap policy. RAM-backed storage is not proof against swap, dumps, screen capture,
or copies. Never reuse a shared predictable directory or bulk-delete scratch roots.

No baseline export/import converter is planned. Do not revive retired Electron
debugging or reverse-engineered APIs merely because historical examples exist.
Unsupported methods require a new threat review and explicit operation approval.

## Cleanup and evidence

User-requested local deletion is limited to one confirmed entry in the native
TUI browser. GPG deletion unlinks the exact validated flat private ciphertext;
TPM-backed deletion uses a direct SQLite transaction for the pinned totpm 0.1.2
schema version 1; the native substring-matching delete command is not used.
`BEGIN IMMEDIATE` protects the exact `BINARY` service/account match, and exactly
one row must be deleted. Unknown schema, triggers and views are rejected, as are
non-private or non-absolute configuration, user-data and database paths. Only
local presence verification `none` is supported. No decrypted seed is read and
no native TPM operation is performed. Neither operation
changes keys, initializes stores, clears or evicts the TPM, deletes 1Password
items or changes the service's enrolled factor. There is no bulk or automatic
deletion. Escape, resize and cancellation leave the entry untouched.

An append-only coarse audit intent is written before the dangerous operation;
failure to write it blocks deletion. It contains no entry labels, item IDs,
paths, seeds or codes, and does not prove completion. After success the browser
refreshes metadata; if refresh fails, stale metadata is discarded. Backups and
other seed copies are unaffected, so removal is not a secure-erasure claim.

Record paths and ownership without contents before narrow cleanup. Check history,
clipboard manager, temporary captures and backups for unintended retention under
operator control. SSD deletion is not proof of physical erasure; prevent persistence
instead of promising secure deletion. If a real seed escaped, stop migration and
rotate the affected service enrollment through a trusted recovery path.

Gate security review before a software release and before enabling an optional
backend. Record coverage and unresolved risks; static pattern checks and synthetic
tests cannot prove that live accounts or independent recovery are safe.
