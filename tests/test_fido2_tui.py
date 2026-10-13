"""Automated UI and interaction tests for FIDO2 Textual touch modal and enrollment."""

import asyncio
import os
import unittest
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import Button, Checkbox, OptionList, Static

from authy_local.cli import main, parser
from authy_local.tui import (
    AddOtpModal,
    AuthyApp,
    BackendSelectModal,
    CountdownBar,
    DashboardScreen,
    Fido2TouchModal,
)


class DummyModalHostApp(App[bool | None]):
    """Host application for isolated modal testing."""

    def __init__(self, modal_to_test, **kwargs) -> None:
        super().__init__(**kwargs)
        self.modal_to_test = modal_to_test
        self.result: bool | None = None

    def compose(self) -> ComposeResult:
        yield Static("Modal Host Screen")

    def on_mount(self) -> None:
        def on_dismiss(res: bool | None) -> None:
            self.result = res

        self.push_screen(self.modal_to_test, on_dismiss)


class TestFido2Tui(unittest.IsolatedAsyncioTestCase):
    """Test suite covering Fido2TouchModal, BackendSelectModal, and AddOtpModal integration."""

    def setUp(self) -> None:
        self.dummy_env = {"HOME": "/tmp/test_fido2_tui_home"}
        os.makedirs(self.dummy_env["HOME"], exist_ok=True)

    async def test_touch_modal_initial_render_and_pulsing_frames(self) -> None:
        """Verify Fido2TouchModal renders title, account, countdown bar, and cycles pulse frames."""
        modal = Fido2TouchModal(account="test_work_key", timeout_seconds=30.0)
        app = DummyModalHostApp(modal)

        async with app.run_test() as pilot:
            await pilot.pause()

            self.assertIsInstance(app.screen, Fido2TouchModal)
            title = modal.query_one("#fido2-touch-title", Static)
            self.assertIn("FIDO2 Security Key Required", str(title.render()))

            acct_lbl = modal.query_one("#fido2-touch-account", Static)
            self.assertIn("test_work_key", str(acct_lbl.render()))

            cbar = modal.query_one("#fido2-touch-bar", CountdownBar)
            self.assertAlmostEqual(cbar.remaining_seconds, 30.0)

            pulse_widget = modal.query_one("#fido2-touch-pulse", Static)
            initial_render = str(pulse_widget.render())
            self.assertIn("TOUCH SECURITY KEY", initial_render)

            # Advance ticks to verify visual pulsing frames progression
            modal._tick()
            self.assertEqual(modal.pulse_step, 1)
            self.assertAlmostEqual(modal.remaining_seconds, 29.75)
            self.assertAlmostEqual(cbar.remaining_seconds, 29.75)

            modal._tick()
            self.assertEqual(modal.pulse_step, 2)
            self.assertAlmostEqual(modal.remaining_seconds, 29.5)

            # Test cancel dismiss
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(app.result, False)

    async def test_touch_modal_simulate_touch_key(self) -> None:
        """Verify pressing 't' or clicking touch button dismisses modal with True."""
        modal = Fido2TouchModal(account="alice_prod")
        app = DummyModalHostApp(modal)

        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertIsInstance(app.screen, Fido2TouchModal)

            await pilot.press("t")
            await pilot.pause()
            self.assertEqual(app.result, True)

    async def test_touch_modal_button_click_and_touch_received_callback(self) -> None:
        """Verify clicking touch button or programmatic callback dismisses modal with True."""
        modal1 = Fido2TouchModal(account="bob_dev")
        app1 = DummyModalHostApp(modal1)

        async with app1.run_test() as pilot:
            await pilot.pause()
            btn_touch = modal1.query_one("#btn-simulate-touch", Button)
            btn_touch.press()
            await pilot.pause()
            self.assertEqual(app1.result, True)

        # Test direct device callback invocation
        modal2 = Fido2TouchModal(account="charlie_corp")
        app2 = DummyModalHostApp(modal2)

        async with app2.run_test() as pilot:
            await pilot.pause()
            modal2.touch_received()
            await pilot.pause()
            self.assertEqual(app2.result, True)

    async def test_touch_modal_timeout_expiration(self) -> None:
        """Verify timeout expiration dismisses modal with False when countdown reaches 0."""
        modal = Fido2TouchModal(account="timeout_key", timeout_seconds=1.0)
        app = DummyModalHostApp(modal)

        async with app.run_test() as pilot:
            await pilot.pause()
            # Simulate 4 ticks (4 x 0.25s = 1.0s)
            modal._tick()
            modal._tick()
            modal._tick()
            modal._tick()
            await pilot.pause()

            self.assertEqual(app.result, False)

    async def test_backend_select_modal_fido2_option(self) -> None:
        """Verify option 8 exists and pressing 8 selects 'fido2' backend."""
        modal = BackendSelectModal(current_backend="onepassword")
        chosen_backend: str | None = None

        def on_dismiss(res: str | None) -> None:
            nonlocal chosen_backend
            chosen_backend = res

        class HostApp(App[None]):
            def compose(self) -> ComposeResult:
                yield Static("Host")

            def on_mount(self) -> None:
                self.push_screen(modal, on_dismiss)

        app = HostApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            opt_list = modal.query_one("#backend-select-list", OptionList)
            self.assertEqual(opt_list.option_count, 8)

            # Hotkey '8' selection
            await pilot.press("8")
            await pilot.pause()
            self.assertEqual(app.current_backend, "fido2")

    async def test_add_otp_modal_fido2_enrollment(self) -> None:
        """Verify AddOtpModal contains chk-fido2 and enrolls to fido2 backend upon save."""
        modal = AddOtpModal(current_backend="fido2")

        class HostApp(App[None]):
            session_status: str = ""

            def compose(self) -> ComposeResult:
                yield Static("Host")

            def on_mount(self) -> None:
                self.push_screen(modal)

        app = HostApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            chk_fido2 = modal.query_one("#chk-fido2", Checkbox)
            self.assertTrue(chk_fido2.value)

            # Input valid secret and token names
            modal.query_one("#inp-otp-secret").value = "JBSWY3DPEHPK3PXP"
            modal.query_one("#inp-otp-issuer").value = "TestIssuer"
            modal.query_one("#inp-otp-account").value = "test_user"

            # Uncheck other backends to isolate fido2
            for b_id in (
                "#chk-onepassword",
                "#chk-pass-otp",
                "#chk-totpm",
                "#chk-keychain",
                "#chk-dpapi",
            ):
                modal.query_one(b_id, Checkbox).value = False

            with patch("authy_local.backends.fido2.fido2_enroll") as mock_enroll:
                btn_save = modal.query_one("#btn-enroll-save", Button)
                btn_save.press()
                await pilot.pause()
                await asyncio.sleep(0.1)

                mock_enroll.assert_called_once()
                args, _ = mock_enroll.call_args
                self.assertEqual(args[0], "test_user")
                self.assertEqual(args[1], "JBSWY3DPEHPK3PXP")

    def test_cli_enroll_fido2_flag_and_backup_token_flag(self) -> None:
        """Verify CLI flags --fido2 and --backup-token are parsed and routed correctly."""
        p = parser()

        # 1. Normal --fido2 flag
        args1 = p.parse_args(
            ["enroll", "--apply", "--fido2", "--account", "acct1", "--title", "Test"]
        )
        self.assertTrue(args1.fido2)
        self.assertFalse(args1.backup_token)

        # 2. Backup token flag
        args2 = p.parse_args(
            ["enroll", "--apply", "--fido2", "--backup-token", "--account", "acct2"]
        )
        self.assertTrue(args2.fido2)
        self.assertTrue(args2.backup_token)

        # 3. Test execution routing to fido2_enroll
        with (
            patch("authy_local.cli.has_terminal", return_value=True),
            patch("getpass.getpass", side_effect=["JBSWY3DPEHPK3PXP", "JBSWY3DPEHPK3PXP"]),
            patch("authy_local.backends.fido2.fido2_enroll") as mock_enroll,
        ):
            code = main(["enroll", "--apply", "--fido2", "--account", "acct1"])
            self.assertEqual(code, 0)
            mock_enroll.assert_called_once_with("acct1", "JBSWY3DPEHPK3PXP", unittest.mock.ANY)

        # 4. Test execution routing to fido2_add_backup_token
        with (
            patch("authy_local.cli.has_terminal", return_value=True),
            patch("getpass.getpass", side_effect=["JBSWY3DPEHPK3PXP", "JBSWY3DPEHPK3PXP"]),
            patch("authy_local.backends.fido2.fido2_add_backup_token") as mock_backup,
        ):
            code = main(
                ["enroll", "--apply", "--fido2", "--backup-token", "--account", "acct_backup"]
            )
            self.assertEqual(code, 0)
            mock_backup.assert_called_once_with(
                "acct_backup", "JBSWY3DPEHPK3PXP", unittest.mock.ANY
            )

        # 5. Invalid combinations
        with patch("authy_local.cli.has_terminal", return_value=True):
            # Conflicting backend
            err_code = main(
                [
                    "enroll",
                    "--apply",
                    "--backend",
                    "pass-otp",
                    "--fido2",
                    "--account",
                    "err",
                ]
            )
            self.assertEqual(err_code, 2)

            # Backup token on non-fido2 backend
            err_code2 = main(
                [
                    "enroll",
                    "--apply",
                    "--backend",
                    "pass-otp",
                    "--backup-token",
                    "--account",
                    "err",
                ]
            )
            self.assertEqual(err_code2, 2)

    async def test_fido2_device_disconnect_and_adversarial_handling(self) -> None:
        """Verify graceful error reporting when FIDO2 hardware disconnects or times out in TUI."""

        def fail_dispatch(args, output, diagnostic):
            diagnostic.write("Security key not detected or disconnected during assertion.\n")
            return 3

        app = AuthyApp(dispatch=fail_dispatch, profiles={})
        app.current_backend = "fido2"

        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # Execute action expecting touch prompt and error handling
            with patch.object(app, "load_records", return_value=[("mock_key", "Mock Key")]):
                # Trigger action 3 (Show code)
                await pilot.press("3")
                await pilot.pause()

                # In PromptItemModal, select the item
                await pilot.press("enter")
                await pilot.pause()
                await asyncio.sleep(0.1)

                # Verify application remains running and didn't crash
                self.assertTrue(app.is_running)


if __name__ == "__main__":
    unittest.main()
