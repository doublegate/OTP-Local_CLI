# Phase 2 verification — 2026-10-12

Status: Phase 2 software and preview exit criteria complete. The operator approved
real-home installation, which passed ownership and non-authenticating smoke checks.
Human disposable acceptance and Phase 3 migration evidence remain pending.

## Delivered capabilities

Scoped `copy` and `select [--copy]`, bounded ephemeral metadata, sanitized fzf
configuration, safe labels/index mapping and explicit Wayland handoff are
implemented. Failed retrieval or cancelled selection never invokes clipboard copy.

The same package includes fish wrappers, preview-first offline installation,
ownership snapshots, locking, journal recovery, verified rollback and conservative
uninstall. The curses TUI dispatches shared CLI operations, displays only validated
codes, previews installation and provides private migration guidance without
account mutations. No third-party Python runtime dependency was added.

Source fingerprint (sorted relative Python paths, NUL, bytes, NUL):
`c27f4f0119bb10027c7de9c0a054ee86a3e31071e4f62c7635681751284da174`.

## Measured checks

`bash scripts/check.sh` completed successfully after implementation stabilized:

| Check | Result |
| --- | --- |
| Synthetic unittest suite | 114 tests pass |
| Branch-inclusive coverage | 96% aggregate; blocking floor 90% |
| Scope/code validator and 1Password adapter | 100%; blocking floor 100% |
| Installer / interaction / TUI coverage | 93% / 96% / 99% |
| Ruff lint and formatting | Pass |
| ShellCheck and fish syntax/argument/status tests | Pass |
| Markdown and local links/task IDs/reference hash | Pass |
| Source distribution and wheel build | Pass |
| Isolated installed wheel | CLI help/version plus TUI and installer imports pass, without backend access |
| Actual fzf synthetic controlling terminal | Pass; five repeated scoped runs also passed |
| Actual curses menu with no backend available | Pass; menu renders and quits |
| Guidance doctor | Zero failures or warnings; not authenticated readiness evidence |
| Concrete real-home preview | Pass; no reported file collisions or writes |
| Authorized real-home installation | Pass; ownership, unchanged repeat preview and installed CLI/TUI help/version verified |
| Installed fish and uninstall preview | Wrapper help dispatch passes without backend access; preview lists only four owned launcher/function files |

The gate uses fake provider/clipboard executables, synthetic scope/code values,
temporary homes and controlled PTYs. It never accesses real vault contents or
reads the desktop clipboard. The package artifact and footprint are in the
[reviewable installation preview](../operations/2026-10-12-installation-preview.md).

## Failures found and resolved

- Initial command/TUI tests failed before implementation as expected.
- Actual fzf failed when detached from its controlling terminal. Selection now
  preserves the foreground terminal and cleans up its direct child; other bounded
  operations retain isolated process-group cleanup.
- Timing-driven PTY input was unreliable; the regression now answers actual cursor
  queries and accepts only after synthetic input loads.
- A test metadata fixture exceeded Linux environment limits; the fake backend now
  reads synthetic fixture data from its temporary file.
- Full discovery exposed a relative test-helper import; the absolute package
  import works with the canonical gate.
- Installer regressions cover concurrent edits, partial uninstall and malformed
  wheel metadata; TUI regressions reject overflow instead of truncating IDs.

## Limits and next evidence

Successful clipboard handoff preserves a background clipboard server. It does not
prove future ownership, paste success or history erasure. The selector has no
configured command hooks; its terminal-preserving cleanup targets its direct child.
Same-user malware, filesystem races and Python memory retention remain outside
the helper's guarantees.

Older releases are retained inert. Interrupted environment preparation before a
prepared manifest exists is refused on retry rather than deleted automatically.
See the [installer limits](../operations/2026-10-12-installer.md).

Phase 3 requires authorized installation, human CLI/TUI synthetic acceptance, a
passed private pilot and reconciled private account dispositions. No live OTP,
enrollment, fresh login, account migration, Authy retirement, commit or publication
is claimed here. The [operator checkpoints](../operations/2026-10-12-phase-3-operator-checkpoints.md)
define the pending evidence; aggregate status remains authoritative in
[PROJECT-STATUS.md](../../PROJECT-STATUS.md).
