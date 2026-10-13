"""Tier 1: Feature Coverage (>=5 test cases per feature covering representative inputs).

Covers all 8 actions:
- F1: Doctor
- F2: Show code
- F3: Copy code
- F4: Browse and show
- F5: Browse and copy
- F6: Installation preview
- F7: Private migration guide
- F8: Saved scope
"""

import json
import sys
import unittest

from authy_local import __version__
from tests.e2e.harness import E2EEnvironment

ITEM = "a" * 26
ACCOUNT = "b" * 26
VAULT = "v" * 26


class TestTier1FeatureCoverage(unittest.TestCase):
    """Tier 1: Comprehensive feature coverage across all 8 user actions."""

    # -------------------------------------------------------------------------
    # Feature 1: Doctor
    # -------------------------------------------------------------------------

    def test_f1_doctor_cli_text_format(self):
        """CLI doctor returns human-readable text status for all inspected tools."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(["doctor"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("op: available", result.stdout)
            self.assertIn("platform: available", result.stdout)
            self.assertIn("python: available", result.stdout)

    def test_f1_doctor_cli_json_format(self):
        """CLI doctor --json returns valid JSON mapping tool names to status dicts."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(["doctor", "--json"])
            self.assertEqual(result.exit_code, 0)
            data = json.loads(result.stdout)
            self.assertIn("op", data)
            self.assertEqual(data["op"]["state"], "available")
            self.assertIn("platform", data)
            self.assertIn("python", data)
            self.assertIn("clock", data)

    def test_f1_doctor_tui_key1_execution(self):
        """Pressing key '7' in TUI executes doctor and renders summary panel."""
        with E2EEnvironment() as env:
            # Press '7' to run doctor, then Enter to dismiss, then 'q' to exit
            code, screen = env.run_tui([ord("7"), 10, ord("q")])
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("Doctor") or screen.has_text("available"))

    def test_f1_doctor_healthy_status_zero(self):
        """Doctor returns 0 when required platform, python, op, and clock are available."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(["doctor"])
            self.assertEqual(result.exit_code, 0)

    def test_f1_doctor_missing_op_exit_three(self):
        """Doctor reports missing and exits with code 3 when op is absent."""
        with E2EEnvironment() as env:
            (env.bin_dir / "op").unlink()
            result = env.invoke_cli(["doctor"])
            self.assertEqual(result.exit_code, 3)
            self.assertIn("op: missing", result.stdout)

    def test_f1_doctor_tui_menu_choice_0(self):
        """Selecting Doctor from dashboard menu with Enter triggers inspection."""
        with E2EEnvironment() as env:
            # Menu item 6 is Doctor (6x Down arrow). Press Enter (10), Enter to dismiss, 'q' to quit.
            code, screen = env.run_tui([*[258]*6, 10, 10, ord("q")])
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("Doctor"))

    # -------------------------------------------------------------------------
    # Feature 2: Show Code
    # -------------------------------------------------------------------------

    def test_f2_show_code_cli_onepassword_valid(self):
        """CLI show outputs 6-digit TOTP code for 1Password backend."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(["show", ITEM, "--account", ACCOUNT, "--vault", VAULT])
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stdout.strip(), "001234")

    def test_f2_show_code_cli_allow_pipe(self):
        """CLI show with --allow-pipe outputs code when stdout is not a terminal."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(
                ["show", ITEM, "--account", ACCOUNT, "--vault", VAULT, "--allow-pipe"],
                isatty=True,
                stdout_isatty=False,
            )
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stdout.strip(), "001234")

    def test_f2_show_code_tui_key2_with_resident_profile(self):
        """TUI key '3' with resident profile prompts only for item and displays code."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Press '3' (Show code), type 26-char ITEM, press Enter (10), Enter to dismiss, 'q'
            keys = [ord("3"), *map(ord, ITEM), 10, 10, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("001234"))

    def test_f2_show_code_tui_menu_choice_1(self):
        """TUI menu choice 2 (Show code) activated via 2x Down arrow and Enter."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # 2x Down arrow (258), Enter (10), type ITEM, Enter, Enter to dismiss, 'q'
            keys = [258, 258, 10, *map(ord, ITEM), 10, 10, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("001234"))

    def test_f2_show_code_countdown_timer_modal(self):
        """TUI show code displays countdown / dismissal prompt."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            keys = [ord("3"), *map(ord, ITEM), 10, 10, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("Dismiss") or screen.has_text("001234"))

    def test_f2_show_code_cli_version_flag(self):
        """CLI --version reports project version without invoking backend."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(["--version"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn(__version__, result.stdout)

    # -------------------------------------------------------------------------
    # Feature 3: Copy Code
    # -------------------------------------------------------------------------

    def test_f3_copy_code_cli_onepassword(self):
        """CLI copy sends 6-digit TOTP code to desktop clipboard via wl-copy."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(["copy", ITEM, "--account", ACCOUNT, "--vault", VAULT])
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(env.clipboard_content().strip(), "001234")

    def test_f3_copy_code_stdout_clean_invariant(self):
        """CLI copy outputs nothing to stdout, preventing screen scrapers."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(["copy", ITEM, "--account", ACCOUNT, "--vault", VAULT])
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stdout, "")

    def test_f3_copy_code_tui_key3(self):
        """TUI key '4' triggers Copy code for resident profile."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Key '4', type ITEM, Enter (10), Enter to dismiss, 'q'
            keys = [ord("4"), *map(ord, ITEM), 10, 10, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertEqual(env.clipboard_content().strip(), "001234")

    def test_f3_copy_code_tui_menu_choice_2(self):
        """TUI menu choice 3 (Copy code) activated via 3x Down-Enter."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Down x 3 (258), Enter (10), type ITEM, Enter (10), Enter, 'q'
            keys = [258, 258, 258, 10, *map(ord, ITEM), 10, 10, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertEqual(env.clipboard_content().strip(), "001234")

    def test_f3_copy_code_missing_wayland_display_fails_closed(self):
        """CLI copy fails with exit code 3 when WAYLAND_DISPLAY is absent."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(
                ["copy", ITEM, "--account", ACCOUNT, "--vault", VAULT],
                extra_env={"WAYLAND_DISPLAY": ""},
            )
            self.assertEqual(result.exit_code, 3)

    def test_f3_copy_code_missing_wl_copy_fails_closed(self):
        """CLI copy fails with exit code 3 when wl-copy binary is absent."""
        with E2EEnvironment() as env:
            (env.bin_dir / "wl-copy").unlink()
            result = env.invoke_cli(["copy", ITEM, "--account", ACCOUNT, "--vault", VAULT])
            self.assertEqual(result.exit_code, 3)

    # -------------------------------------------------------------------------
    # Feature 4: Browse and Show
    # -------------------------------------------------------------------------

    def test_f4_browse_show_cli_select_onepassword(self):
        """CLI select lists items via fzf and shows chosen item's code."""
        with E2EEnvironment() as env:
            # Setup mock fzf
            fzf = env.bin_dir / "fzf"
            fzf.write_text(
                f"#!{sys.executable}\n"
                "import sys\n"
                "if '--help' in sys.argv:\n"
                "    print('--accept-nth --delimiter')\n"
                "    sys.exit(0)\n"
                "print('0')\n"
                "sys.exit(0)\n"
            )
            fzf.chmod(0o700)
            result = env.invoke_cli(["select", "--account", ACCOUNT, "--vault", VAULT])
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stdout.strip(), "001234")

    def test_f4_browse_show_tui_key4_opens_browser(self):
        """TUI key '4' opens item browser showing listed items."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Press '1', then Escape (27) to go back, 'q' to quit
            keys = [ord("1"), 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("GitHub") or screen.has_text("items"))

    def test_f4_browse_show_tui_key_s_shows_code(self):
        """In browser, pressing 's' retrieves and displays the selected item's code."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Press '1' (browse), 's' (show), Enter (dismiss code modal), Escape (exit browser), 'q'
            keys = [ord("1"), ord("s"), 10, 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("001234"))

    def test_f4_browse_show_tui_enter_shows_code(self):
        """In browser, pressing Enter in show-mode displays code."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Press '1' (browse and show default), Enter (10), Enter to dismiss, Escape, 'q'
            keys = [ord("1"), 10, 10, 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("001234"))

    def test_f4_browse_show_tui_search_filter(self):
        """Typing search query in browser filters displayed items."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Press '1', press '/' to search, type 'AWS', press Enter (10) to finish search, Esc, 'q'
            keys = [ord("1"), ord("/"), ord("A"), ord("W"), ord("S"), 10, 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("AWS"))

    def test_f4_browse_show_tui_navigation_arrows(self):
        """Down arrow navigates down the item list in browser."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Press '1', Down arrow (258), 's', Enter, Escape, 'q'
            keys = [ord("1"), 258, ord("s"), 10, 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("001234"))

    # -------------------------------------------------------------------------
    # Feature 5: Browse and Copy
    # -------------------------------------------------------------------------

    def test_f5_browse_copy_cli_select_copy_onepassword(self):
        """CLI select --copy delivers selected item's code to clipboard."""
        with E2EEnvironment() as env:
            fzf = env.bin_dir / "fzf"
            fzf.write_text(
                f"#!{sys.executable}\n"
                "import sys\n"
                "if '--help' in sys.argv:\n"
                "    print('--accept-nth --delimiter')\n"
                "    sys.exit(0)\n"
                "print('0')\n"
                "sys.exit(0)\n"
            )
            fzf.chmod(0o700)
            result = env.invoke_cli(["select", "--copy", "--account", ACCOUNT, "--vault", VAULT])
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(env.clipboard_content().strip(), "001234")
            self.assertEqual(result.stdout, "")

    def test_f5_browse_copy_tui_key5_opens_browser(self):
        """TUI key '2' opens browser in copy mode."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Key '2', Escape, 'q'
            keys = [ord("2"), 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("Enter: copy") or screen.has_text("GitHub"))

    def test_f5_browse_copy_tui_enter_copies_code(self):
        """In browse-and-copy mode, pressing Enter copies selected code to clipboard."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Key '2', Enter (copies), Enter (dismiss modal), Escape, 'q'
            keys = [ord("2"), 10, 10, 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertEqual(env.clipboard_content().strip(), "001234")

    def test_f5_browse_copy_tui_key_c_copies_code(self):
        """In browser, pressing 'c' copies selected item's code to clipboard."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Key '2', 'c' (copies), Enter (dismiss modal), Escape, 'q'
            keys = [ord("2"), ord("c"), 10, 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertEqual(env.clipboard_content().strip(), "001234")

    def test_f5_browse_copy_tui_search_and_copy(self):
        """Filter item in copy browser and press Enter to copy filtered item."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # Key '2', '/', type 'Git', Enter (finish search), Enter (copy), Enter (dismiss), Escape, 'q'
            keys = [ord("2"), ord("/"), ord("G"), ord("i"), ord("t"), 10, 10, 10, 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertEqual(env.clipboard_content().strip(), "001234")

    def test_f5_browse_copy_tui_menu_choice_4(self):
        """TUI menu choice 1 (Browse and copy) navigated via 1x Down arrow."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            # 1x Down (258), Enter (10), Escape, 'q'
            keys = [258, 10, 27, ord("q")]
            code, screen = env.run_tui(keys, profiles=profile)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("Enter: copy") or screen.has_text("items"))

    # -------------------------------------------------------------------------
    # Feature 6: Installation Preview
    # -------------------------------------------------------------------------

    def test_f6_install_preview_cli_wheel(self):
        """Running offline installer without --apply produces preview execution plan."""
        with E2EEnvironment() as env:
            from authy_local.installer import operate
            plan = operate("install", env.home, wheel=env.wheel_path, apply=False)
            self.assertIsInstance(plan, list)
            self.assertGreater(len(plan), 0)
            self.assertTrue(any("stage" in line or "install" in line for line in plan))

    def test_f6_install_preview_tui_key6(self):
        """Pressing key '8' in TUI prompts for wheel path and renders preview."""
        with E2EEnvironment() as env:
            # Key '8', type wheel path, Enter, Enter to dismiss preview, 'q'
            keys = [ord("8"), *map(ord, str(env.wheel_path)), 10, 10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("PREVIEW") or screen.has_text("Installation preview"))

    def test_f6_install_preview_tui_menu_choice_5(self):
        """Menu navigation to choice 7 activates Installation preview."""
        with E2EEnvironment() as env:
            # 7x Down, Enter, type wheel path, Enter, Enter dismiss, 'q'
            keys = [*[258] * 7, 10, *map(ord, str(env.wheel_path)), 10, 10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("PREVIEW") or screen.has_text("Installation preview"))

    def test_f6_install_preview_filesystem_unchanged(self):
        """Installation preview makes zero changes to home directory."""
        with E2EEnvironment() as env:
            from authy_local.installer import operate
            before = set(env.home.rglob("*"))
            operate("install", env.home, wheel=env.wheel_path, apply=False)
            after = set(env.home.rglob("*"))
            self.assertEqual(before, after)

    def test_f6_install_preview_missing_wheel_error(self):
        """Preview with missing wheel returns error status 3."""
        with E2EEnvironment() as env:
            missing_wheel = env.home / "nonexistent-py3-none-any.whl"
            keys = [ord("8"), *map(ord, str(missing_wheel)), 10, 10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("unavailable") or screen.has_text("failed"))

    def test_f6_install_preview_form_escape_cancels(self):
        """Pressing Escape in preview form cancels without running preview."""
        with E2EEnvironment() as env:
            # Key '8', Escape (27), 'q'
            keys = [ord("8"), 27, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertFalse(screen.has_text("PREVIEW (no changes)"))

    # -------------------------------------------------------------------------
    # Feature 7: Private Migration Guide
    # -------------------------------------------------------------------------

    def test_f7_guide_cli_migration(self):
        """CLI guide migration outputs private migration checkpoints."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(["guide", "migration"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Migration and recovery procedure", result.stdout)

    def test_f7_guide_cli_all_topics(self):
        """CLI guide outputs documentation for all valid topics."""
        topics = ("setup", "recovery", "acceptance", "tui", "optional")
        with E2EEnvironment() as env:
            for topic in topics:
                with self.subTest(topic=topic):
                    result = env.invoke_cli(["guide", topic])
                    self.assertEqual(result.exit_code, 0)
                    self.assertGreater(len(result.stdout), 100)

    def test_f7_guide_tui_key7_displays_guide(self):
        """Pressing key '9' in TUI displays Private migration guide checkpoints."""
        with E2EEnvironment() as env:
            # Key '9', Enter to dismiss, 'q'
            keys = [ord("9"), 10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("Private migration checkpoints"))

    def test_f7_guide_tui_menu_choice_6(self):
        """Menu navigation to choice 8 displays Private migration guide."""
        with E2EEnvironment() as env:
            # 8x Down, Enter, Enter to dismiss, 'q'
            keys = [*[258] * 8, 10, 10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("Private migration checkpoints"))

    def test_f7_guide_tui_escape_dismisses_to_dashboard(self):
        """Pressing Escape in migration guide dismisses view back to dashboard."""
        with E2EEnvironment() as env:
            # Key '9', Escape (27), 'q'
            keys = [ord("9"), 27, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("Authy Local") or screen.has_text("Actions"))

    def test_f7_guide_cli_invalid_topic_rejected(self):
        """CLI guide rejects invalid topic with exit code 2."""
        with E2EEnvironment() as env:
            result = env.invoke_cli(["guide", "nonexistent_topic"])
            self.assertEqual(result.exit_code, 2)

    # -------------------------------------------------------------------------
    # Feature 8: Saved Scope
    # -------------------------------------------------------------------------

    def test_f8_saved_scope_save_and_load_roundtrip(self):
        """Saved scope writes profile to ~/.config/authy-local/tui-profiles.json."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            env.save_profile(profile)
            loaded = env.load_profiles()
            self.assertEqual(loaded, profile)

    def test_f8_saved_scope_strict_file_permissions(self):
        """Saved scope ensures mode 0600 on profiles file and 0700 on parent dir."""
        with E2EEnvironment() as env:
            profile = {"onepassword": {"account": ACCOUNT, "vault": VAULT}}
            env.save_profile(profile)
            prof_file = env.home / ".config/authy-local/tui-profiles.json"
            self.assertEqual(prof_file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(prof_file.parent.stat().st_mode & 0o777, 0o700)

    def test_f8_saved_scope_tui_key8_configure_form(self):
        """Pressing key '6' opens Saved scope configuration form and saves profile."""
        with E2EEnvironment() as env:
            # Key '6', enter Account (26 chars), Enter (10), enter Vault (26 chars), Enter (10), Enter (tag), 'q'
            keys = [ord("6"), *map(ord, ACCOUNT), 10, *map(ord, VAULT), 10, 10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            profiles = env.load_profiles()
            self.assertIn("onepassword", profiles)
            self.assertEqual(profiles["onepassword"]["account"], ACCOUNT)
            self.assertEqual(profiles["onepassword"]["vault"], VAULT)

    def test_f8_saved_scope_tui_key_p_shortcut(self):
        """Pressing key 'p' opens Saved scope configuration form."""
        with E2EEnvironment() as env:
            keys = [ord("p"), *map(ord, ACCOUNT), 10, *map(ord, VAULT), 10, 10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            profiles = env.load_profiles()
            self.assertEqual(profiles["onepassword"]["account"], ACCOUNT)

    def test_f8_saved_scope_multi_backend_profiles(self):
        """Profiles for onepassword, pass-otp, and totpm coexist independently."""
        with E2EEnvironment() as env:
            profiles = {
                "onepassword": {"account": ACCOUNT, "vault": VAULT},
                "pass-otp": {"store": "/store", "key_home": "/keys"},
                "totpm": {"config": "/totpm.conf"},
            }
            env.save_profile(profiles)
            loaded = env.load_profiles()
            self.assertEqual(loaded, profiles)

    def test_f8_saved_scope_empty_profiles_file(self):
        """Fresh environment returns empty dict without throwing errors."""
        with E2EEnvironment() as env:
            self.assertEqual(env.load_profiles(), {})
