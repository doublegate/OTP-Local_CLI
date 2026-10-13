"""Tier 3: Cross-Feature Interactions (Pairwise combinations across features).

Tests sequential interactions and state handoffs between:
- Doctor <-> Saved Scope
- Saved Scope <-> Show Code / Copy Code
- Saved Scope <-> Browse and Show / Browse and Copy
- Backend Switching <-> Saved Scope
- Browse and Show <-> Copy Code
- Installation Preview <-> Private Migration Guide
- Multi-backend workflows
"""

import unittest

from tests.e2e.harness import E2EEnvironment

ITEM = "a" * 26
ACCOUNT = "b" * 26
VAULT = "v" * 26
ITEM2 = "c" * 26


class TestTier3CrossFeatureInteractions(unittest.TestCase):
    """Tier 3: Pairwise feature interactions and sequential state transitions."""

    def test_pairwise_doctor_then_saved_scope(self):
        """Pairwise: Run Doctor check, then configure Saved Scope in TUI."""
        with E2EEnvironment() as env:
            # 1. Run Doctor: key '7', Enter to dismiss
            # 2. Configure Saved Scope: key '6', enter Account, Enter, enter Vault, Enter, Enter, 'q'
            keys = [
                ord("7"), 10,
                ord("6"), *map(ord, ACCOUNT), 10, *map(ord, VAULT), 10, 10,
                ord("q"),
            ]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("Doctor"))
            profiles = env.load_profiles()
            self.assertEqual(profiles["onepassword"]["account"], ACCOUNT)
            self.assertEqual(profiles["onepassword"]["vault"], VAULT)

    def test_pairwise_saved_scope_then_show_code(self):
        """Pairwise: Configure Saved Scope on disk, then execute Show Code without re-prompting scope."""
        with E2EEnvironment() as env:
            env.save_profile({"onepassword": {"account": ACCOUNT, "vault": VAULT}})
            # In TUI, key '3' (Show code) with saved scope prompts ONLY for item
            keys = [ord("3"), *map(ord, ITEM), 10, 10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("001234"))

    def test_pairwise_saved_scope_then_copy_code(self):
        """Pairwise: Configure Saved Scope, then execute Copy Code delivering OTP to clipboard."""
        with E2EEnvironment() as env:
            env.save_profile({"onepassword": {"account": ACCOUNT, "vault": VAULT}})
            # Key '4' (Copy code), enter ITEM, Enter (10), Enter to dismiss modal, 'q'
            keys = [ord("4"), *map(ord, ITEM), 10, 10, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertEqual(env.clipboard_content().strip(), "001234")

    def test_pairwise_saved_scope_then_browse_show(self):
        """Pairwise: Configure Saved Scope, then open Browse and Show using the saved vault."""
        with E2EEnvironment() as env:
            env.save_profile({"onepassword": {"account": ACCOUNT, "vault": VAULT}})
            # Key '1' (browse), 's' (show selected), Enter (dismiss code), Escape (exit browser), 'q'
            keys = [ord("1"), ord("s"), 10, 27, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("GitHub") or screen.has_text("001234"))

    def test_pairwise_saved_scope_then_browse_copy(self):
        """Pairwise: Configure Saved Scope, then open Browse and Copy to clipboard."""
        with E2EEnvironment() as env:
            env.save_profile({"onepassword": {"account": ACCOUNT, "vault": VAULT}})
            # Key '2' (browse & copy), Enter (copy), Enter (dismiss modal), Escape, 'q'
            keys = [ord("2"), 10, 10, 27, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertEqual(env.clipboard_content().strip(), "001234")

    def test_pairwise_backend_switch_then_saved_scope(self):
        """Pairwise: Switch active backend ('b'), then configure scope for newly active backend."""
        with E2EEnvironment() as env:
            # 'b' (switch backend), '2' (pass-otp - selects immediately), '6' (saved scope)
            # Field 1 (store): 21 (Ctrl-U clear), '/my/store', 10 (advance)
            # Field 2 (key_home): 21 (Ctrl-U clear), '/my/keys', 10 (submit), 'q'
            keys = [
                ord("b"), ord("2"),
                ord("6"),
                21, *map(ord, "/my/store"), 10,
                21, *map(ord, "/my/keys"), 10,
                ord("q"),
            ]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            profiles = env.load_profiles()
            self.assertIn("pass-otp", profiles)
            self.assertEqual(profiles["pass-otp"]["store"], "/my/store")
            self.assertEqual(profiles["pass-otp"]["key_home"], "/my/keys")

    def test_pairwise_doctor_then_browse_show(self):
        """Pairwise: Verify health with Doctor, then immediately browse tokens."""
        with E2EEnvironment() as env:
            env.save_profile({"onepassword": {"account": ACCOUNT, "vault": VAULT}})
            # Doctor (7), Enter dismiss, Browse (1), Escape, 'q'
            keys = [ord("7"), 10, ord("1"), 27, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("GitHub") or screen.has_text("Doctor"))

    def test_pairwise_browse_show_then_copy_code(self):
        """Pairwise: In browser, inspect code with 's', then copy code with 'c'."""
        with E2EEnvironment() as env:
            env.save_profile({"onepassword": {"account": ACCOUNT, "vault": VAULT}})
            # '1' (browse), 's' (show), 10 (dismiss), 'c' (copy), 10 (dismiss), 27 (exit), 'q'
            keys = [ord("1"), ord("s"), 10, ord("c"), 10, 27, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertEqual(env.clipboard_content().strip(), "001234")

    def test_pairwise_show_code_then_copy_code_dashboard(self):
        """Pairwise: Retrieve code with Show (key 3), then retrieve code with Copy (key 4)."""
        with E2EEnvironment() as env:
            env.save_profile({"onepassword": {"account": ACCOUNT, "vault": VAULT}})
            # Key '3', ITEM, 10, 10 dismiss, Key '4', ITEM, 10, 10 dismiss, 'q'
            keys = [
                ord("3"), *map(ord, ITEM), 10, 10,
                ord("4"), *map(ord, ITEM), 10, 10,
                ord("q"),
            ]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertEqual(env.clipboard_content().strip(), "001234")

    def test_pairwise_installation_preview_then_migration_guide(self):
        """Pairwise: Preview wheel installation, then immediately review migration guide."""
        with E2EEnvironment() as env:
            # Key '8', wheel path, 10, 10 dismiss, Key '9' (guide), 10 dismiss, 'q'
            keys = [
                ord("8"), *map(ord, str(env.wheel_path)), 10, 10,
                ord("9"), 10,
                ord("q"),
            ]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("Private migration checkpoints"))

    def test_pairwise_saved_scope_update_then_show_code(self):
        """Pairwise: Update existing saved scope in form, then show code with updated scope."""
        with E2EEnvironment() as env:
            # Save initial profile
            initial_vault = "x" * 26
            env.save_profile({"onepassword": {"account": ACCOUNT, "vault": initial_vault}})
            # Reconfigure via key '6', new account, new vault
            updated_account = "d" * 26
            updated_vault = "e" * 26
            # In form: clear account (21), type updated, Enter (10); clear vault (21), type updated, Enter (10); Enter (tag submit)
            keys = [
                ord("6"),
                21, *map(ord, updated_account), 10,
                21, *map(ord, updated_vault), 10,
                10,
                ord("3"), *map(ord, ITEM), 10, 10,
                ord("q"),
            ]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            profiles = env.load_profiles()
            self.assertEqual(profiles["onepassword"]["account"], updated_account)
            self.assertEqual(profiles["onepassword"]["vault"], updated_vault)

    def test_pairwise_browse_search_then_refresh_then_copy(self):
        """Pairwise: In browser, search for item, press refresh ('r'), navigate and copy ('c')."""
        with E2EEnvironment() as env:
            env.save_profile({"onepassword": {"account": ACCOUNT, "vault": VAULT}})
            # '1' (browse), '/' (search), 'A', 'W', 'S', 10 (end search), 'r' (refresh), 'c' (copy), 10 (dismiss), 27, 'q'
            keys = [
                ord("1"), ord("/"), ord("A"), ord("W"), ord("S"), 10,
                ord("r"), ord("c"), 10, 27, ord("q"),
            ]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertEqual(env.clipboard_content().strip(), "001234")

    def test_pairwise_preview_failure_then_migration_guide(self):
        """Pairwise: Installation preview fails on invalid path; operator reviews migration guide."""
        with E2EEnvironment() as env:
            bad_wheel = env.home / "bad.whl"
            # Key '8', bad path, 10, 10 dismiss error, Key '9', 10 dismiss, 'q'
            keys = [
                ord("8"), *map(ord, str(bad_wheel)), 10, 10,
                ord("9"), 10,
                ord("q"),
            ]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("Private migration checkpoints"))

    def test_pairwise_multi_backend_profile_coexistence(self):
        """Pairwise: Multi-backend saved scopes persist and do not cross-contaminate."""
        with E2EEnvironment() as env:
            profiles = {
                "onepassword": {"account": ACCOUNT, "vault": VAULT},
                "pass-otp": {"store": "/store", "key_home": "/keys"},
            }
            env.save_profile(profiles)
            # Switch to pass-otp ('b', '2', 10), open saved scope ('6'), Escape, 'q'
            keys = [ord("b"), ord("2"), 10, ord("6"), 27, ord("q")]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            loaded = env.load_profiles()
            self.assertEqual(loaded["onepassword"]["account"], ACCOUNT)
            self.assertEqual(loaded["pass-otp"]["store"], "/store")

    def test_pairwise_cli_doctor_then_cli_show(self):
        """Pairwise: CLI operator checks doctor health, then runs show code."""
        with E2EEnvironment() as env:
            doc_res = env.invoke_cli(["doctor"])
            self.assertEqual(doc_res.exit_code, 0)
            show_res = env.invoke_cli(["show", ITEM, "--account", ACCOUNT, "--vault", VAULT])
            self.assertEqual(show_res.exit_code, 0)
            self.assertEqual(show_res.stdout.strip(), "001234")

    def test_pairwise_cli_show_then_cli_copy(self):
        """Pairwise: CLI operator retrieves code on terminal, then copies same code to clipboard."""
        with E2EEnvironment() as env:
            show_res = env.invoke_cli(["show", ITEM, "--account", ACCOUNT, "--vault", VAULT])
            self.assertEqual(show_res.exit_code, 0)
            copy_res = env.invoke_cli(["copy", ITEM, "--account", ACCOUNT, "--vault", VAULT])
            self.assertEqual(copy_res.exit_code, 0)
            self.assertEqual(env.clipboard_content().strip(), show_res.stdout.strip())
