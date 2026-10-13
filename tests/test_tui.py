"""Modern Textual safety, output sanitization, and error isolation test suite.

Replaces legacy curses mock tests with Textual headless pilot tests.
"""

import unittest
from unittest.mock import MagicMock, patch

from textual.widgets import Static

from authy_local.errors import AppError
from authy_local.tui import (
    AuthyApp,
    Capture,
    CodeDisplayModal,
    DashboardScreen,
    DoctorModal,
    MessageModal,
    PromptItemModal,
    run,
)


class TestTuiSafetyAndIsolation(unittest.IsolatedAsyncioTestCase):
    """Verifies output sanitization, ANSI stripping, and error boundary isolation in Textual."""

    def setUp(self) -> None:
        self.valid_profile = {
            "onepassword": {
                "account": "2w4j6k8m0n2p4r6t8v0x2z4a6c",
                "vault": "2w4j6k8m0n2p4r6t8v0x2z4a6c",
            }
        }

    async def test_untrusted_ansi_output_never_renders_in_code_modal(self) -> None:
        """Verify raw ANSI escape sequences and unsafe stderr are never rendered in CodeDisplayModal or MessageModal."""

        def stderr_dispatch(args, stdout, stderr):
            stdout.write("001234\n")
            stderr.write("private-internal-stderr-log\n")
            return 0

        app = AuthyApp(dispatch=stderr_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            await pilot.press("3")
            await pilot.pause()

            modal = app.screen
            self.assertIsInstance(modal, PromptItemModal)
            modal.query_one("#prompt-item-input").value = "2w4j6k8m0n2p4r6t8v0x2z4a6c"
            await pilot.press("enter")
            await pilot.pause()

            self.assertIsInstance(app.screen, CodeDisplayModal)
            code_modal = app.screen
            rendered_dom = str([widget.render() for widget in code_modal.query(Static)])
            self.assertIn("001", rendered_dom)
            self.assertNotIn("private-internal-stderr-log", rendered_dom)

            await pilot.press("escape")
            await pilot.pause()

            # Verify ANSI escapes are rejected and do not leak into MessageModal
            def ansi_dispatch(args, stdout, stderr):
                stdout.write("001234\x1b[31mUNSAFE_COLOR\x1b[0m\n")
                stderr.write("private-internal-stderr-log\n")
                return 0

            app.dispatch_callback = ansi_dispatch
            await pilot.press("3")
            await pilot.pause()

            modal = app.screen
            modal.query_one("#prompt-item-input").value = "2w4j6k8m0n2p4r6t8v0x2z4a6c"
            await pilot.press("enter")
            await pilot.pause()

            self.assertIsInstance(app.screen, MessageModal)
            msg_modal = app.screen
            modal_text = str([widget.render() for widget in msg_modal.query(Static)])
            self.assertNotIn("UNSAFE_COLOR", modal_text)
            self.assertNotIn("private-internal-stderr-log", modal_text)

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_unexpected_backend_exception_never_exposes_traceback(self) -> None:
        """Verify RuntimeError in dispatch never exposes exception details or tracebacks in DOM."""

        def crashing_dispatch(args, stdout, stderr):
            raise RuntimeError("sensitive-backend-database-failure-credential")

        app = AuthyApp(dispatch=crashing_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            await pilot.press("3")
            await pilot.pause()

            prompt_modal = app.screen
            self.assertIsInstance(prompt_modal, PromptItemModal)
            prompt_modal.query_one("#prompt-item-input").value = "2w4j6k8m0n2p4r6t8v0x2z4a6c"
            await pilot.press("enter")
            await pilot.pause()

            # Must catch exception and display sanitized MessageModal
            self.assertIsInstance(app.screen, MessageModal)
            msg_modal = app.screen
            modal_text = str([widget.render() for widget in msg_modal.query(Static)])

            self.assertNotIn("sensitive-backend-database-failure-credential", modal_text)
            self.assertNotIn("Traceback", modal_text)
            self.assertNotIn("RuntimeError", modal_text)

            # Modal dismisses cleanly back to dashboard
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)
            self.assertTrue(app.is_running)
            await pilot.press("q")

    async def test_doctor_reports_statuses_when_backend_exits_nonzero(self) -> None:
        """Verify DoctorModal parses statuses even when dispatch returns non-zero code (e.g. 3)."""

        def doctor_failing_dispatch(args, stdout, stderr):
            stdout.write("op: available\nwl-copy: missing\nclock: unknown\n")
            return 3

        app = AuthyApp(dispatch=doctor_failing_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            await pilot.press("7")
            await pilot.pause()

            self.assertIsInstance(app.screen, DoctorModal)
            modal = app.screen

            # DoctorModal should show status badges accurately
            badge_op = str(modal.query_one("#badge-op", Static).render())
            badge_wl = str(modal.query_one("#badge-wl-copy", Static).render())
            self.assertIn("AVAILABLE", badge_op)
            self.assertIn("MISSING", badge_wl)

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_prompt_modal_cancellation_and_bounds(self) -> None:
        """Verify PromptItemModal dismisses on Escape returning to DashboardScreen without dispatch."""
        dispatched = []

        def tracking_dispatch(args, stdout, stderr):
            dispatched.append(args)
            return 0

        app = AuthyApp(dispatch=tracking_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            await pilot.press("3")
            await pilot.pause()
            self.assertIsInstance(app.screen, PromptItemModal)

            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)
            self.assertEqual(dispatched, [])
            await pilot.press("q")

    def test_capture_bounds_and_terminal_flag(self) -> None:
        """Verify Capture buffer bounds at 128 KiB and isatty behaves as terminal."""
        cap = Capture()
        self.assertTrue(cap.isatty())
        cap.write("x" * 1000)
        self.assertEqual(cap.tell(), 1000)
        with self.assertRaises(AppError) as ctx:
            cap.write("y" * 131073)
        self.assertEqual(ctx.exception.exit_code, 5)

    def test_run_entrypoint_lifecycle(self) -> None:
        """Verify run() returns 3 on non-terminal and handles normal execution."""
        self.assertEqual(run(lambda *a: 0, terminal=False), 3)
        with patch.object(AuthyApp, "run", return_value=0):
            self.assertEqual(run(lambda *a: 0, terminal=True), 0)
        with patch.object(AuthyApp, "run", side_effect=KeyboardInterrupt):
            self.assertEqual(run(lambda *a: 0, terminal=True), 130)

    def test_legacy_curses_compat_bridges(self) -> None:
        """Verify legacy curses helper functions for backwards compatibility."""
        from authy_local.tui import choose_backend, confirm_delete, delete_record, message, prompt

        mock_screen = MagicMock()
        mock_screen.getmaxyx.return_value = (24, 80)
        mock_curses = MagicMock()
        mock_curses.KEY_RESIZE = 410
        mock_curses.KEY_BACKSPACE = 263

        # confirm_delete with DELETE
        mock_screen.getch.side_effect = [
            ord("D"),
            ord("E"),
            ord("L"),
            ord("E"),
            ord("T"),
            ord("E"),
            10,
        ]
        self.assertTrue(confirm_delete(mock_screen, mock_curses, "pass-otp", "test/key"))

        # confirm_delete escape
        mock_screen.getch.side_effect = [27]
        self.assertFalse(confirm_delete(mock_screen, mock_curses, "pass-otp", "test/key"))

        # delete_record success
        mock_screen.getch.side_effect = [27]
        with patch("authy_local.tui_items.remove"):
            self.assertTrue(delete_record(mock_screen, mock_curses, "pass-otp", {}, "test/key"))

        # choose_backend select 2
        mock_screen.getch.side_effect = [ord("2")]
        self.assertEqual(choose_backend(mock_screen, mock_curses, "onepassword"), "pass-otp")

        # message escape
        mock_screen.getch.side_effect = [27]
        message(mock_screen, ["Hello line 1", "Hello line 2"])

        # prompt entry
        mock_screen.getch.side_effect = [ord("a"), ord("b"), 10]
        self.assertEqual(prompt(mock_screen, "Item", 10, mock_curses), "ab")
