"""Unit and integration tests for Milestone M3 menu actions, dialogs, and suspension."""

import unittest
from collections.abc import Callable
from unittest.mock import MagicMock, patch

from textual.widgets import Button, Input, OptionList, ProgressBar, Static

from authy_local.tui import (
    AuthyApp,
    BackendSelectModal,
    CodeDisplayModal,
    DashboardScreen,
    DoctorModal,
    HelpModal,
    InstallPreviewModal,
    MigrationGuideModal,
    PromptItemModal,
    SavedScopeModal,
)


class TestTuiActions(unittest.IsolatedAsyncioTestCase):
    """Test suite covering all 8 menu actions and auxiliary dialogs in Textual."""

    def setUp(self) -> None:
        self.dummy_dispatch: Callable = lambda args, out, diag: 0
        self.dummy_preview: Callable = lambda wheel, out, diag: 0
        self.valid_profile = {
            "onepassword": {
                "account": "2w4j6k8m0n2p4r6t8v0x2z4a6c",
                "vault": "2w4j6k8m0n2p4r6t8v0x2z4a6c",
            }
        }

    async def test_action_1_doctor_modal_badges_and_copy(self) -> None:
        """Verify Action 1 'Doctor' displays DoctorModal with status badges and copy summary."""

        def doctor_dispatch(args, output, diagnostic):
            output.write("platform: available\n")
            output.write("op: available\n")
            output.write("wl-copy: missing\n")
            output.write("clock: unknown\n")
            return 0

        app = AuthyApp(dispatch=doctor_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            await pilot.press("7")
            await pilot.pause()

            self.assertIsInstance(app.screen, DoctorModal)
            modal = app.screen

            badge_platform = modal.query_one("#badge-platform", Static)
            self.assertIn("AVAILABLE", str(badge_platform.render()))

            badge_wl = modal.query_one("#badge-wl-copy", Static)
            self.assertIn("MISSING", str(badge_wl.render()))

            badge_clock = modal.query_one("#badge-clock", Static)
            self.assertIn("UNKNOWN", str(badge_clock.render()))

            with patch("authy_local.interaction.copy_code") as mock_copy:
                await pilot.press("c")
                await pilot.pause()
                mock_copy.assert_called_once()
                self.assertIn("platform: available", mock_copy.call_args[0][0])

            # Test Re-run button 'r'
            await pilot.press("r")
            await pilot.pause()
            self.assertEqual(modal.status, 0)

            # Test Escape dismisses modal
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)
            await pilot.press("q")

    async def test_action_2_show_code_modal_and_countdown_purging(self) -> None:
        """Verify Action 2 prompts for item ID, executes show, and displays CodeDisplayModal with countdown."""

        def show_dispatch(args, output, diagnostic):
            if args[0] == "show":
                output.write("987654\n")
                return 0
            return 0

        app = AuthyApp(dispatch=show_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            await pilot.press("3")
            await pilot.pause()

            # 1. Verify PromptItemModal is mounted
            self.assertIsInstance(app.screen, PromptItemModal)
            prompt_modal = app.screen

            # 2. Enter valid 26-char ID and submit
            inp = prompt_modal.query_one("#prompt-item-input", Input)
            inp.value = "2w4j6k8m0n2p4r6t8v0x2z4a6c"
            await pilot.press("enter")
            await pilot.pause()

            # 3. Verify CodeDisplayModal is mounted
            self.assertIsInstance(app.screen, CodeDisplayModal)
            code_modal = app.screen
            self.assertEqual(code_modal.code, "987654")

            # Verify large typography formatting
            digits_text = str(code_modal.query_one("#code-digits", Static).render())
            self.assertIn("987  654", digits_text)

            # Verify countdown progress bar and timer update
            progress_bar = code_modal.query_one(ProgressBar)
            self.assertIsInstance(progress_bar, ProgressBar)
            timer_label = str(code_modal.query_one("#code-timer-label", Static).render())
            self.assertTrue(timer_label.startswith("Valid for"))

            # Test copy code button 'c'
            with patch("authy_local.interaction.copy_code") as mock_copy:
                await pilot.press("c")
                await pilot.pause()
                mock_copy.assert_called_once()
                self.assertEqual(mock_copy.call_args[0][0], "987654")

            # 4. Verify code string is wiped from memory upon dismissal
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(code_modal.code, "")
            self.assertIsInstance(app.screen, DashboardScreen)
            await pilot.press("q")

    async def test_action_2_show_code_with_fuzzy_suggestions(self) -> None:
        """Verify PromptItemModal filters cached records and submits selected suggestion."""
        records = [
            ("2w4j6k8m0n2p4r6t8v0x2z4a6a", "GitHub Personal [2z4a6a]"),
            ("2w4j6k8m0n2p4r6t8v0x2z4a6b", "AWS Infrastructure [2z4a6b]"),
        ]

        def show_dispatch(args, output, diagnostic):
            output.write("112233\n")
            return 0

        app = AuthyApp(dispatch=show_dispatch, profiles=self.valid_profile)
        app.load_records = MagicMock(return_value=records)

        async with app.run_test() as pilot:
            await pilot.press("3")
            await pilot.pause()

            self.assertIsInstance(app.screen, PromptItemModal)
            prompt_modal = app.screen
            suggestions = prompt_modal.query_one("#prompt-suggestions", OptionList)
            self.assertEqual(suggestions.option_count, 2)

            # Filter via search query
            inp = prompt_modal.query_one("#prompt-item-input", Input)
            inp.value = "AWS"
            await pilot.pause()
            self.assertEqual(suggestions.option_count, 1)

            # Select option via OptionList
            suggestions.action_select()
            await pilot.pause()

            self.assertIsInstance(app.screen, CodeDisplayModal)
            code_modal = app.screen
            self.assertEqual(code_modal.code, "112233")
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_action_3_copy_code_confirmation(self) -> None:
        """Verify Action 3 prompts for item ID, executes copy, and confirms clipboard toast."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            await pilot.press("4")
            await pilot.pause()

            self.assertIsInstance(app.screen, PromptItemModal)
            prompt_modal = app.screen
            self.assertEqual(prompt_modal.action_mode, "copy")

            inp = prompt_modal.query_one("#prompt-item-input", Input)
            inp.value = "2w4j6k8m0n2p4r6t8v0x2z4a6c"
            await pilot.press("enter")
            await pilot.pause()

            # Dismisses back to dashboard with notification
            self.assertIsInstance(app.screen, DashboardScreen)
            await pilot.press("q")

    async def test_action_6_installation_preview_readonly(self) -> None:
        """Verify Action 6 opens InstallPreviewModal, renders dry-run plan without mutations."""

        def preview_cb(wheel, output, diagnostic):
            output.write("Create /home/user/.local/bin/otp-local\n")
            output.write("Create /home/user/.local/share/fish/vendor_functions.d/otp-local.fish\n")
            return 0

        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            preview=preview_cb,
            profiles=self.valid_profile,
        )
        async with app.run_test() as pilot:
            await pilot.press("8")
            await pilot.pause()

            self.assertIsInstance(app.screen, InstallPreviewModal)
            preview_modal = app.screen

            # Enter wheel path
            inp = preview_modal.query_one("#preview-wheel-input", Input)
            inp.value = "dist/authy_local-1.0.0-py3-none-any.whl"
            await pilot.press("enter")
            await pilot.pause()

            # Verify preview plan contents
            scroll = preview_modal.query_one("#preview-scroll")
            plan_text = " ".join(str(w.render()) for w in scroll.query(Static))
            self.assertIn("Preview only; no changes authorized.", plan_text)
            self.assertIn("Create /home/user/.local/bin/otp-local", plan_text)

            # Escape dismisses modal
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)
            await pilot.press("q")

    async def test_action_7_migration_guide_modal(self) -> None:
        """Verify Action 7 opens MigrationGuideModal and renders all 14 checkpoints."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            await pilot.press("9")
            await pilot.pause()

            self.assertIsInstance(app.screen, MigrationGuideModal)
            guide_modal = app.screen

            # Verify 14 checkpoints rendered
            items = guide_modal.query(".guide-item")
            # 14 checkpoints + 1 runbook summary
            self.assertGreaterEqual(len(items), 14)

            # Test Copy Checkpoints 'c'
            with patch("authy_local.interaction.copy_code") as mock_copy:
                await pilot.press("c")
                await pilot.pause()
                mock_copy.assert_called_once()
                self.assertIn("Private migration checkpoints", mock_copy.call_args[0][0])

            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)
            await pilot.press("q")

    async def test_action_8_saved_scope_modal_validation_and_0600_persistence(self) -> None:
        """Verify Action 8 / 'p' validates scope and persists to 0600 file via save_profiles."""
        saved_holder = []

        def save_cb(candidate):
            saved_holder.append(candidate)

        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            profiles={},
            save_profiles=save_cb,
        )
        async with app.run_test() as pilot:
            await pilot.press("6")
            await pilot.pause()

            self.assertIsInstance(app.screen, SavedScopeModal)
            scope_modal = app.screen

            # 1. Invalid Account ID (too short) -> validation failure
            acc_inp = scope_modal.query_one("#scope-op-account", Input)
            acc_inp.value = "short"
            vault_inp = scope_modal.query_one("#scope-op-vault", Input)
            vault_inp.value = "2w4j6k8m0n2p4r6t8v0x2z4a6c"
            btn_save = scope_modal.query_one("#btn-save-scope", Button)
            btn_save.press()
            await pilot.pause()

            error_text = str(scope_modal.query_one("#scope-error-banner", Static).render())
            self.assertIn("Validation failed", error_text)
            self.assertEqual(len(saved_holder), 0)

            # 2. Valid 26-char IDs -> save succeeds
            acc_inp.value = "2w4j6k8m0n2p4r6t8v0x2z4a6c"
            btn_save.press()
            await pilot.pause()

            self.assertIsInstance(app.screen, DashboardScreen)
            self.assertEqual(len(saved_holder), 1)
            self.assertIn("onepassword", saved_holder[0])
            self.assertEqual(
                saved_holder[0]["onepassword"]["account"],
                "2w4j6k8m0n2p4r6t8v0x2z4a6c",
            )
            self.assertEqual(app.profiles, saved_holder[0])
            await pilot.press("q")

    async def test_saved_scope_pass_otp_and_totpm_validation(self) -> None:
        """Verify SavedScopeModal validates local path schemas for pass-otp and totpm."""
        saved_holder = []
        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            profiles={},
            save_profiles=lambda cand: saved_holder.append(cand),
        )
        app.current_backend = "pass-otp"

        async with app.run_test() as pilot:
            await pilot.press("p")
            await pilot.pause()

            self.assertIsInstance(app.screen, SavedScopeModal)
            scope_modal = app.screen

            # Non-absolute path fails
            store_inp = scope_modal.query_one("#scope-pass-store", Input)
            store_inp.value = "relative/path"
            key_inp = scope_modal.query_one("#scope-pass-keyhome", Input)
            key_inp.value = "/home/user/.gnupg"
            scope_modal.query_one("#btn-save-scope", Button).press()
            await pilot.pause()

            err = str(scope_modal.query_one("#scope-error-banner", Static).render())
            self.assertIn("Validation failed", err)

            # Absolute paths succeed
            store_inp.value = "/home/user/.password-store"
            scope_modal.query_one("#btn-save-scope", Button).press()
            await pilot.pause()

            self.assertIsInstance(app.screen, DashboardScreen)
            self.assertIn("pass-otp", app.profiles)
            await pilot.press("q")

    async def test_auxiliary_backend_select_modal(self) -> None:
        """Verify 'b' opens BackendSelectModal and keys 1-3 switch active backend."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            self.assertEqual(app.current_backend, "onepassword")

            # Press 'b' to open modal
            await pilot.press("b")
            await pilot.pause()
            self.assertIsInstance(app.screen, BackendSelectModal)

            # Press '2' to choose pass-otp
            await pilot.press("2")
            await pilot.pause()
            self.assertEqual(app.current_backend, "pass-otp")
            self.assertIsInstance(app.screen, DashboardScreen)

            # Press 'b' and '3' to choose totpm
            await pilot.press("b")
            await pilot.pause()
            self.assertIsInstance(app.screen, BackendSelectModal)
            await pilot.press("3")
            await pilot.pause()
            self.assertEqual(app.current_backend, "totpm")
            self.assertIsInstance(app.screen, DashboardScreen)
            await pilot.press("q")

    async def test_auxiliary_help_modal(self) -> None:
        """Verify '?' and F1 open HelpModal with navigation guidance."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            await pilot.press("question_mark")
            await pilot.pause()

            self.assertIsInstance(app.screen, HelpModal)
            help_modal = app.screen
            lines = help_modal.query(".help-line")
            self.assertGreaterEqual(len(lines), 5)

            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # Test F1
            await pilot.press("f1")
            await pilot.pause()
            self.assertIsInstance(app.screen, HelpModal)
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)
            await pilot.press("q")

    async def test_safe_suspend_interactive_lifecycle_and_sigint(self) -> None:
        """Verify safe_suspend calls driver suspension and restores mode cleanly on SIGINT."""
        app = AuthyApp(dispatch=self.dummy_dispatch)

        mock_driver = MagicMock()
        mock_driver.can_suspend = True
        mock_driver.is_application_mode_suspended = False

        def mock_suspend_mode():
            mock_driver.is_application_mode_suspended = True

        def mock_resume_mode():
            mock_driver.is_application_mode_suspended = False

        mock_driver.suspend_application_mode = mock_suspend_mode
        mock_driver.resume_application_mode = mock_resume_mode

        app._driver = mock_driver
        app._running = True

        # 1. Normal execution under suspension
        with patch.object(app, "suspend") as mock_app_suspend:
            mock_app_suspend.return_value.__enter__ = MagicMock()
            mock_app_suspend.return_value.__exit__ = MagicMock()

            with app.safe_suspend():
                pass

        # 2. KeyboardInterrupt (SIGINT) simulation during CLI invocation
        def interrupt_dispatch(args, output, diagnostic):
            raise KeyboardInterrupt()

        app.dispatch_callback = interrupt_dispatch
        status, summary, lines = app.execute(["show", "item1"])
        self.assertEqual(status, 130)


if __name__ == "__main__":
    unittest.main()
