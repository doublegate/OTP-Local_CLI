"""Dashboard Textual component and layout integration tests.

Replaces legacy curses dashboard tests with Textual headless pilot tests.
"""

import unittest

from authy_local.tui import (
    ActionListView,
    AuthyApp,
    BackendSelectModal,
    DashboardScreen,
    DetailWorkspace,
    HeaderBar,
    HelpModal,
    KeyboardFooter,
    SessionStatusPanel,
)


class DashboardTextualTests(unittest.IsolatedAsyncioTestCase):
    """Verifies DashboardScreen panel composition, layout, navigation, and backend selection."""

    def setUp(self) -> None:
        self.profiles = {"onepassword": {"account": "a" * 26, "vault": "v" * 26}}

    async def test_dashboard_has_panels_and_truthful_status(self) -> None:
        """Verify dashboard widgets render panels, title, backend badge, and unauthenticated status."""
        app = AuthyApp(dispatch=lambda *a: 0, profiles=self.profiles)
        async with app.run_test() as pilot:
            screen = app.screen
            self.assertIsInstance(screen, DashboardScreen)

            self.assertIsNotNone(screen.query_one(HeaderBar))
            self.assertIsNotNone(screen.query_one(SessionStatusPanel))
            self.assertIsNotNone(screen.query_one(ActionListView))
            self.assertIsNotNone(screen.query_one(DetailWorkspace))
            self.assertIsNotNone(screen.query_one(KeyboardFooter))

            status_panel = screen.query_one(SessionStatusPanel)
            self.assertIn("not checked", status_panel.status.lower())
            self.assertNotIn("authenticated", status_panel.status.lower())

            header = screen.query_one(HeaderBar)
            self.assertEqual(header.backend, "onepassword")

            await pilot.press("q")

    async def test_dashboard_keyboard_navigation(self) -> None:
        """Verify navigation via keyboard moves cursor in ActionListView and updates detail."""
        app = AuthyApp(dispatch=lambda *a: 0, profiles=self.profiles)
        async with app.run_test() as pilot:
            action_list = app.screen.query_one(ActionListView)
            initial_index = action_list.highlighted
            self.assertEqual(initial_index, 0)

            await pilot.press("down")
            await pilot.pause()
            self.assertEqual(action_list.highlighted, 1)

            await pilot.press("up")
            await pilot.pause()
            self.assertEqual(action_list.highlighted, 0)

            await pilot.press("q")

    async def test_backend_picker_changes_dashboard_without_backend_calls(self) -> None:
        """Verify pressing 'b' opens BackendSelectModal and switching updates dashboard backend."""
        backend_called = []

        def tracking_dispatch(args, out, diag):
            backend_called.append(args)
            return 0

        app = AuthyApp(dispatch=tracking_dispatch, profiles=self.profiles)
        async with app.run_test() as pilot:
            self.assertEqual(app.current_backend, "onepassword")

            await pilot.press("b")
            await pilot.pause()
            self.assertIsInstance(app.screen, BackendSelectModal)

            # Switch to pass-otp (down + enter)
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause()

            self.assertIsInstance(app.screen, DashboardScreen)
            self.assertEqual(app.current_backend, "pass-otp")
            self.assertEqual(backend_called, [])

            await pilot.press("q")

    async def test_help_modal_shortcuts_display_and_dismiss(self) -> None:
        """Verify '?' key displays shortcuts HelpOverlay and dismisses on Escape."""
        app = AuthyApp(dispatch=lambda *a: 0, profiles=self.profiles)
        async with app.run_test() as pilot:
            await pilot.press("?")
            await pilot.pause()

            self.assertIsInstance(app.screen, HelpModal)

            await pilot.press("escape")
            await pilot.pause()

            self.assertIsInstance(app.screen, DashboardScreen)
            await pilot.press("q")
