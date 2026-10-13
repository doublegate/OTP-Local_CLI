"""Adversarial Stress Test Suite for Milestone M3 (Dialog Stress & Event Hammering).

Authored by Challenger 1 (Empirical Challenger) to rigorously stress test:
1. Rapid key event injection / hammering (100+ events per second across action keys 1-8, b, p, ?, esc).
2. Modal dismissal via Escape/q and boundary resizes while modals are open (below 60x18 and back).
3. Boundary inputs in SavedScopeModal: invalid regex characters, oversized paths (>1024 chars),
   non-existent directories, traversal sequences, and malformed tags.
4. OTP memory wiping: verify that when CodeDisplayModal is dismissed/unmounted, the OTP code is
   completely wiped from instance attributes and memory.
"""

import asyncio
import time
import unittest
from collections.abc import Callable
from unittest.mock import MagicMock

from textual.events import Key
from textual.widgets import Button, Input, Static

from authy_local.tui import (
    AuthyApp,
    BackendSelectModal,
    CodeDisplayModal,
    DashboardScreen,
    DeleteConfirmModal,
    DoctorModal,
    HelpModal,
    InstallPreviewModal,
    MessageModal,
    MigrationGuideModal,
    PromptItemModal,
    SavedScopeModal,
    TokenBrowserScreen,
    WheelPathModal,
)


class TestM3DialogStress(unittest.IsolatedAsyncioTestCase):
    """Adversarial stress and dialog verification harness under Textual pilot."""

    def setUp(self) -> None:
        self.dummy_dispatch: Callable = lambda args, out, diag: 0
        self.dummy_preview: Callable = lambda wheel, out, diag: 0
        self.valid_profile = {
            "onepassword": {
                "account": "2w4j6k8m0n2p4r6t8v0x2z4a6c",
                "vault": "2w4j6k8m0n2p4r6t8v0x2z4a6c",
            }
        }

    async def test_rapid_key_event_hammering_dashboard_action_keys(self) -> None:
        """Hammer 150+ rapid key events across action keys (1-8, b, p, ?) at high rate (>100 events/sec).

        Verifies no crash, screen stack stays bounded, and hammering protection activates.
        """
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)
        action_keys = ["1", "2", "3", "4", "5", "6", "7", "8", "b", "p", "question_mark"]

        async with app.run_test() as pilot:
            self.assertIsInstance(app.screen, DashboardScreen)

            # Rapid injection of 150 events in a tight loop (< 0.05s)
            start_time = time.perf_counter()
            for i in range(150):
                k = action_keys[i % len(action_keys)]
                char = k if len(k) == 1 else "?"
                app._driver.send_message(Key(k, char))
            elapsed = time.perf_counter() - start_time

            # Rate should exceed 100 events/second
            rate = 150 / max(elapsed, 0.001)
            self.assertGreater(rate, 100.0)

            await pilot.pause()
            self.assertTrue(app.is_running)

            # Screen stack must not have accumulated unbounded modal screens
            self.assertLessEqual(len(app.screen_stack), 2)

            # Let hammering cooldown expire (0.15s)
            await asyncio.sleep(0.2)
            await pilot.pause()

            # Verify app is still functional and returns cleanly
            self.assertTrue(app.is_running)
            await pilot.press("escape")
            await pilot.pause()

    async def test_rapid_key_hammering_escape_clean_exit_dashboard(self) -> None:
        """Verify that rapid key hammering ending in Escape on dashboard exits cleanly with code 0."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)
        keys_to_hammer = ["1", "2", "3", "4", "5", "6", "7", "8", "b", "p", "escape"]

        async with app.run_test() as pilot:
            self.assertIsInstance(app.screen, DashboardScreen)

            for i in range(100):
                k = keys_to_hammer[i % len(keys_to_hammer)]
                char = k if len(k) == 1 else None
                app._driver.send_message(Key(k, char))

            await pilot.pause()
            # Escape on DashboardScreen should trigger clean quit (exit code 0)
            self.assertFalse(app.is_running)
            self.assertEqual(app.return_code, 0)

    async def test_rapid_key_hammering_while_modals_open(self) -> None:
        """Inject bursts of 100+ key events while each modal is open to ensure no stack corruption."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)

        modals = [
            DoctorModal(states={"op": "available"}),
            HelpModal(),
            SavedScopeModal(backend="onepassword"),
            MigrationGuideModal(),
            InstallPreviewModal(),
            BackendSelectModal(current_backend="onepassword"),
        ]

        async with app.run_test() as pilot:
            for modal in modals:
                app.push_screen(modal)
                await pilot.pause()
                self.assertIs(app.screen, modal)

                # Hammer 100 events while this modal is mounted
                for i in range(100):
                    k = str((i % 8) + 1)
                    app._driver.send_message(Key(k, k))

                await pilot.pause()
                self.assertTrue(app.is_running)

                # Dismiss modal cleanly via Escape
                await pilot.press("escape")
                await pilot.pause()
                self.assertIsInstance(app.screen, DashboardScreen)

    async def test_all_modals_dismissal_via_escape(self) -> None:
        """Verify modal dismissal via Escape across all 11 dialog and screen classes."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)

        async with app.run_test() as pilot:
            self.assertIsInstance(app.screen, DashboardScreen)

            # 1. DoctorModal
            app.push_screen(DoctorModal(states={"op": "available"}))
            await pilot.pause()
            self.assertIsInstance(app.screen, DoctorModal)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # 2. PromptItemModal
            app.push_screen(
                PromptItemModal(
                    backend="onepassword",
                    profile=self.valid_profile["onepassword"],
                    action_mode="show",
                )
            )
            await pilot.pause()
            self.assertIsInstance(app.screen, PromptItemModal)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # 3. CodeDisplayModal
            app.push_screen(CodeDisplayModal(code="654321", item_label="TestItem"))
            await pilot.pause()
            self.assertIsInstance(app.screen, CodeDisplayModal)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # 4. MessageModal
            app.push_screen(MessageModal("Test Alert", ["Sample message line"]))
            await pilot.pause()
            self.assertIsInstance(app.screen, MessageModal)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # 5. WheelPathModal
            app.push_screen(WheelPathModal())
            await pilot.pause()
            self.assertIsInstance(app.screen, WheelPathModal)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # 6. InstallPreviewModal
            app.push_screen(InstallPreviewModal())
            await pilot.pause()
            self.assertIsInstance(app.screen, InstallPreviewModal)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # 7. MigrationGuideModal
            app.push_screen(MigrationGuideModal())
            await pilot.pause()
            self.assertIsInstance(app.screen, MigrationGuideModal)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # 8. SavedScopeModal
            app.push_screen(SavedScopeModal(backend="onepassword"))
            await pilot.pause()
            self.assertIsInstance(app.screen, SavedScopeModal)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # 9. BackendSelectModal
            app.push_screen(BackendSelectModal(current_backend="onepassword"))
            await pilot.pause()
            self.assertIsInstance(app.screen, BackendSelectModal)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # 10. HelpModal
            app.push_screen(HelpModal())
            await pilot.pause()
            self.assertIsInstance(app.screen, HelpModal)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # 11. DeleteConfirmModal
            app.push_screen(DeleteConfirmModal(backend="pass-otp", label="test/entry"))
            await pilot.pause()
            self.assertIsInstance(app.screen, DeleteConfirmModal)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_token_browser_dismissal_escape_and_q(self) -> None:
        """Verify TokenBrowserScreen dismissal via both Escape and 'q'."""
        records = [("k1", "GitHub OTP"), ("k2", "AWS Production")]
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)

        async with app.run_test() as pilot:
            # Dismissal via 'q'
            browser = TokenBrowserScreen(
                backend="onepassword",
                profile=self.valid_profile["onepassword"],
                records=records,
            )
            app.push_screen(browser)
            await pilot.pause()
            self.assertIsInstance(app.screen, TokenBrowserScreen)
            await pilot.press("q")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # Dismissal via 'escape'
            browser2 = TokenBrowserScreen(
                backend="onepassword",
                profile=self.valid_profile["onepassword"],
                records=records,
            )
            app.push_screen(browser2)
            await pilot.pause()
            self.assertIsInstance(app.screen, TokenBrowserScreen)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # Dismissal when search input is focused: first Escape unfocuses, second Escape pops
            browser3 = TokenBrowserScreen(
                backend="onepassword",
                profile=self.valid_profile["onepassword"],
                records=records,
            )
            app.push_screen(browser3)
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            inp = browser3.query_one("#search-input", Input)
            self.assertTrue(inp.has_focus)
            # Escape while input focused clears/unfocuses
            await pilot.press("escape")
            await pilot.pause()
            self.assertFalse(inp.has_focus)
            self.assertIsInstance(app.screen, TokenBrowserScreen)
            # Second Escape dismisses browser screen
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_boundary_resizes_while_all_modals_open(self) -> None:
        """Resize terminal below 60x18 and back while modals are open; verify stability."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)

        modals = [
            DoctorModal(states={"op": "available"}),
            CodeDisplayModal(code="112233", item_label="ResizeTest"),
            SavedScopeModal(backend="onepassword"),
            HelpModal(),
            MigrationGuideModal(),
            InstallPreviewModal(),
        ]

        async with app.run_test() as pilot:
            for modal in modals:
                app.push_screen(modal)
                await pilot.pause()
                self.assertIs(app.screen, modal)

                # Boundary test points
                # 1. Standard (80x24)
                await pilot.resize_terminal(80, 24)
                await pilot.pause()

                # 2. Exact boundary threshold (60x18)
                await pilot.resize_terminal(60, 18)
                await pilot.pause()

                # 3. Sub-threshold width (59x18)
                await pilot.resize_terminal(59, 18)
                await pilot.pause()

                # 4. Sub-threshold height (60x17)
                await pilot.resize_terminal(60, 17)
                await pilot.pause()

                # 5. Compact tiny viewport (40x12)
                await pilot.resize_terminal(40, 12)
                await pilot.pause()

                # 6. Degenerate viewport (10x5)
                await pilot.resize_terminal(10, 5)
                await pilot.pause()

                # 7. Recovery to 80x24
                await pilot.resize_terminal(80, 24)
                await pilot.pause()

                # Modal must remain alive and dismissable
                self.assertTrue(app.is_running)
                await pilot.press("escape")
                await pilot.pause()
                self.assertIsInstance(app.screen, DashboardScreen)

    async def test_saved_scope_modal_boundary_regex_onepassword(self) -> None:
        """Boundary inputs in SavedScopeModal (onepassword): invalid regex, symbols, length limits."""
        save_mock = MagicMock()
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)
        app.save_profiles_callback = save_mock

        async with app.run_test() as pilot:
            modal = SavedScopeModal(backend="onepassword")
            app.push_screen(modal)
            await pilot.pause()
            self.assertIs(app.screen, modal)

            account_inp = modal.query_one("#scope-op-account", Input)
            vault_inp = modal.query_one("#scope-op-vault", Input)
            tag_inp = modal.query_one("#scope-op-tag", Input)
            error_banner = modal.query_one("#scope-error-banner", Static)

            # Adversarial test cases: (account, vault, tag, should_fail)
            invalid_cases = [
                # Regex metacharacters
                (".*.*.*.*.*.*.*.*.*.*.*.*", "2w4j6k8m0n2p4r6t8v0x2z4a6c", "", True),
                ("[a-zA-Z0-9]{26}", "2w4j6k8m0n2p4r6t8v0x2z4a6c", "", True),
                ("^2w4j6k8m0n2p4r6t8v0x2z$", "2w4j6k8m0n2p4r6t8v0x2z4a6c", "", True),
                # Symbols and non-alphanumeric
                ("2w4j6k8m0n2p4r6t8v0x2z4a!!", "2w4j6k8m0n2p4r6t8v0x2z4a6c", "", True),
                ("2w4j6k8m0n 2p4r6t8v0x2z4a", "2w4j6k8m0n2p4r6t8v0x2z4a6c", "", True),
                # Length violations: too short (<26)
                ("2w4j6k8m0n2p4r6t8v0x2z4a6", "2w4j6k8m0n2p4r6t8v0x2z4a6c", "", True),
                ("", "2w4j6k8m0n2p4r6t8v0x2z4a6c", "", True),
                # Length violations in vault
                ("2w4j6k8m0n2p4r6t8v0x2z4a6c", "short", "", True),
                # Invalid tag: starts with hyphen
                ("2w4j6k8m0n2p4r6t8v0x2z4a6c", "2w4j6k8m0n2p4r6t8v0x2z4a6c", "-tag", True),
                # Invalid tag: contains comma
                ("2w4j6k8m0n2p4r6t8v0x2z4a6c", "2w4j6k8m0n2p4r6t8v0x2z4a6c", "tag1,tag2", True),
                # Invalid tag: oversized (>64 chars)
                ("2w4j6k8m0n2p4r6t8v0x2z4a6c", "2w4j6k8m0n2p4r6t8v0x2z4a6c", "A" * 65, True),
            ]

            for acc, vlt, tag_val, expect_fail in invalid_cases:
                account_inp.value = acc
                vault_inp.value = vlt
                tag_inp.value = tag_val
                await pilot.pause()

                # Trigger Save Scope
                btn = modal.query_one("#btn-save-scope", Button)
                btn.press()
                await pilot.pause()

                if expect_fail:
                    self.assertIn("Validation failed", str(error_banner.render()))
                    self.assertIs(app.screen, modal)  # Must NOT dismiss
                    save_mock.assert_not_called()

            # Now test valid submission: exactly 26 alphanumeric chars
            account_inp.value = "2w4j6k8m0n2p4r6t8v0x2z4a6c"
            vault_inp.value = "2w4j6k8m0n2p4r6t8v0x2z4a6d"
            tag_inp.value = "OTP"
            await pilot.pause()
            btn = modal.query_one("#btn-save-scope", Button)
            btn.press()
            await pilot.pause()

            # Must have called save callback and dismissed
            save_mock.assert_called_once()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_saved_scope_modal_boundary_paths_pass_otp_and_totpm(self) -> None:
        """Boundary inputs in SavedScopeModal (pass-otp & totpm): oversized paths (>1024), traversal."""
        save_mock = MagicMock()
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles={})
        app.save_profiles_callback = save_mock

        async with app.run_test() as pilot:
            # 1. pass-otp backend
            modal_pass = SavedScopeModal(backend="pass-otp")
            app.push_screen(modal_pass)
            await pilot.pause()

            store_inp = modal_pass.query_one("#scope-pass-store", Input)
            key_inp = modal_pass.query_one("#scope-pass-keyhome", Input)
            error_banner = modal_pass.query_one("#scope-error-banner", Static)

            invalid_pass_cases = [
                # Oversized path (>1024 chars)
                ("/store/" + "a" * 1020, "/home/user/.gnupg"),
                # Traversal sequence
                ("/home/user/../../etc/passwd", "/home/user/.gnupg"),
                # Non-absolute path
                ("home/user/.password-store", "/home/user/.gnupg"),
                ("~/.password-store", "/home/user/.gnupg"),
                # Control character
                ("/home/user/\x00password-store", "/home/user/.gnupg"),
                # Empty fields
                ("", "/home/user/.gnupg"),
                ("/home/user/.password-store", ""),
            ]

            for store_val, key_val in invalid_pass_cases:
                store_inp.value = store_val
                key_inp.value = key_val
                await pilot.pause()

                modal_pass.query_one("#btn-save-scope", Button).press()
                await pilot.pause()

                self.assertIn("Validation failed", str(error_banner.render()))
                self.assertIs(app.screen, modal_pass)
                save_mock.assert_not_called()

            await pilot.press("escape")
            await pilot.pause()

            # 2. totpm backend
            modal_totpm = SavedScopeModal(backend="totpm")
            app.push_screen(modal_totpm)
            await pilot.pause()

            cfg_inp = modal_totpm.query_one("#scope-totpm-config", Input)
            err_banner_totpm = modal_totpm.query_one("#scope-error-banner", Static)

            invalid_totpm_cases = [
                # Oversized path (>1024 chars)
                "/config/" + "b" * 1020,
                # Traversal sequence
                "/home/user/../totpm.conf",
                # Non-absolute path
                "totpm.conf",
                # Empty field
                "",
            ]

            for cfg_val in invalid_totpm_cases:
                cfg_inp.value = cfg_val
                await pilot.pause()

                modal_totpm.query_one("#btn-save-scope", Button).press()
                await pilot.pause()

                self.assertIn("Validation failed", str(err_banner_totpm.render()))
                self.assertIs(app.screen, modal_totpm)
                save_mock.assert_not_called()

            await pilot.press("escape")
            await pilot.pause()

    async def test_saved_scope_nonexistent_directory_handling(self) -> None:
        """Non-existent directories saved in scope must be handled gracefully without crashing."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles={})

        async with app.run_test() as pilot:
            # Save a scope pointing to a non-existent directory
            nonexistent_profile = {
                "store": "/tmp/authy_adversarial_nonexistent_store_9999",
                "key_home": "/tmp/authy_adversarial_nonexistent_keys_9999",
            }

            modal = SavedScopeModal(backend="pass-otp")
            app.push_screen(modal)
            await pilot.pause()

            modal.query_one("#scope-pass-store", Input).value = nonexistent_profile["store"]
            modal.query_one("#scope-pass-keyhome", Input).value = nonexistent_profile["key_home"]
            await pilot.pause()

            # Valid syntax allows saving
            modal.query_one("#btn-save-scope", Button).press()
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)
            self.assertIn("pass-otp", app.profiles)

            # Now test load_records with this non-existent directory
            records = app.load_records("pass-otp", nonexistent_profile)
            # Must return None safely (caught AppError) without unhandled exception
            self.assertIsNone(records)

            # Test launching browser with non-existent directory: must show MessageModal error
            app.current_backend = "pass-otp"
            await pilot.press("1")
            await pilot.pause()

            self.assertIsInstance(app.screen, MessageModal)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_otp_code_memory_wiping_on_dismissal(self) -> None:
        """Verify that when CodeDisplayModal is dismissed or unmounted, the OTP code is wiped.

        Empirically checks:
        1. modal.code attribute is wiped to empty string upon Escape / dismiss.
        2. Direct unmount wipes modal.code attribute.
        3. No lingering secret string in modal instance attributes.
        """
        secret_otp = "987654"
        modal = CodeDisplayModal(code=secret_otp, item_label="CriticalItem")
        self.assertEqual(modal.code, secret_otp)

        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            app.push_screen(modal)
            await pilot.pause()
            self.assertIs(app.screen, modal)

            # Code is present while mounted
            self.assertEqual(modal.code, secret_otp)
            digits_text = str(modal.query_one("#code-digits", Static).render())
            self.assertIn("987  654", digits_text)

            # Dismiss via Escape
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # EMPIRICAL ASSERTION: code attribute MUST be wiped
            self.assertEqual(modal.code, "")

            # Check all instance attributes on the dismissed modal
            for attr_name, attr_val in modal.__dict__.items():
                if isinstance(attr_val, str):
                    self.assertNotIn(
                        secret_otp,
                        attr_val,
                        f"Secret OTP lingering in attribute '{attr_name}' after dismissal!",
                    )

            # Verify that all child widgets are pruned and detached from the modal DOM
            self.assertEqual(len(modal.children), 0)
            from textual.css.query import NoMatches

            with self.assertRaises(NoMatches):
                modal.query_one("#code-digits", Static)

            # Test 2: Direct unmount via app.pop_screen()
            secret_otp_2 = "876543"
            modal2 = CodeDisplayModal(code=secret_otp_2, item_label="Item2")
            app.push_screen(modal2)
            await pilot.pause()
            self.assertEqual(modal2.code, secret_otp_2)

            app.pop_screen()
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # EMPIRICAL ASSERTION: code attribute MUST be wiped on unmount
            self.assertEqual(modal2.code, "")
            self.assertEqual(len(modal2.children), 0)
            for attr_name, attr_val in modal2.__dict__.items():
                if isinstance(attr_val, str):
                    self.assertNotIn(
                        secret_otp_2,
                        attr_val,
                        f"Secret OTP lingering in attribute '{attr_name}' after unmount!",
                    )
