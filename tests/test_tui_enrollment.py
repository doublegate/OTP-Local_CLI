"""Tests for TUI Action 9 AddOtpModal and interactive OTP enrollment."""

import unittest
from unittest.mock import MagicMock, patch

from textual.widgets import Checkbox, Input, Static

from authy_local.tui import ActionListView, AddOtpModal, AuthyApp, CountdownBar, DashboardScreen


class TestTuiEnrollment(unittest.IsolatedAsyncioTestCase):
    """Integration test suite for TUI AddOtpModal and enrollment workflows."""

    def setUp(self) -> None:
        self.profiles = {
            "onepassword": {
                "account": "2w4j6k8m0n2p4r6t8v0x2z4a6a",
                "vault": "2w4j6k8m0n2p4r6t8v0x2z4a6v",
            },
            "pass-otp": {"store": "/tmp/test-store", "key_home": "/tmp/test-key-home"},
            "totpm": {"config": "/tmp/test-tpm.json"},
        }

    async def test_action_5_hotkey_opens_add_otp_modal(self) -> None:
        """Verify pressing '5' or 'a' on dashboard launches AddOtpModal."""
        app = AuthyApp(profiles=self.profiles)
        async with app.run_test() as pilot:
            self.assertIsInstance(app.screen, DashboardScreen)

            # Check sidebar has 9 options
            sidebar = app.screen.query_one(ActionListView)
            self.assertEqual(sidebar.option_count, 9)

            # Press '5'
            await pilot.press("5")
            await pilot.pause()
            self.assertIsInstance(app.screen, AddOtpModal)

            # Dismiss
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # Press 'a'
            await pilot.press("a")
            await pilot.pause()
            self.assertIsInstance(app.screen, AddOtpModal)
            await pilot.press("q")

    async def test_secret_input_activates_live_totp_preview(self) -> None:
        """Verify entering a valid Base32 secret activates live TOTP code and countdown bar."""
        app = AuthyApp(profiles=self.profiles)
        async with app.run_test() as pilot:
            await pilot.press("5")
            await pilot.pause()
            self.assertIsInstance(app.screen, AddOtpModal)
            modal = app.screen

            code_label = modal.query_one("#lbl-live-code", Static)
            self.assertEqual(str(code_label.render()), "------")

            # Input secret
            inp_secret = modal.query_one("#inp-otp-secret", Input)
            inp_secret.value = "JBSWY3DPEHPK3PXP"
            await pilot.pause()

            code_text = str(code_label.render())
            self.assertNotEqual(code_text, "------")
            self.assertEqual(len(code_text.replace(" ", "")), 6)

            # CountdownBar is active
            cbar = modal.query_one("#live-countdown-bar", CountdownBar)
            self.assertGreater(cbar.remaining_seconds, 0.0)

            await pilot.press("escape")

    async def test_uri_input_auto_fills_metadata_fields(self) -> None:
        """Verify entering an otpauth:// URI auto-populates issuer and account fields."""
        app = AuthyApp(profiles=self.profiles)
        async with app.run_test() as pilot:
            await pilot.press("5")
            await pilot.pause()
            modal = app.screen

            inp_secret = modal.query_one("#inp-otp-secret", Input)
            inp_secret.value = "otpauth://totp/GitHub:alice@example.com?secret=JBSWY3DPEHPK3PXP&issuer=GitHub&digits=6&period=30"
            await pilot.pause()

            self.assertEqual(modal.query_one("#inp-otp-issuer", Input).value, "GitHub")
            self.assertEqual(modal.query_one("#inp-otp-account", Input).value, "alice@example.com")
            self.assertEqual(modal.query_one("#inp-otp-digits", Input).value, "6")
            self.assertEqual(modal.query_one("#inp-otp-period", Input).value, "30")

            await pilot.press("escape")

    async def test_copy_test_code_and_toggle_mask(self) -> None:
        """Verify Copy Test Code invokes copy_code and Toggle Mask changes input password mode."""
        app = AuthyApp(profiles=self.profiles)
        async with app.run_test() as pilot:
            await pilot.press("5")
            await pilot.pause()
            modal = app.screen

            inp_secret = modal.query_one("#inp-otp-secret", Input)
            inp_secret.value = "JBSWY3DPEHPK3PXP"
            await pilot.pause()

            # Toggle mask
            self.assertTrue(inp_secret.password)
            modal.on_toggle_mask()
            self.assertFalse(inp_secret.password)
            modal.on_toggle_mask()
            self.assertTrue(inp_secret.password)

            # Copy test code
            with patch("authy_local.interaction.copy_code") as mock_copy:
                modal.action_copy_test_code()
                mock_copy.assert_called_once()
                copied_code = mock_copy.call_args[0][0]
                self.assertEqual(len(copied_code), 6)

            await pilot.press("escape")

    async def test_paste_clipboard_and_decode_file(self) -> None:
        """Verify clipboard paste button and file decode button populate secret input."""
        app = AuthyApp(profiles=self.profiles)
        async with app.run_test() as pilot:
            await pilot.press("5")
            await pilot.pause()
            modal = app.screen

            # Paste from clipboard mock
            with (
                patch("authy_local.enrollment.get_clipboard_image", return_value=b"FAKE_PNG"),
                patch(
                    "authy_local.enrollment.decode_qr_image_bytes",
                    return_value="otpauth://totp/Test:user?secret=JBSWY3DPEHPK3PXP",
                ),
            ):
                modal.on_paste_clipboard()
                await pilot.pause()
                self.assertEqual(
                    modal.query_one("#inp-otp-secret", Input).value,
                    "otpauth://totp/Test:user?secret=JBSWY3DPEHPK3PXP",
                )

            # Decode file mock
            modal.query_one("#inp-qr-file-path", Input).value = "/tmp/fake.png"
            with patch(
                "authy_local.enrollment.decode_qr_image_file", return_value="JBSWY3DPEHPK3PXP"
            ):
                modal.on_decode_file()
                await pilot.pause()
                self.assertEqual(
                    modal.query_one("#inp-otp-secret", Input).value, "JBSWY3DPEHPK3PXP"
                )

            await pilot.press("escape")

    async def test_enroll_save_dispatches_to_selected_backends(self) -> None:
        """Verify clicking Enroll and Save triggers backend enrollment across checked targets."""
        app = AuthyApp(profiles=self.profiles)
        async with app.run_test() as pilot:
            await pilot.press("5")
            await pilot.pause()
            modal = app.screen

            # Set secret and metadata
            modal.query_one("#inp-otp-secret", Input).value = "JBSWY3DPEHPK3PXP"
            modal.query_one("#inp-otp-issuer", Input).value = "Acme"
            modal.query_one("#inp-otp-account", Input).value = "alice"
            modal.query_one("#chk-onepassword", Checkbox).value = True
            modal.query_one("#chk-pass-otp", Checkbox).value = True
            modal.query_one("#chk-totpm", Checkbox).value = False
            await pilot.pause()

            with (
                patch(
                    "authy_local.backends.onepassword.enroll", return_value="item-123"
                ) as mock_op,
                patch(
                    "authy_local.backends.local.LocalScope",
                    return_value=MagicMock(backend="pass-otp"),
                ),
                patch("authy_local.backends.local.preflight"),
                patch("authy_local.backends.local.enroll") as mock_local,
            ):
                modal.on_enroll_save_pressed()
                await app.workers.wait_for_complete()
                await pilot.pause()

                mock_op.assert_called_once()
                self.assertIn("Acme (alice)", mock_op.call_args.kwargs["title"])
                self.assertIn("tags", mock_op.call_args.kwargs)
                self.assertEqual(mock_op.call_args.kwargs["tags"], "OTP")

                mock_local.assert_called_once()
                self.assertEqual(mock_local.call_args.args[0].backend, "pass-otp")

            # Modal dismisses back to dashboard on success
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)


if __name__ == "__main__":
    unittest.main()
