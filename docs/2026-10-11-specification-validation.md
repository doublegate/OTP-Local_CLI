# Specification validation — 2026-10-11

Scope: documentation and plans, not implemented software or live account readiness.

| Check | Result |
|---|---|
| Local Markdown file links | No missing targets in hand-authored docs, root navigation and plans |
| Task allocation | Exactly 48 unique unchecked sprint tasks, T-AUTH-010 through T-AUTH-057 |
| Plan coverage | Six phase plans, twelve sprint plans; optional branch explicitly skippable |
| Requirements | R-01 through R-14 map to acceptance evidence and sprints |
| Document size | Each hand-authored guide/plan below 200 lines |
| Markdown lint | 0 issues; markdownlint-cli2 0.23.3 / markdownlint 0.41.1 |
| Agent configuration | mc-doctor: 0 fail, 0 warn; symlinks and core version valid |
| Immutable reference | SHA-256 unchanged from the recorded baseline |
| Application tests | Not applicable: source/test suite not implemented |
| Authentication/migration | Not performed; human verification remains pending |

Markdown lint covers README.md, PROJECT-STATUS.md, ROADMAP.md, docs and to-dos;
it excludes the generated AGENTS core and immutable reference. A temporary CLI2
configuration disables MD013 (line length), MD033 (HTML) and MD060 (table spacing).
No project lint configuration or runtime files were installed. A deliberately invalid
synthetic stdin fixture produced a failing linter result, confirming rules were active.
The linter's summary counts files with issues, so “0 issues in 0 files” following
“Linting: N files” denotes zero failing files.

Read-only review corrected three contract gaps: inherited fzf options-file behavior,
index-only selector output for long labels, and the installed human synthetic-item
gate before a real-account pilot. Link/task/hash checks were repeated afterward.

The parent Git repository ignores this project; an empty Git status/diff does not
establish that these documents are tracked. No repository was initialized and no
commit, publication, package change or MFA action was performed.

See [research evidence](10-research-and-host-evidence.md) for versions and remaining
live checks, and [project status](../PROJECT-STATUS.md) for authoritative progress.
