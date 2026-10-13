# Confirmed local-item deletion verification — 2026-10-12

The operator requested deletion of GPG and TPM item entries through the TUI.
The installed candidate is 1.0.0rc3. [Project status](../PROJECT-STATUS.md) remains
the authority for private migration and recovery gates.

## Delivered behavior and boundaries

In either local backend's item browser, d opens a confirmation naming the selected
entry. Exact uppercase `DELETE` and Enter authorize removal. Empty input, Escape,
resize or cancellation do not delete. The 1Password browser has no delete action,
and the adapter independently rejects 1Password deletion. There is no bulk delete.

GPG removal unlinks one owned private regular single-link ciphertext file through
an anchored directory descriptor. It does not invoke pass, Git or hooks, and
preserves the keyring, recipient configuration and extensions.

TPM removal uses an exact bounded SQLite transaction against the reviewed native
0.1.2 local-mode database schema. It requires exactly one service/account match,
rejects unknown schema objects/triggers and unsafe database/configuration paths,
and rolls back failed transactions. Native deletion is deliberately not used:
it matches substrings using SQL LIKE. The database transaction does not retrieve
or decrypt seed values and does not initialize, clear or evict a TPM key.
See [ADR 0007](adr/0007-confirmed-local-item-deletion.md) and the
[TUI specification](11-tui.md) for compatibility and operational limits.

Before each removal attempt, a bounded private audit file records UTC, UID,
backend, action and coarse scope. It contains no entry names, IDs, paths, seeds
or codes. Audit failure blocks deletion. Successful deletion refreshes the list;
if refresh fails, the removed entry is also removed from the in-memory list.
Backups and other copies remain; secure erasure or service seed revocation is
not claimed.

## Validation

`bash scripts/check.sh` passed after final code changes:

| Check | Result |
| --- | --- |
| Synthetic unittest suite | 243 passed |
| Aggregate branch-inclusive coverage | 94%; blocking floor 90% |
| Models and 1Password retrieval adapter | 100% |
| Ruff lint and formatting | Passed |
| ShellCheck | Passed |
| Markdown, links, task IDs and immutable reference hash | Passed |
| Wheel build and isolated package smoke | Passed |

Tests cover typed confirmation, cancellation, single-item dispatch, backend
exclusion, failed operations, audit failure, exact/ambiguous/missing matches,
unsafe files, locked databases and unexpected schema objects. A regression
catches a schema-filter SQL LIKE wildcard that could otherwise hide a trigger;
the implemented filter treats the internal-name underscore literally.

The installed native totpm 0.1.2 `list` command created a temporary synthetic
database without TPM access. Two dummy encrypted rows were inserted, then exact
companion deletion removed only the selected row and preserved its similarly
named neighbor. This independently verifies the schema against native-created
storage rather than relying only on hand-authored database fixtures.

## Installation and smoke evidence

Artifact: `dist/authy_local-1.0.0rc3-py3-none-any.whl`.

SHA-256: `e9543ed02eae6a058b04633ef5d2fffe4efac20ca10ee524079da31c1f2e0aa8`.

The reviewed offline installer applied the requested update to its app-owned
runtime, launcher and three fish wrappers. Installed version reports 1.0.0rc3;
repeat preview reports unchanged. Prior rc2 artifacts were preserved in
checksum-specific archive directories.

An actual installed TUI process ran in an 80x24 controlling pseudo-terminal with
a temporary synthetic HOME and empty PATH. It browsed a disposable empty `.gpg`
fixture, displayed the confirmation, accepted typed DELETE, removed that fixture
and refreshed to an empty list. Recipient file, key-home directory and scope
profile remained unchanged; the coarse audit was created without entry identity.
The process exited 0 and restored canonical input and echo.

No real item, keyring, vault, profile or TPM state was accessed by these tests.
No real deletion, enrollment, TPM provisioning, commit or publication occurred.
Authy retention and private operator acceptance remain unchanged.
