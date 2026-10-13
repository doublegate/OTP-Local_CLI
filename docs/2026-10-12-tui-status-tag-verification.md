# TUI status and OTP tag verification — 2026-10-12

The operator requested retained Session Status and a 1Password OTP-only browser,
and reported adding the `OTP` tag to the intended entries. Candidate 1.0.0rc4
implements retained Doctor results and optional saved metadata tag filtering.
[Project status](../PROJECT-STATUS.md) remains the authority for private gates.

## Behavior

Action 1 replaces the initial unchecked message with a summary of available,
missing and unknown capabilities. The summary survives dashboard redraws,
backend selection and returning from the browser. Another Doctor run replaces
it; failures show a retry notice. There is no background refresh or authentication
claim. Capability names and states are allowlisted before rendering or retention.

The 1Password browser lists Login metadata within the saved account/vault using
tag `OTP` by default. Existing account/vault-only profiles remain valid and use
this default without rewriting the profile. Key p or 8 provides a third field
for saving a different tag; Ctrl-U clears it, and blank disables the tag filter.
Tags are bounded single printable ASCII values; commas, leading dash and control
characters are rejected before any native request.

The [official item-list reference](https://www.1password.dev/cli/reference/management-commands/item#item-list)
documents metadata filtering through `--tags`, including nested tags. This is an
operator-maintained classification, not verification that an OTP field exists.
No bulk item-content or OTP reads were added. CLI `select` keeps its existing
behavior, and show/copy still retrieve only the explicitly selected item.

## Validation

The final `bash scripts/check.sh` passed:

| Check | Result |
| --- | --- |
| Synthetic unittest suite | 250 passed |
| Aggregate branch-inclusive coverage | 94%; blocking floor 90% |
| Models and 1Password retrieval adapter | 100% |
| Ruff lint and formatting; ShellCheck | Passed |
| Markdown, links, task IDs and immutable reference hash | Passed |
| Build and isolated wheel smoke | Passed |

Regressions cover retained Doctor state, safe failures, legacy scopes, editable
default and blank tags, saved-profile validation, native metadata arguments and
unchanged CLI selection. Initial regression tests failed before implementation.
An initial gate caught a loop-lambda lint error in a test; it was corrected before
the successful final gate. A separate read-only review found no actionable issue.

## Installed evidence

Artifact: `dist/authy_local-1.0.0rc4-py3-none-any.whl`.

SHA-256: `804b3e12204abc228408cd595401dfd1279b1a8461b0d5c7ad47ae453f5ff2a1`.

The offline installer previewed and applied the update to its app-owned runtime,
launcher and wrappers. Installed version reports 1.0.0rc4. Repeat preview reports
unchanged. Prior rc3 wheel and source archive were preserved by checksum.

The actual installed TUI ran in an 80x24 controlling pseudo-terminal using an
isolated synthetic HOME and a metadata-only fake `op`. Doctor's summary survived
returning from a browser. A legacy account/vault profile sent the default `OTP`
tag filter, listed a synthetic entry and remained byte-identical after exit.
The process exited 0 and restored canonical input and echo. The fake backend
rejected operations other than version and metadata listing.

Documentation checks also passed after adding this report: 62 authored files,
52 task IDs and the unchanged reference hash. Bundled public guides match source.
No real profile, item, vault, keyring or TPM state was read. Authy retention and
private migration/recovery gates are unchanged; no commit or publication occurred.
