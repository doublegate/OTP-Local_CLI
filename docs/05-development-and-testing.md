# Development and validation

Status: developer workflow includes all three adapters, hidden enrollment,
dashboard, bundled guides, native-runtime setup, installer and fish wrappers.
Live compatibility and migration remain operator acceptance gates.

## Toolchain and layout

Use Python 3.14 and the standard library for the runtime and `unittest` for tests.
The [architecture](02-architecture.md) package layout and `pyproject.toml` expose
the `otp-local` entry point. Linux and Python `>=3.14,<3.15` are declared; the
observed runtime is Python 3.14.7. Synthetic unit and subprocess tests live in
`tests/test_*.py`; no real-account fixtures are permitted.

Use a project virtual environment for development. Keep environments, coverage,
build output and local state ignored. Do not install development dependencies into
the system interpreter. Avoid runtime third-party dependencies and network tests.

`requirements-dev.txt` pins setuptools 84.0.0, wheel 0.48.0, build 1.6.0,
packaging 26.3, pyproject_hooks 1.3.3, Ruff 0.17.0 and coverage 7.16.2.
`package.json` and its lock pin markdownlint-cli2 0.23.3 and its dependency tree.
Dependency setup may download tools; the test suite must not contact providers.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
npm ci --ignore-scripts
.venv/bin/python scripts/bundle_guides.py
bash scripts/check.sh
```

Editable installation is developer-local, not the Phase 2 home installer.
Build isolation is disabled only after installing the pinned build tools above.

## Implementation order

1. Build fake executables and a bounded subprocess runner; prove failures first.
2. Implement non-authenticating doctor probes and explicit scope validation.
3. Implement `show` with exact output validation and generic diagnostics.
4. Implement clipboard and selector flows against fake tools.
5. Add thin fish wrappers and a reversible, conflict-aware installer.
6. Integrate the curses TUI through shared command dispatch and preview-only installation.
7. Run an operator-controlled CLI/TUI synthetic-item acceptance test before real accounts.

Keep retrieval, presentation and installation separate. Inject clocks, process
launchers and terminal detection in tests. Avoid tests that merely duplicate the
implementation; assert observable output, denied operations and side effects.

## Required test matrix

The automated gate covers the following synthetic boundaries. Human acceptance
remains separate from software coverage.

| Area | Independent failures the suite must detect |
|---|---|
| Scope/argv | Missing/optionlike IDs; wrong vault; exact argument boundaries; shell metacharacters |
| Output | Leading zeros; six/eight digits; empty, extra line, ANSI, invalid UTF-8 and oversized output |
| Process | Nonzero status with secret-like stderr; timeout; cancellation; output flood; child cleanup |
| Show | TTY policy, explicit pipe override, stdout contains only validated code |
| Clipboard | Backend failure/cancel never calls copy; copy failure never prints code |
| Selector | Duplicate names, malicious titles, unknown selection, zero items, cancel, cap overflow |
| Environment | Debug/session/service overrides rejected or removed; fzf options/command/options-file overrides removed |
| Installer | Dry-run creates nothing; path escape; existing file; interrupted update; modified uninstall target |
| Doctor | Missing tools, unavailable session bus, unsupported version and unknown auth reported honestly |
| TUI | Navigation/cancel, safe display, shared dispatch, preview-only installation and terminal restoration |

Fake tools must be selected by explicit test paths, never by falling through to the
real `op` or clipboard executable. Tests must not inherit provider credentials.
Use conspicuously synthetic IDs and codes; assert that sentinel secret-like stderr
does not appear in any captured diagnostic. No fixtures derived from real accounts.

## Implemented local gate

Run `bash scripts/check.sh` from the prepared project environment. It executes:

```sh
.venv/bin/python scripts/bundle_guides.py --check
.venv/bin/python -m build --no-isolation
.venv/bin/python -m coverage run -m unittest discover -s tests -v
.venv/bin/python -m coverage report
.venv/bin/python -m coverage report --include='*/models.py,*/backends/onepassword.py' --fail-under=100
.venv/bin/ruff check src tests scripts
.venv/bin/ruff format --check src tests scripts
shellcheck scripts/check.sh
node_modules/.bin/markdownlint-cli2 --config .markdownlint-cli2.jsonc
.venv/bin/python scripts/check_docs.py
.venv/bin/python scripts/smoke_package.py
```

The script exports `PYTHONPATH` to the project's source directory. Individual
tests can be run with that same source path and the virtual-environment Python.
It checks bundled guides and builds the current wheel before installer tests;
those tests must never accidentally exercise a stale development artifact.
The source distribution retains the attributed public pass-otp test fixture and
license. Native fixture tests run the full hardened Bash extension with synthetic
GPG/oathtool stubs and inspect argv/stdin. Real synthetic GPG and swtpm acceptance
is separately reported; the default suite opens no real keyring or TPM device.
Coverage measures branches and enforces a 90% aggregate floor plus a 100% floor
over scope/code validation and the 1Password adapter. Semantic failure-case tests
remain mandatory independently of those percentages. Canonical status and
the final verification report record measured results after all changes settle.

Fish wrapper tests include `fish -n` and actual argument/status forwarding.
ShellCheck applies to the Bash gate, not to fish. Actual fzf is tested with a
synthetic controlling PTY; provider and clipboard acceptance remains human-only.

Documentation gates check local links, requirement/task references and consistency
with status. Limit formatting to hand-authored files; exempt the immutable reference
and generated Master-Claude core. Pin any Markdown linter and its configuration.
The implemented checker verifies authored local links, all 52 sprint task IDs
and the immutable reference checksum. Markdown configuration excludes reference
and generated guidance and permits long technical tables.

CI is optional for this local project. A later CI decision must use synthetic data,
the same aggregate gate, pinned tools and no vault access, clipboard session,
production credentials or uploads of private operational evidence.

## Human acceptance boundary

A human creates a disposable synthetic TOTP item in the chosen vault, runs the
installed command in a terminal, compares it with the native app, checks clipboard
behavior and verifies cancellation. Record only pass/fail and versions here.
Agents must not capture actual OTP output. A fake-tool pass proves the companion
contract; it does not prove desktop authorization or provider compatibility.

Before declaring a software release, review subprocess allowlists, error handling,
installer path handling and the complete diff. Re-run affected gates after fixes.
Keep full test results and aggregate metrics separate from account migration counts.
