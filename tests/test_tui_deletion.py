"""Token browser deletion error handling and state preservation suite.

Replaces legacy curses deletion tests with Textual headless pilot tests.
"""

import unittest
from unittest.mock import MagicMock

from textual.widgets import Input

from authy_local.errors import AppError
from authy_local.tui import (
    AuthyApp,
    DeleteConfirmModal,
    MessageModal,
    TokenBrowserScreen,
    TokenOptionList,
)


class TestBrowserDeletionSafety(unittest.IsolatedAsyncioTestCase):
    """Verifies error handling and state preservation during entry deletion."""

    async def test_deletion_backend_failure_shows_message_and_preserves_item(self) -> None:
        """Verify that when backend deletion fails, an error dialog displays and the item is retained."""
        records = [("work/vpn", "work/vpn"), ("personal/email", "personal/email")]
        app = AuthyApp(dispatch=lambda *args: 0, profiles={"pass-otp": {}})
        app.current_backend = "pass-otp"
        app.load_records = MagicMock(return_value=records)

        # Mock delete_record to fail with False
        app.delete_record = MagicMock(return_value=False)

        async with app.run_test() as pilot:
            await pilot.press("1")  # Browse and show
            await pilot.pause()

            browser = app.screen
            self.assertIsInstance(browser, TokenBrowserScreen)
            opt_list = browser.query_one(TokenOptionList)
            self.assertEqual(opt_list.option_count, 2)

            # Press 'd' to initiate delete
            await pilot.press("d")
            await pilot.pause()
            self.assertIsInstance(app.screen, DeleteConfirmModal)

            # Type exact DELETE and submit
            del_modal = app.screen
            del_modal.query_one("#delete-confirm-input", Input).value = "DELETE"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            # Error dialog must display
            self.assertIsInstance(app.screen, MessageModal)
            await pilot.press("escape")
            await pilot.pause()

            # Browser is restored and the item is NOT removed
            self.assertIsInstance(app.screen, TokenBrowserScreen)
            self.assertEqual(opt_list.option_count, 2)
            self.assertEqual(browser.selected_token_key, "work/vpn")

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_deletion_exception_shows_sanitized_modal_without_crashing(self) -> None:
        """Verify that an unexpected exception during deletion is caught and presented cleanly."""
        records = [("work/vpn", "work/vpn")]
        app = AuthyApp(dispatch=lambda *args: 0, profiles={"pass-otp": {}})
        app.current_backend = "pass-otp"
        app.load_records = MagicMock(return_value=records)
        app.delete_record = MagicMock(side_effect=AppError(4))

        async with app.run_test() as pilot:
            await pilot.press("1")
            await pilot.pause()

            await pilot.press("d")
            await pilot.pause()

            del_modal = app.screen
            del_modal.query_one("#delete-confirm-input", Input).value = "DELETE"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            # App must remain alive and show MessageModal
            self.assertTrue(app.is_running)
            self.assertIsInstance(app.screen, MessageModal)

            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, TokenBrowserScreen)

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_deletion_cancelled_preserves_browser_state(self) -> None:
        """Verify pressing escape in DeleteConfirmModal cancels deletion without changes."""
        records = [("work/vpn", "work/vpn")]
        app = AuthyApp(dispatch=lambda *args: 0, profiles={"pass-otp": {}})
        app.current_backend = "pass-otp"
        app.load_records = MagicMock(return_value=records)
        app.delete_record = MagicMock()

        async with app.run_test() as pilot:
            await pilot.press("1")
            await pilot.pause()

            await pilot.press("d")
            await pilot.pause()
            self.assertIsInstance(app.screen, DeleteConfirmModal)

            # Cancel via Escape
            await pilot.press("escape")
            await pilot.pause()

            self.assertIsInstance(app.screen, TokenBrowserScreen)
            app.delete_record.assert_not_called()

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")
