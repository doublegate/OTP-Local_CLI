# Resident TUI scope and browsing verification — 2026-10-12

The operator requested resident 1Password account/vault scope and selection of
stored items across 1Password, pass-otp/GPG and totpm/TPM. The installed candidate
is now 1.0.0rc2. [Project status](../../PROJECT-STATUS.md) remains authoritative for
migration and private acceptance; this report establishes software delivery.

## Delivered behavior

- Backend selector b offers all three stores with independent saved scopes.
- Key 8 or p configures account/vault IDs, store/key-home paths or TPM config path.
- Private profiles use `~/.config/authy-local/tui-profiles.json`, mode 0600 under
  an owned 0700 directory. Parsing is bounded; unsafe paths, ownership, modes,
  duplicate keys, unknown fields and malformed data fail closed. Saves are atomic.
- Keys 4/5 open a native searchable browser. Highlight/search never request OTPs;
  Enter, s or c explicitly show/copy the selected item. Refresh uses r.
- IDs/paths persist across launches; metadata, item keys and codes do not.
  CLI flags remain explicit, and no profile is created during installation.
- The 1Password list contains scoped Login candidates. It does not identify OTP
  availability reliably; only a chosen item is requested, with a safe failure if
  it has no OTP. There are no bulk secret reads or background authorization calls.

See the [TUI specification](../specs/11-tui.md) for keys, forms and security boundaries.

## Validation

`bash scripts/check.sh` passed after the final implementation:

| Check | Result |
| --- | --- |
| Synthetic unittest suite | 208 passed |
| Aggregate branch-inclusive coverage | 94%; blocking floor 90% |
| Models and 1Password retrieval adapter | 100% |
| Ruff lint and formatting | Passed |
| ShellCheck | Passed |
| Markdown, local links and task allocation | Passed; 52 existing task IDs |
| Immutable migration reference | Hash unchanged |
| Wheel build and isolated package smoke | Passed |

Regressions cover resident scope without repeated ID entry, selected-item show
and copy, search/edit/refresh, cancellation, terminal resize, static errors,
unsafe profile files and atomic write failures. Reversed JSON field order cannot
swap account/vault or store/key-home values when editing a saved scope. Tests
use synthetic isolated homes, files and backend responses only.

## Installed evidence

Artifact: `dist/authy_local-1.0.0rc2-py3-none-any.whl`.

SHA-256: `69e4c480ddc59a9cff5c74c53156460552b4cf1c48039732f62bdea9d995755f`.

The reviewed installer applied the update to its existing owned runtime, launcher
and three fish wrappers. `otp-local --version` reports 1.0.0rc2. A repeat preview
reports all four targets unchanged. The prior rc1 wheel and source distribution
were preserved under checksum-specific directories in `dist/archive/`.

An actual installed curses process ran in an 80x24 controlling pseudo-terminal
with a synthetic HOME and empty PATH. It loaded a prewritten private GPG scope,
opened the native browser and displayed a synthetic encrypted-entry filename,
then exited 0 and restored canonical input and echo. The scope file remained
unchanged. No real profile, vault, keyring, OTP store or TPM was accessed by this
smoke check; showing/copying real codes remains private operator acceptance.

No account enrollment, TPM initialization, seed transfer, commit or publication
was performed. Existing Authy retention and operational gates remain in effect.
