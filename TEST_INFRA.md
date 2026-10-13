# End-to-End (E2E) Test Infrastructure Specification

## 1. Test Philosophy

The End-to-End Testing Track for **Authy-to-1Password Local** is built on the following foundational tenets:

1. **Opaque-Box Testing**:
   - Tests exercise the system exclusively from the perspective of an external operator or client runtime.
   - Tests interact solely through the published public entrypoints:
     - Command-line interface: `otp-local` (via `python -m authy_local <cmd>` and `cli.main()`)
     - Terminal user interface: Textual/curses TUI dashboard (via `tui.run()` and `tui.session()`)
     - Offline installer: `authy-local-installer` / `installer.main()`
   - Internal implementation details, private variables, and non-contractual helper functions are never directly accessed or asserted upon.

2. **Requirement-Driven & Oracle-Verified**:
   - Test cases are systematically derived from the authoritative specifications in `ORIGINAL_REQUEST.md` and `PROJECT.md`.
   - Expected outputs (exit codes, RFC 6238 TOTP codes, stdout JSON structures, screen redraw frames) are derived strictly from documented requirements and standards.

3. **Security Baseline & Fail-Closed Integrity**:
   - Secret Leak Prevention: Under no circumstances should test outputs or error diagnostics expose sensitive tokens, seeds, or account IDs to standard error or logs.
   - Enforce explicit permissions (`0600` for profiles, `0700` for config directories).
   - Fail-closed behavior on missing terminals, pipe restrictions, and unauthenticated backends.

4. **Deterministic Hermetic Isolation**:
   - Every test case executes within a fresh temporary sandbox (`$HOME` tempdir, synthetic `$PATH`).
   - Zero state leakage between tests; no reliance on existing user profile paths (`~/.config/authy-local`) or native production vaults.
   - Fully deterministic and executable in local developer workstations and CI runners.

---

## 2. Feature Inventory

The project specifies 8 fundamental user actions and capabilities:

| ID | Feature Name | Command / UI Trigger | Scope & Behavior | Authoritative Reference |
|---|---|---|---|---|
| **F1** | **Doctor** | `doctor` / Key `1` | Capability inspection of external tools (op, gpg, oath, totpm, tpm2, timedatectl, wl-copy) without authenticating. | ORIGINAL_REQUEST §R1, PROJECT.md #7 |
| **F2** | **Show Code** | `show` / Key `2` | Retrieve OTP code for specified account/item, display on screen with active countdown/erasure instruction. | ORIGINAL_REQUEST §R1, PROJECT.md #8 |
| **F3** | **Copy Code** | `copy` / Key `3` | Retrieve OTP code and securely transfer to desktop clipboard without stdout leakage. | ORIGINAL_REQUEST §R1, PROJECT.md #9 |
| **F4** | **Browse and Show** | `select` / Key `4` | Interactive token catalog browser with search/filtering; pressing Enter or `s` displays selected code. | ORIGINAL_REQUEST §R1, PROJECT.md #10 |
| **F5** | **Browse and Copy** | `select --copy` / Key `5` | Interactive token catalog browser; pressing Enter or `c` copies selected code directly to clipboard. | ORIGINAL_REQUEST §R1, PROJECT.md #11 |
| **F6** | **Installation Preview** | `preview` / Key `6` | Offline inspection of local wheel package; outputs execution plan without touching filesystem. | ORIGINAL_REQUEST §R1, PROJECT.md #12 |
| **F7** | **Private Migration Guide** | `guide migration` / Key `7` | Review migration checkpoints and independent recovery procedures; scrollable modal in TUI. | ORIGINAL_REQUEST §R1, PROJECT.md #13 |
| **F8** | **Saved Scope** | `profiles` / Key `8` or `p` | Configure resident account/vault IDs or local store paths saved to `~/.config/authy-local/tui-profiles.json` (0600). | ORIGINAL_REQUEST §R1, PROJECT.md #14 |

---

## 3. 4-Tier Test Architecture

The E2E test suite is organized into 4 distinct testing tiers, each targeting a specific layer of functional verification:

```
tests/e2e/
├── harness.py               # Hermetic test harness, mock terminals, synthetic binaries
├── test_e2e_tier1.py        # Tier 1: Feature Coverage (>=5 tests per feature, >=40 total)
├── test_e2e_tier2.py        # Tier 2: Boundary & Corner Cases (>=5 tests per feature, >=40 total)
├── test_e2e_tier3.py        # Tier 3: Cross-Feature Interactions (Pairwise combinations, >=12 total)
└── test_e2e_tier4.py        # Tier 4: Real-World Application Scenarios (>=5 full scenarios)
```

### Tier 1: Feature Coverage (>=5 test cases per feature)
Verifies primary happy paths and expected nominal workflows across all 8 features.

- **F1 (Doctor)**:
  1. `test_doctor_cli_text_output`: Runs CLI doctor; verifies human-readable capability list.
  2. `test_doctor_cli_json_output`: Runs CLI `doctor --json`; validates JSON schema and capability attributes.
  3. `test_doctor_tui_key1_execution`: Pressing key '1' in TUI triggers doctor dispatch and displays summary.
  4. `test_doctor_all_tools_healthy_exit_zero`: When required tools are present, exit status is 0.
  5. `test_doctor_missing_op_exit_three`: When `op` CLI is absent, doctor reports missing and returns code 3.
  6. `test_doctor_tui_menu_selection`: Navigating menu to option 0 and pressing Enter triggers doctor.

- **F2 (Show Code)**:
  1. `test_show_code_cli_onepassword`: CLI `show` retrieves 6-digit TOTP code for 1Password backend.
  2. `test_show_code_cli_pass_otp`: CLI `show --backend pass-otp` retrieves valid TOTP code.
  3. `test_show_code_cli_totpm`: CLI `show --backend totpm` retrieves valid TOTP code.
  4. `test_show_code_tui_key2_with_resident_profile`: Pressing key '2' with resident profile prompts for item and renders code.
  5. `test_show_code_tui_menu_choice_1`: Menu navigation to choice 1 activates Show Code.
  6. `test_show_code_allow_pipe`: `--allow-pipe` flag allows non-interactive terminal pipe output.

- **F3 (Copy Code)**:
  1. `test_copy_code_cli_onepassword`: CLI `copy` delivers code to clipboard tool without writing code to stdout.
  2. `test_copy_code_cli_pass_otp`: CLI `copy --backend pass-otp` copies code to clipboard.
  3. `test_copy_code_cli_totpm`: CLI `copy --backend totpm` copies code to clipboard.
  4. `test_copy_code_tui_key3`: Pressing key '3' triggers clipboard copy dialog and dispatches copy.
  5. `test_copy_code_clean_stdout_invariant`: Asserts stdout is empty during copy operations to prevent screen scrapers.
  6. `test_copy_code_stderr_notice`: Stderr outputs confirmation notice without disclosing secret values.

- **F4 (Browse and Show)**:
  1. `test_browse_show_cli_select_onepassword`: CLI `select` presents items and shows selected code.
  2. `test_browse_show_cli_select_pass_otp`: CLI `select --backend pass-otp` presents gpg entries and shows code.
  3. `test_browse_show_cli_select_totpm`: CLI `select --backend totpm` presents totpm entries and shows code.
  4. `test_browse_show_tui_key4`: Pressing key '4' launches interactive item browser.
  5. `test_browse_show_tui_filter_and_select`: Search filtering (`/`) in TUI browser highlights matching item.
  6. `test_browse_show_tui_key_s_shows_code`: Pressing 's' in browser displays code for active item.

- **F5 (Browse and Copy)**:
  1. `test_browse_copy_cli_select_copy_onepassword`: CLI `select --copy` delivers selected code to clipboard.
  2. `test_browse_copy_cli_select_copy_pass_otp`: CLI `select --copy --backend pass-otp` copies selected code.
  3. `test_browse_copy_cli_select_copy_totpm`: CLI `select --copy --backend totpm` copies selected code.
  4. `test_browse_copy_tui_key5`: Pressing key '5' launches browser in direct-copy mode.
  5. `test_browse_copy_tui_enter_copies_code`: Pressing Enter in browse-and-copy copies code and returns.
  6. `test_browse_copy_tui_key_c_copies_code`: Pressing 'c' in browse mode copies code.

- **F6 (Installation Preview)**:
  1. `test_install_preview_cli_wheel`: Running installer without `--apply` produces `PREVIEW (no changes)` output.
  2. `test_install_preview_tui_key6`: Pressing key '6' in TUI prompts for wheel path and runs preview.
  3. `test_install_preview_tui_menu_choice_5`: Menu navigation to choice 5 activates preview dialog.
  4. `test_install_preview_zero_side_effects`: Confirms no filesystem modifications occur in HOME during preview.
  5. `test_install_preview_missing_wheel_error`: Nonexistent wheel path returns exit code 3 or error modal.

- **F7 (Private Migration Guide)**:
  1. `test_guide_cli_migration`: CLI `guide migration` outputs migration guide markdown.
  2. `test_guide_cli_all_topics`: CLI `guide` outputs topics (`setup`, `acceptance`, `recovery`, `tui`, `optional`).
  3. `test_guide_tui_key7`: Pressing key '7' opens scrollable migration checkpoints screen.
  4. `test_guide_tui_dismiss_returns_to_dashboard`: Pressing Enter or Escape dismisses guide screen.
  5. `test_guide_cli_invalid_topic_rejected`: CLI `guide invalid_topic` exits with code 2.

- **F8 (Saved Scope)**:
  1. `test_saved_scope_save_and_load`: Configured profile roundtrips to `tui-profiles.json`.
  2. `test_saved_scope_strict_file_permissions`: Profile file has mode `0600` and directory `0700`.
  3. `test_saved_scope_tui_key8_configure_form`: Pressing key '8' opens scope configuration form.
  4. `test_saved_scope_tui_key_p_shortcut`: Key 'p' opens profile configuration form.
  5. `test_saved_scope_multi_backend`: Profile stores settings for onepassword, pass-otp, and totpm independently.
  6. `test_saved_scope_absent_defaults`: Fresh environment without profiles returns empty profile cleanly.

---

### Tier 2: Boundary & Corner Cases (>=5 test cases per feature)
Verifies resilience against extreme inputs, missing assets, format errors, and adversarial edge cases.

- **F1 (Doctor Boundaries)**:
  1. Empty `PATH` environment: doctor runs without crashing when all tools are absent.
  2. Malformed clock probe: non-standard `timedatectl` output handled gracefully.
  3. Slow/timed-out capability probe: timeout does not hang the process.
  4. Corrupted executable: non-executable mock binary in PATH reports missing without error trace.
  5. Sensitive environment scrubbing: child environment strips `OP_SESSION_*` and token variables.

- **F2 (Show Code Boundaries)**:
  1. Missing terminal without `--allow-pipe`: fails closed with exit code 3.
  2. Missing item identifier when no profile exists: rejected with exit code 2.
  3. Unknown/unexpected CLI arguments: rejected with exit code 2 without echoing argument content.
  4. Special characters & control characters in item input: safely sanitized or rejected.
  5. Non-digit / malformed backend output: rejected with exit code 3 without disclosing payload.

- **F3 (Copy Code Boundaries)**:
  1. Clipboard tool completely absent: returns exit code 3 cleanly.
  2. Clipboard subprocess exits with error: handles failure without leaking code.
  3. Maximum length item argument: strict bounds enforcement without buffer overflow.
  4. Incompatible backend flags (`--vault` with `--backend pass-otp`): rejected with exit code 2.
  5. Pipe redirection during copy: copy continues to clipboard, stdout stays empty.

- **F4 (Browse and Show Boundaries)**:
  1. Empty catalog / zero records from backend: browser displays clean empty state without IndexError.
  2. Overlong item titles (>1000 characters): safely clipped by terminal renderer.
  3. Special characters & newlines in item labels: sanitized with safe_text.
  4. Regex metacharacters in search query (`.*+?[]^$`): treated as literal text, no regex crash.
  5. Search query matching zero items: displays empty results list gracefully.

- **F5 (Browse and Copy Boundaries)**:
  1. Selection on empty item list: pressing Enter/c does not trigger copy or error.
  2. Clipboard error during browser session: displays error message modal instead of crash.
  3. Vertical boundary navigation: pressing Up at top or Down at bottom does not crash.
  4. Filtered single item selection: filtering down to 1 item and pressing Enter copies exact item.
  5. Escape dismissal: pressing Escape cancels browser without triggering copy.

- **F6 (Installation Preview Boundaries)**:
  1. Empty wheel path input: rejected by validator without executing preview.
  2. Wheel path pointing to a directory: rejected with exit code 3.
  3. Corrupted / unreadable zip archive: rejected with exit code 3.
  4. Symlink escaping user home in path: rejected by `_safe()` security checks.
  5. Path exceeding maximum allowable length (>1024 chars): form limits input buffer.

- **F7 (Private Migration Guide Boundaries)**:
  1. Minimal terminal window dimensions (e.g. 10x40): safe clipping without curses overflow.
  2. Rapid keypress flooding while viewing guide: safely consumed without input queue corruption.
  3. CLI guide called with excess arguments: rejected with exit code 2.
  4. Non-ascii or unicode guide rendering: handles UTF-8 terminal encoding properly.
  5. Terminal resize event (`KEY_RESIZE`) while in guide: redraws gracefully without crash.

- **F8 (Saved Scope Boundaries)**:
  1. Corrupted / non-JSON profiles file on disk: safely handled as invalid or reset without crash.
  2. Profile file with insecure permissions (`0777`): rejected or tightened to `0600`.
  3. Form input containing control characters or whitespace injection: stripped or rejected.
  4. Escape cancellation of form: leaves previous profile unchanged on disk.
  5. Overlong field entries (>256 characters): validated against size constraints.

---

### Tier 3: Cross-Feature Interactions (Pairwise Combinations)
Verifies sequential operations and state handoffs across distinct features:

1. `Doctor` -> `Saved Scope`: Inspect capabilities first, then configure resident profile for detected backend.
2. `Saved Scope` -> `Show Code`: Save resident profile, execute Show Code without arguments; verify saved account/vault IDs are auto-applied.
3. `Saved Scope` -> `Copy Code`: Save resident profile, execute Copy Code; verify clipboard receives code using saved scope.
4. `Saved Scope` -> `Browse and Show`: Save resident profile, open Browse and Show; verify catalog items loaded from saved scope.
5. `Saved Scope` -> `Browse and Copy`: Save resident profile, open Browse and Copy; verify selected item copies using saved scope.
6. `Backend Switching` -> `Saved Scope`: Switch active backend in TUI ('b'), configure each profile, verify profiles coexist without collisions.
7. `Doctor` -> `Browse and Show`: Doctor verifies tool availability, browser successfully indexes records.
8. `Browse and Show` -> `Copy Code`: In browser, preview code on screen with 's', then copy code with 'c'.
9. `Show Code` -> `Copy Code`: Retrieve code with Show Code, immediately retrieve next code with Copy Code.
10. `Installation Preview` -> `Private Migration Guide`: Preview installation package, then transition to migration checkpoints.
11. `Saved Scope Update` -> `Show Code`: Mutate existing profile in Saved Scope, verify next Show Code reflects updated scope.
12. `Browse Search` -> `Refresh` -> `Copy`: Search items in browser, clear search filter, navigate down, and copy selected item.

---

### Tier 4: Real-World Application Scenarios (>=5 Realistic Scenarios)
Verifies complex, end-to-end multi-step operator workflows mimicking production usage:

1. **Scenario 1: Fresh Operator Onboarding & Environment Validation**:
   - Operator runs Doctor check (CLI & TUI).
   - Operator inspects Private Migration Guide.
   - Operator runs Installation Preview on wheel artifact.
   - Operator configures Saved Scope profile.
   - Operator runs Doctor again to confirm operational readiness.

2. **Scenario 2: Daily Workflow — Rapid TOTP Code Retrieval (Show & Copy)**:
   - Operator with pre-configured 1Password profile launches TUI.
   - Retrieves primary login OTP via Show Code with countdown view.
   - Dismisses primary code view.
   - Retrieves secondary login OTP via Copy Code for immediate desktop clipboard paste.
   - Exits dashboard cleanly.

3. **Scenario 3: Multi-Account Browser Navigation & Search Workflow**:
   - Operator launches Browse and Show with multiple accounts.
   - Types search query `/aws` to filter AWS production credentials.
   - Inspects AWS code on screen.
   - Clears search and searches `/github`.
   - Copies GitHub code directly from browser and exits.

4. **Scenario 4: Multi-Backend Offline Operator Workflow**:
   - Operator works in an environment with both pass-otp (GPG) and totpm (TPM) local stores.
   - Configures saved profile for pass-otp and retrieves GPG-backed code.
   - Switches backend to totpm, configures totpm config path, and browses stored keys.
   - Copies totpm code and verifies profile isolation between backends.

5. **Scenario 5: Fail-Closed Security & Resilient Recovery Scenario**:
   - Operator attempts retrieval with invalid/broken backend subprocess.
   - System displays safe diagnostic without exposing backend commandline or secrets.
   - Operator consults Migration Guide to review recovery procedures.
   - Operator adjusts scope profile in Saved Scope.
   - Re-running Show Code succeeds cleanly.

---

## 4. Test Suite Execution & Commands

The opaque-box E2E test suite is executed using `pytest`:

```bash
PYTHONPATH=src:tests pytest tests/e2e/
```

Individual tier execution:
```bash
PYTHONPATH=src:tests pytest tests/e2e/test_e2e_tier1.py
PYTHONPATH=src:tests pytest tests/e2e/test_e2e_tier2.py
PYTHONPATH=src:tests pytest tests/e2e/test_e2e_tier3.py
PYTHONPATH=src:tests pytest tests/e2e/test_e2e_tier4.py
```
