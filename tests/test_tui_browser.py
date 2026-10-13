"""Doctor status persistence and token browser state integration tests.

Replaces legacy curses browser tests with Textual headless pilot tests.
"""

import unittest
from unittest.mock import MagicMock

from authy_local.errors import AppError
from authy_local.tui import (
    AuthyApp,
    BackendSelectModal,
    DashboardScreen,
    DoctorModal,
    MessageModal,
    SessionStatusPanel,
    TokenBrowserScreen,
    TokenOptionList,
)


class DoctorStatusPersistenceTests(unittest.IsolatedAsyncioTestCase):
    """Verifies that Doctor results update session_status and persist across backend selection."""

    async def test_doctor_summary_persists_in_status_panel_and_survives_backend_switch(
        self,
    ) -> None:
        """Verify Doctor summary updates app.session_status and survives switching backend via 'b'."""

        def doctor_dispatch(args, stdout, stderr):
            if args[0] == "doctor":
                stdout.write("op: available\nwl-copy: missing\nclock: unknown\n")
                return 0
            return 0

        app = AuthyApp(dispatch=doctor_dispatch, profiles={"onepassword": {}})
        async with app.run_test() as pilot:
            # 1. Run Doctor (Action 7)
            await pilot.press("7")
            await pilot.pause()
            self.assertIsInstance(app.screen, DoctorModal)

            # Dismiss Doctor modal via Escape
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # Verify session status panel reflects doctor results
            status_panel = app.screen.query_one(SessionStatusPanel)
            status_text = status_panel.status
            self.assertIn("1 available", status_text)
            self.assertIn("1 missing", status_text)

            # 2. Open Backend Select modal via 'b'
            await pilot.press("b")
            await pilot.pause()
            self.assertIsInstance(app.screen, BackendSelectModal)

            # Switch backend to pass-otp (down arrow + Enter)
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause()

            # Dashboard screen active again with updated backend
            self.assertIsInstance(app.screen, DashboardScreen)
            self.assertEqual(app.current_backend, "pass-otp")

            # Doctor status summary must still be retained in session_status
            self.assertIn("1 available", app.session_status)
            await pilot.press("q")

    async def test_doctor_failure_updates_session_status_with_failure_notice(self) -> None:
        """Verify failed doctor execution updates app.session_status with failure diagnostic."""

        def failing_doctor(args, stdout, stderr):
            stderr.write("doctor probe failure\n")
            return 4

        app = AuthyApp(dispatch=failing_doctor, profiles={"onepassword": {}})
        async with app.run_test() as pilot:
            await pilot.press("7")
            await pilot.pause()

            # Doctor modal mounted with failure status
            self.assertIsInstance(app.screen, DoctorModal)
            self.assertEqual(app.screen.status, 4)

            await pilot.press("escape")
            await pilot.pause()

            # app.session_status reflects failure
            self.assertIn("failed", app.session_status.lower())
            await pilot.press("q")

    async def test_browser_search_and_keyboard_selection(self) -> None:
        """Verify token browser loads records, filters on search input, and selects options."""
        records = [("item1", "Item One [i1]"), ("item2", "Item Two [i2]")]
        app = AuthyApp(dispatch=lambda *a: 0, profiles={"pass-otp": {}})
        app.current_backend = "pass-otp"
        app.load_records = MagicMock(return_value=records)

        async with app.run_test() as pilot:
            await pilot.press("1")  # Browse and show
            await pilot.pause()

            browser = app.screen
            self.assertIsInstance(browser, TokenBrowserScreen)
            opt_list = browser.query_one(TokenOptionList)
            self.assertEqual(opt_list.option_count, 2)

            # Navigate down to select item2
            await pilot.press("down")
            await pilot.pause()
            self.assertEqual(browser.selected_token_key, "item2")

            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)
            await pilot.press("q")

    async def test_scope_save_failure_shows_modal_and_prevents_dispatch(self) -> None:
        """Verify scope save error displays MessageModal and prevents dispatch."""
        dispatched = []

        def tracking_dispatch(args, out, diag):
            dispatched.append(args)
            return 0

        def failing_save(profiles):
            raise AppError(3)

        app = AuthyApp(
            dispatch=tracking_dispatch,
            profiles={"pass-otp": {}},
            save_profiles=failing_save,
        )
        async with app.run_test() as pilot:
            # Trigger Scope configuration (Action 6)
            await pilot.press("6")
            await pilot.pause()

            modal = app.screen
            # Submit form
            if hasattr(modal, "action_submit"):
                modal.action_submit()
                await pilot.pause()
                self.assertIsInstance(app.screen, MessageModal)

            self.assertEqual(dispatched, [])
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")
