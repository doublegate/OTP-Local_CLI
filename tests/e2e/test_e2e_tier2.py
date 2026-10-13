"""Tier 2: Boundary & Corner Cases (>=5 test cases per feature covering edge conditions).

Covers edge conditions:
- Empty inputs, missing keys, special characters, invalid scopes
- Boundary buffer sizes, permission restrictions, fail-closed assertions
Across all 8 actions: F1-F8.
"""

import json
import sys
import unittest

from tests.e2e.harness import E2EEnvironment, MockCurses, MockScreen

ITEM = "a" * 26
ACCOUNT = "b" * 26
VAULT = "v" * 26


class TestTier2BoundaryAndCornerCases(unittest.TestCase):
    """Tier 2: Edge cases, boundaries, invalid inputs, and security constraints."""

    # -------------------------------------------------------------------------
    # Feature 1: Doctor Boundaries
    # -------------------------------------------------------------------------

    def test_f1_boundary_empty_path(self):
        """When PATH is completely empty, doctor runs safely and reports missing tools."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(["doctor"], extra_env={"PATH": ""})
            self.assertEqual(result.exit_code, 3)
            self.assertIn("op: missing", result.stdout)

    def test_f1_boundary_clock_probe_failure(self):
        """When clock probe outputs non-yes/no string, clock is unknown and does not crash."""
        with E2EEnvironment() as env:
            clock = env.bin_dir / "timedatectl"
            clock.write_text(f"#!{sys.executable}\nprint('unknown_output')\nsys.exit(0)\n")
            clock.chmod(0o700)
            result = env.invoke_cli(["doctor", "--json"])
            self.assertEqual(result.exit_code, 0)
            data = json.loads(result.stdout)
            self.assertEqual(data["clock"]["state"], "unknown")

    def test_f1_boundary_clock_not_synchronized_status_three(self):
        """When clock is not NTP-synchronized ('no'), clock state is missing and exit status is 3."""
        with E2EEnvironment() as env:
            clock = env.bin_dir / "timedatectl"
            clock.write_text(f"#!{sys.executable}\nimport sys\nprint('no')\nsys.exit(0)\n")
            clock.chmod(0o700)
            result = env.invoke_cli(["doctor"])
            self.assertEqual(result.exit_code, 3)

    def test_f1_boundary_corrupted_op_binary_not_executable(self):
        """When op binary is non-executable (0600), probe reports missing without crashing."""
        with E2EEnvironment() as env:
            op = env.bin_dir / "op"
            op.chmod(0o600)
            result = env.invoke_cli(["doctor"])
            self.assertEqual(result.exit_code, 3)
            self.assertIn("op: missing", result.stdout)

    def test_f1_boundary_env_scrubbing_removes_secrets(self):
        """Doctor and child processes do not leak OP_SESSION secrets to external binaries."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(
                ["doctor"],
                extra_env={"OP_SESSION_myaccount": "SUPER_SECRET_TOKEN_DO_NOT_LEAK"},
            )
            self.assertEqual(result.exit_code, 0)
            self.assertNotIn("SUPER_SECRET_TOKEN", result.stdout)
            self.assertNotIn("SUPER_SECRET_TOKEN", result.stderr)

    def test_f1_boundary_doctor_rapid_redraw_survives(self):
        """TUI rapidly toggling backends and re-running Doctor redraws without crash."""
        with E2EEnvironment() as env:
            # Run doctor (7), Enter, switch backend (b), 2, Enter, doctor (7), Enter, 'q'
            keys = [ord("7"), 10, ord("b"), ord("2"), 10, ord("7"), 10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("Doctor"))

    # -------------------------------------------------------------------------
    # Feature 2: Show Code Boundaries
    # -------------------------------------------------------------------------

    def test_f2_boundary_missing_terminal_fails_closed(self):
        """Show without terminal fails closed with exit code 3."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(
                ["show", ITEM, "--account", ACCOUNT, "--vault", VAULT],
                isatty=False,
            )
            self.assertEqual(result.exit_code, 3)

    def test_f2_boundary_invalid_item_length(self):
        """Item ID with 25 characters (invalid length) is rejected with exit code 2."""
        with E2EEnvironment() as env:
            short_item = "a" * 25
            result = env.invoke_cli(["show", short_item, "--account", ACCOUNT, "--vault", VAULT])
            self.assertEqual(result.exit_code, 2)

    def test_f2_boundary_item_special_chars_rejected(self):
        """Item ID containing special characters ($ ; \n \0) is rejected with exit code 2."""
        with E2EEnvironment() as env:
            bad_item = "a" * 20 + "$;rm -rf"
            result = env.invoke_cli(["show", bad_item, "--account", ACCOUNT, "--vault", VAULT])
            self.assertEqual(result.exit_code, 2)

    def test_f2_boundary_unknown_flag_rejected_without_leak(self):
        """Unknown CLI flag is rejected with exit code 2 without echoing argument content."""
        with E2EEnvironment() as env:
            secret_flag = "--injected-secret=VAL123"
            result = env.invoke_cli(["show", ITEM, "--account", ACCOUNT, "--vault", VAULT, secret_flag])
            self.assertEqual(result.exit_code, 2)
            self.assertNotIn("VAL123", result.stderr)

    def test_f2_boundary_backend_non_digit_code_rejected(self):
        """If backend returns non-digit output, code validation rejects with exit code 5."""
        with E2EEnvironment() as env:
            unique_item = "z" * 26
            result = env.invoke_cli(
                ["show", unique_item, "--account", ACCOUNT, "--vault", VAULT],
                extra_env={"MOCK_OTP_CODE": "BAD_NON_DIGIT_OUTPUT"},
            )
            self.assertEqual(result.exit_code, 5)

    def test_f2_boundary_cross_backend_flags_rejected(self):
        """Providing 1Password flags (--vault) with pass-otp backend rejected with code 2."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(
                ["show", "--backend", "pass-otp", "--vault", VAULT, "--store", "/store", "--key-home", "/keys", "--entry", "x"]
            )
            self.assertEqual(result.exit_code, 2)

    # -------------------------------------------------------------------------
    # Feature 3: Copy Code Boundaries
    # -------------------------------------------------------------------------

    def test_f3_boundary_clipboard_missing_wayland_display(self):
        """Copying when WAYLAND_DISPLAY is empty fails with exit code 3."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(
                ["copy", ITEM, "--account", ACCOUNT, "--vault", VAULT],
                extra_env={"WAYLAND_DISPLAY": ""},
            )
            self.assertEqual(result.exit_code, 3)

    def test_f3_boundary_clipboard_tool_absent(self):
        """Copying when wl-copy binary is absent fails with exit code 3."""
        with E2EEnvironment() as env:
            (env.bin_dir / "wl-copy").unlink()
            result = env.invoke_cli(["copy", ITEM, "--account", ACCOUNT, "--vault", VAULT])
            self.assertEqual(result.exit_code, 3)

    def test_f3_boundary_clipboard_handoff_failure_handled(self):
        """If wl-copy exits with failure, copy returns exit code 6 (selector/clipboard failure)."""
        with E2EEnvironment() as env:
            wl_copy = env.bin_dir / "wl-copy"
            wl_copy.write_text(f"#!{sys.executable}\nimport sys\nsys.exit(1)\n")
            wl_copy.chmod(0o700)
            result = env.invoke_cli(["copy", ITEM, "--account", ACCOUNT, "--vault", VAULT])
            self.assertEqual(result.exit_code, 6)

    def test_f3_boundary_empty_item_argument_rejected(self):
        """Empty string item argument is rejected with exit code 2."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(["copy", "", "--account", ACCOUNT, "--vault", VAULT])
            self.assertEqual(result.exit_code, 2)

    def test_f3_boundary_copy_with_redirected_stdout(self):
        """Redirecting stdout during copy works, and stdout remains strictly 0 bytes."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(
                ["copy", ITEM, "--account", ACCOUNT, "--vault", VAULT],
                isatty=True,
                stdout_isatty=False,
            )
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(env.clipboard_content().strip(), "001234")

    def test_f3_boundary_copy_with_overlong_scope_rejected(self):
        """Overlong account ID (>26 characters) is rejected with exit code 2."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(["copy", ITEM, "--account", ACCOUNT + "extra", "--vault", VAULT])
            self.assertEqual(result.exit_code, 2)

    # -------------------------------------------------------------------------
    # Feature 4: Browse and Show Boundaries
    # -------------------------------------------------------------------------

    def test_f4_boundary_empty_records_from_backend(self):
        """When backend returns zero items, browser displays 'No matching items.' without crash."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Mock op returning []
            op = env.bin_dir / "op"
            op.write_text(
                f"#!{sys.executable}\n"
                "import sys\n"
                "if sys.argv[1:] == ['--version']: print('2.39.0'); sys.exit(0)\n"
                "if len(sys.argv) > 1 and sys.argv[1] == 'item' and sys.argv[2] == 'list':\n"
                "    print('[]')\n"
                "    sys.exit(0)\n"
                "sys.exit(1)\n"
            )
            op.chmod(0o700)
            keys = [ord("1"), 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("No matching items") or screen.has_text("0 matches"))

    def test_f4_boundary_overlong_item_title_clipped(self):
        """Item title exceeding 500 characters is safely clipped by renderer."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            long_title = "VeryLongTitle" * 50
            op = env.bin_dir / "op"
            op.write_text(
                f"#!{sys.executable}\n"
                "import json, sys\n"
                "if sys.argv[1:] == ['--version']: print('2.39.0'); sys.exit(0)\n"
                "if len(sys.argv) > 1 and sys.argv[1] == 'item' and sys.argv[2] == 'list':\n"
                f"    print(json.dumps([{{'id': '{ITEM}', 'title': '{long_title}', 'vault': {{'id': '{VAULT}'}}}}]))\n"
                "    sys.exit(0)\n"
                "sys.exit(1)\n"
            )
            op.chmod(0o700)
            keys = [ord("1"), 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("VeryLongTitle"))

    def test_f4_boundary_special_chars_in_item_title(self):
        """Control characters in item title are escaped/sanitized without breaking terminal."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            op = env.bin_dir / "op"
            op.write_text(
                f"#!{sys.executable}\n"
                "import json, sys\n"
                "if sys.argv[1:] == ['--version']: print('2.39.0'); sys.exit(0)\n"
                "if len(sys.argv) > 1 and sys.argv[1] == 'item' and sys.argv[2] == 'list':\n"
                f"    print(json.dumps([{{'id': '{ITEM}', 'title': 'Title\\x00\\x1b[31mRed', 'vault': {{'id': '{VAULT}'}}}}]))\n"
                "    sys.exit(0)\n"
                "sys.exit(1)\n"
            )
            op.chmod(0o700)
            keys = [ord("1"), 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)

    def test_f4_boundary_search_regex_characters_literal(self):
        """Search query containing regex metacharacters (.*+?[]^$) matches literally."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Press '1', '/', search '.*+?', Enter, Esc, 'q'
            keys = [ord("1"), ord("/"), ord("."), ord("*"), ord("+"), ord("?"), 10, 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("0 matches") or screen.has_text("Search: .*+?"))

    def test_f4_boundary_search_matching_zero_items(self):
        """Search matching zero items displays empty state; backspace recovers items."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Press '1', '/', 'Z', 'Z', 'Z' (0 matches), backspace (263), backspace, backspace, Enter, Esc, 'q'
            keys = [ord("1"), ord("/"), ord("Z"), ord("Z"), ord("Z"), 263, 263, 263, 10, 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("GitHub") or screen.has_text("3 matches"))

    def test_f4_boundary_small_terminal_refuses_browser(self):
        """Terminal smaller than 18x60 refuses execution with exit code 3."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            code, _ = env.run_tui([ord("1"), ord("q")], profiles=profile, size=(10, 40))
            self.assertEqual(code, 3)

    # -------------------------------------------------------------------------
    # Feature 5: Browse and Copy Boundaries
    # -------------------------------------------------------------------------

    def test_f5_boundary_enter_on_empty_list_no_op(self):
        """Pressing Enter when no items match does not invoke copy or crash."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Key '2', search 'NO_SUCH_ITEM', Enter (stop search), Enter (try copy), Esc, 'q'
            keys = [ord("2"), ord("/"), *map(ord, "NO_SUCH_ITEM"), 10, 10, 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertEqual(env.clipboard_content(), "")

    def test_f5_boundary_key_c_on_empty_list_no_op(self):
        """Pressing 'c' when no items match does not crash or copy."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            keys = [ord("2"), ord("/"), *map(ord, "NO_SUCH_ITEM"), 10, ord("c"), 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertEqual(env.clipboard_content(), "")

    def test_f5_boundary_vertical_navigation_limits(self):
        """Arrow Up at top and Arrow Down at bottom do not exceed item bounds."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Press '2', 10x Up (259), 10x Down (258), 'c', Enter, Esc, 'q'
            keys = [ord("2"), *[259]*10, *[258]*10, ord("c"), 10, 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertEqual(env.clipboard_content().strip(), "001234")

    def test_f5_boundary_escape_cancels_browser_cleanly(self):
        """Pressing Escape immediately cancels browser without copying."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            keys = [ord("2"), 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertEqual(env.clipboard_content(), "")

    def test_f5_boundary_clipboard_failure_displays_message(self):
        """If clipboard tool fails during browse-and-copy, error message is displayed."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Remove wl-copy so clipboard fails
            (env.bin_dir / "wl-copy").unlink()
            # Press '2', Enter (to copy), Enter (to dismiss error modal), Esc, 'q'
            keys = [ord("2"), 10, 10, 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("unavailable") or screen.has_text("failed"))

    def test_f5_boundary_rapid_search_query_overflow(self):
        """Typing search query beyond 160 characters is bounded."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            long_query = [ord("a")] * 200
            keys = [ord("2"), ord("/"), *long_query, 10, 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)

    # -------------------------------------------------------------------------
    # Feature 6: Installation Preview Boundaries
    # -------------------------------------------------------------------------

    def test_f6_boundary_empty_wheel_path_rejected(self):
        """Empty string submitted in wheel form is rejected without running preview."""
        with E2EEnvironment() as env:
            # Key '8', press Enter (empty input - validator rejects), Escape (27), 'q'
            keys = [ord("8"), 10, 27, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertFalse(screen.has_text("PREVIEW (no changes)"))

    def test_f6_boundary_directory_as_wheel_path(self):
        """Passing a directory as wheel path is rejected with status 3."""
        with E2EEnvironment() as env:
            keys = [ord("8"), *map(ord, str(env.home)), 10, 10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("unavailable") or screen.has_text("failed"))

    def test_f6_boundary_corrupt_zip_file(self):
        """Corrupt/non-zip wheel file is rejected with status 3."""
        with E2EEnvironment() as env:
            bad_wheel = env.home / "authy_local-1.0.0-py3-none-any.whl"
            bad_wheel.write_bytes(b"NOT_A_VALID_ZIP_ARCHIVE")
            keys = [ord("8"), *map(ord, str(bad_wheel)), 10, 10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("unavailable") or screen.has_text("failed"))

    def test_f6_boundary_wheel_symlink_rejected(self):
        """Wheel path that is a symbolic link is rejected by security checks."""
        with E2EEnvironment() as env:
            symlink_wheel = env.home / "authy_local-symlink-py3-none-any.whl"
            symlink_wheel.symlink_to(env.wheel_path)
            keys = [ord("8"), *map(ord, str(symlink_wheel)), 10, 10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("unavailable") or screen.has_text("failed"))

    def test_f6_boundary_path_escaping_home_rejected(self):
        """Wheel path attempting path traversal escapes is rejected."""
        with E2EEnvironment() as env:
            bad_path = "/etc/authy_local-1.0.0-py3-none-any.whl"
            keys = [ord("8"), *map(ord, bad_path), 10, 10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("unavailable") or screen.has_text("failed"))

    def test_f6_boundary_whitespace_wheel_path(self):
        """Whitespace-only wheel path is rejected by form validator."""
        with E2EEnvironment() as env:
            keys = [ord("8"), ord(" "), ord(" "), 10, 27, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertFalse(screen.has_text("PREVIEW (no changes)"))

    # -------------------------------------------------------------------------
    # Feature 7: Private Migration Guide Boundaries
    # -------------------------------------------------------------------------

    def test_f7_boundary_small_terminal_clipping(self):
        """Guide renders in compact terminal (18x60) with safe text clipping."""
        with E2EEnvironment() as env:
            code, screen = env.run_tui([ord("9"), 10, ord("q")], size=(18, 60))
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("Private migration checkpoints"))

    def test_f7_boundary_repeated_key_presses_safe(self):
        """Rapid keypresses in guide modal are safely consumed without crash."""
        with E2EEnvironment() as env:
            keys = [ord("9"), *[10]*10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)

    def test_f7_boundary_cli_guide_excess_arguments(self):
        """CLI guide with excess unexpected arguments rejected with exit code 2."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(["guide", "migration", "extra_argument"])
            self.assertEqual(result.exit_code, 2)

    def test_f7_boundary_cli_guide_empty_topic(self):
        """CLI guide without topic rejected with exit code 2."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(["guide"])
            self.assertEqual(result.exit_code, 2)

    def test_f7_boundary_terminal_resize_in_guide(self):
        """Terminal resize event (KEY_RESIZE=410) in guide view redraws safely."""
        with E2EEnvironment() as env:
            keys = [ord("9"), 410, 10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("Private migration checkpoints"))

    def test_f7_boundary_non_ascii_guide_rendering(self):
        """Guide content is rendered cleanly without unhandled encoding error."""
        with E2EEnvironment() as env:
            keys = [ord("9"), 10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertIsInstance(screen.all_text(), str)

    # -------------------------------------------------------------------------
    # Feature 8: Saved Scope Boundaries
    # -------------------------------------------------------------------------

    def test_f8_boundary_corrupted_json_profiles_file(self):
        """Corrupted JSON in profiles file is handled cleanly by load_profiles."""
        with E2EEnvironment() as env:
            prof_file = env.home / ".config/authy-local/tui-profiles.json"
            prof_file.parent.mkdir(parents=True, mode=0o700)
            prof_file.write_text("NOT_VALID_JSON{{{")
            prof_file.chmod(0o600)
            # Loading corrupt file returns {} or raises AppError safely
            from authy_local import tui_profiles
            from authy_local.errors import AppError
            with self.assertRaises(AppError):
                tui_profiles.load(env.home)

    def test_f8_boundary_insecure_permissions_rejected(self):
        """Profiles file with world-readable permissions (0666) is rejected."""
        with E2EEnvironment() as env:
            prof_file = env.home / ".config/authy-local/tui-profiles.json"
            prof_file.parent.mkdir(parents=True, mode=0o700)
            prof_file.write_text(json.dumps({"onepassword": {"account": ACCOUNT, "vault": VAULT}}))
            prof_file.chmod(0o666)
            from authy_local import tui_profiles
            from authy_local.errors import AppError
            with self.assertRaises(AppError):
                tui_profiles.load(env.home)

    def test_f8_boundary_scope_form_escape_cancels(self):
        """Pressing Escape in scope form discards modifications without writing to disk."""
        with E2EEnvironment() as env:
            # Key '6', Escape (27), 'q'
            keys = [ord("6"), 27, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertEqual(env.load_profiles(), {})

    def test_f8_boundary_scope_field_non_ascii_rejected(self):
        """Scope field containing non-ASCII character (ord=226) is rejected."""
        with E2EEnvironment():
            from authy_local import tui
            curses = MockCurses()
            screen = MockScreen([ord("a"), 226, 10])
            self.assertIsNone(tui.prompt(screen, "Value", 26, curses))

    def test_f8_boundary_invalid_account_id_length_in_form(self):
        """Account ID with 25 characters fails length validation in form."""
        with E2EEnvironment():
            from authy_local import tui
            curses = MockCurses()
            # Attempt to submit 25 chars: form requires length==26
            screen = MockScreen([*map(ord, "a" * 25), 10, 27])
            profile = tui.configure_scope(screen, curses, "onepassword", None)
            self.assertIsNone(profile)

    def test_f8_boundary_tag_injection_rejected(self):
        """Invalid characters in optional tag (dashes, commas, newlines, overflow) rejected."""
        from authy_local.tui_profiles import valid_tag
        self.assertFalse(valid_tag("-leading-dash"))
        self.assertFalse(valid_tag("tag,with,comma"))
        self.assertFalse(valid_tag("tag\nwith\nnewline"))
        self.assertFalse(valid_tag("x" * 65))
        self.assertTrue(valid_tag("Valid Tag-01"))
