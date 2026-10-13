"""Adversarial Stress and State Machine Hardening Test Suite for Milestone M6 (Tier 5).

Focus areas:
1. Screen and modal state machines: AuthyApp, DashboardScreen, TokenBrowserScreen,
   CodeDisplayModal, DoctorModal, HelpModal, SavedScopeModal, DeleteConfirmModal, MessageModal.
2. Terminal suspension (safe_suspend()): Unhandled exceptions, SIGINT/KeyboardInterrupt,
   terminal restoration invariants, screen redraw on resume, and driver failure fallbacks.
3. Countdown timer (TotpProgressBar): Clock jumps, backwards time warp, leap second transitions,
   extreme/invalid remaining seconds and bar widths, modal unmount timer stops, and cryptographic
   memory erasure (self.code = "").
4. High-throughput UI events: Concurrent keystrokes, rapid search debouncing, screen resize events
   during active modal dialogs, and clipboard failure fallbacks.

Authored by Challenger 2 (Empirical Challenger) for Milestone M6 Tier 5 verification.
"""

from __future__ import annotations

import asyncio
import time
import unittest
from collections.abc import Callable
from unittest.mock import MagicMock, patch

from rich.text import Text
from textual.events import Key
from textual.widgets import Button, Input, Static

from authy_local.errors import MESSAGES, AppError
from authy_local.tui import (
    ActionListView,
    AuthyApp,
    CodeDisplayModal,
    DashboardScreen,
    DeleteConfirmModal,
    DetailWorkspace,
    DoctorModal,
    HeaderBar,
    HelpModal,
    KeyboardFooter,
    MessageModal,
    MinSizeWarning,
    SavedScopeModal,
    SessionStatusPanel,
    TokenBrowserScreen,
    TotpProgressBar,
)


def make_mock_driver(can_suspend: bool = True, raise_on_resume: bool = False) -> MagicMock:
    """Create a mock Textual driver with instrumented suspension lifecycle."""
    driver = MagicMock()
    driver.can_suspend = can_suspend
    driver.is_application_mode_suspended = False
    driver.is_headless = False
    driver.is_inline = False

    def suspend_app() -> None:
        driver.is_application_mode_suspended = True

    def resume_app() -> None:
        if raise_on_resume:
            raise RuntimeError("Hardware terminal failed to resume application mode")
        driver.is_application_mode_suspended = False

    driver.suspend_application_mode.side_effect = suspend_app
    driver.resume_application_mode.side_effect = resume_app
    return driver


class TestScreenModalStateMachines(unittest.IsolatedAsyncioTestCase):
    """Adversarial stress testing of screen and modal state machines."""

    def setUp(self) -> None:
        self.dummy_dispatch: Callable = lambda args, out, diag: 0
        self.valid_profile = {
            "onepassword": {
                "account": "2w4j6k8m0n2p4r6t8v0x2z4a6c",
                "vault": "2w4j6k8m0n2p4r6t8v0x2z4a6c",
            },
            "pass-otp": {
                "store": "/home/user/.password-store",
                "key_home": "/home/user/.gnupg",
            },
            "totpm": {
                "config": "/home/user/.config/totpm.conf",
            },
        }

    async def test_dashboard_screen_state_and_navigation(self) -> None:
        """DashboardScreen: Verify hierarchy, option list syncing, and key actions."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            screen = app.screen
            self.assertIsInstance(screen, DashboardScreen)

            self.assertIsNotNone(screen.query_one(HeaderBar))
            self.assertIsNotNone(screen.query_one(ActionListView))
            self.assertIsNotNone(screen.query_one(DetailWorkspace))
            self.assertIsNotNone(screen.query_one(SessionStatusPanel))
            self.assertIsNotNone(screen.query_one(KeyboardFooter))
            self.assertIsNotNone(screen.query_one(MinSizeWarning))

            action_list = screen.query_one(ActionListView)
            workspace = screen.query_one(DetailWorkspace)

            action_list.highlighted = 1
            await pilot.pause()
            self.assertEqual(workspace.selected_index, 1)

            action_list.highlighted = 5
            await pilot.pause()
            self.assertEqual(workspace.selected_index, 5)

            # Test cursor navigation actions
            screen.action_cursor_down()
            await pilot.pause()
            self.assertEqual(workspace.selected_index, 6)

            screen.action_cursor_up()
            await pilot.pause()
            self.assertEqual(workspace.selected_index, 5)

    async def test_dialog_gating_prevents_modal_stacking(self) -> None:
        """Verify _can_open_dialog() prevents stacking multiple modal dialogs."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            self.assertIsInstance(app.screen, DashboardScreen)

            # Push first modal
            modal = DoctorModal(states={"op": "available"}, summary="Ready", status=0)
            app.push_screen(modal)
            await pilot.pause()
            self.assertIs(app.screen, modal)
            modal_stack_len = len(app.screen_stack)

            # Attempting to trigger other actions while modal is open must be blocked
            self.assertFalse(app._can_open_dialog())
            app.action_show_code()
            app.action_copy_code()
            app.action_browse_show()
            app.action_install_preview()
            app.action_migration_guide()
            app.action_saved_scope()
            await pilot.pause()

            # Screen stack must remain strictly bounded
            self.assertEqual(len(app.screen_stack), modal_stack_len)
            self.assertIs(app.screen, modal)

            # Dismiss modal
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)
            self.assertEqual(len(app.screen_stack), modal_stack_len - 1)
            self.assertTrue(app._can_open_dialog())

    async def test_code_display_modal_typography_and_formatting(self) -> None:
        """CodeDisplayModal: Test OTP code formatting with varied code lengths and whitespace."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            modal = CodeDisplayModal(code="123456", item_label="GitHub")
            app.push_screen(modal)
            await pilot.pause()

            # Standard 6-digit split
            digits_text = str(modal.query_one("#code-digits", Static).render())
            self.assertIn("123  456", digits_text)

            # 8-digit split
            self.assertEqual(modal._format_digits("12345678"), "1234  5678")

            # 7-digit odd length
            self.assertEqual(modal._format_digits("1234567"), "1234567")

            # Embedded whitespace
            self.assertEqual(modal._format_digits(" 987 654 "), "987  654")

            # Empty code fallback
            self.assertEqual(modal._format_digits(""), "------")
            self.assertEqual(modal._format_digits("   "), "------")

            await pilot.press("escape")
            await pilot.pause()

    async def test_doctor_modal_state_machine_and_diagnostics(self) -> None:
        """DoctorModal: Test diagnostic states parsing, exit badge classes, and re-run."""
        mock_output = (
            "platform: available\n"
            "python: available\n"
            "op: missing\n"
            "tpm-device: unknown\n"
            "unrecognized_field: foo\n"
        )

        def mock_dispatch(args, out, diag):
            out.write(mock_output)
            return 0

        app = AuthyApp(dispatch=mock_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            modal = DoctorModal()
            app.push_screen(modal)
            await pilot.pause()

            banner = modal.query_one("#doctor-status-banner", Static)
            self.assertIn("System Ready", str(banner.render()))

            # Verify badges
            op_badge = modal.query_one("#badge-op", Static)
            self.assertTrue(op_badge.has_class("badge-missing"))
            self.assertIn("MISSING", str(op_badge.render()))

            platform_badge = modal.query_one("#badge-platform", Static)
            self.assertTrue(platform_badge.has_class("badge-available"))
            self.assertIn("AVAILABLE", str(platform_badge.render()))

            tpm_badge = modal.query_one("#badge-tpm-device", Static)
            self.assertTrue(tpm_badge.has_class("badge-unknown"))
            self.assertIn("UNKNOWN", str(tpm_badge.render()))

            # Button click re-run
            modal.on_refresh_pressed()
            await pilot.pause()
            self.assertEqual(modal.status, 0)

            # Button click dismiss
            modal.on_close_pressed()
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_help_modal_state_machine_and_scroll(self) -> None:
        """HelpModal: Test table rendering, scrolling methods, and toggle dismissal."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            modal = HelpModal()
            app.push_screen(modal)
            await pilot.pause()

            self.assertIs(app.screen, modal)
            # Exercise scroll actions safely
            modal.action_scroll_down()
            modal.action_scroll_up()
            modal.action_scroll_page_down()
            modal.action_scroll_page_up()
            await pilot.pause()

            # Dismissal via '?'
            await pilot.press("question_mark")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_saved_scope_modal_all_backends_and_validation(self) -> None:
        """SavedScopeModal: Test 1Password, pass-otp, totpm forms, validation, and cancel."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles={})
        async with app.run_test() as pilot:
            # 1. onepassword with invalid short account ID
            modal_op = SavedScopeModal(backend="onepassword", initial={})
            app.push_screen(modal_op)
            await pilot.pause()

            inp_account = modal_op.query_one("#scope-op-account", Input)
            inp_account.value = "short_invalid"
            inp_vault = modal_op.query_one("#scope-op-vault", Input)
            inp_vault.value = "2w4j6k8m0n2p4r6t8v0x2z4a6c"

            # Trigger save -> should fail validation
            modal_op.on_save_pressed()
            await pilot.pause()

            error_banner = modal_op.query_one("#scope-error-banner", Static)
            self.assertIn("Validation failed", str(error_banner.render()))

            # Cancel
            modal_op.action_cancel_scope()
            await pilot.pause()

            # 2. pass-otp with relative path (should fail validation)
            modal_pass = SavedScopeModal(backend="pass-otp", initial={})
            app.push_screen(modal_pass)
            await pilot.pause()

            modal_pass.query_one("#scope-pass-store", Input).value = "relative/store"
            modal_pass.query_one("#scope-pass-keyhome", Input).value = "/home/user/.gnupg"
            modal_pass.on_save_pressed()
            await pilot.pause()

            error_banner = modal_pass.query_one("#scope-error-banner", Static)
            self.assertIn("Validation failed", str(error_banner.render()))

            # Cancel via button
            modal_pass.on_cancel_pressed()
            await pilot.pause()

            # 3. totpm with valid absolute path (should succeed)
            modal_totpm = SavedScopeModal(backend="totpm", initial={})
            app.push_screen(modal_totpm)
            await pilot.pause()

            modal_totpm.query_one("#scope-totpm-config", Input).value = "/home/user/.totpm.conf"
            modal_totpm.on_save_pressed()
            await pilot.pause()

            # Should dismiss and update app.profiles
            self.assertIn("totpm", app.profiles)
            self.assertEqual(app.profiles["totpm"]["config"], "/home/user/.totpm.conf")

    async def test_delete_confirm_modal_state_machine(self) -> None:
        """DeleteConfirmModal: Test authorization text matching and button enabling."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            modal = DeleteConfirmModal(backend="pass-otp", label="Work/AWS")
            result_holder = []

            def on_dismiss(val):
                result_holder.append(val)

            app.push_screen(modal, on_dismiss)
            await pilot.pause()

            btn_delete = modal.query_one("#btn-confirm-delete", Button)
            self.assertTrue(btn_delete.disabled)

            inp = modal.query_one("#delete-confirm-input", Input)

            # Partial text -> disabled
            inp.value = "DEL"
            await pilot.pause()
            self.assertTrue(btn_delete.disabled)

            # Lowercase text -> disabled
            inp.value = "delete"
            await pilot.pause()
            self.assertTrue(btn_delete.disabled)

            # Exact text -> enabled
            inp.value = "DELETE"
            await pilot.pause()
            self.assertFalse(btn_delete.disabled)

            # Press delete button -> confirms True
            modal.on_confirm_pressed()
            await pilot.pause()
            self.assertEqual(result_holder, [True])

    async def test_message_modal_lifecycle(self) -> None:
        """MessageModal: Test multiline rendering and dismissal keys."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            lines = [f"Line {i}: test diagnostic output" for i in range(20)]
            modal = MessageModal(title="Diagnostic Log", lines=lines)
            app.push_screen(modal)
            await pilot.pause()

            self.assertIs(app.screen, modal)
            # Dismiss via Space
            await pilot.press("space")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_token_browser_show_and_copy_actions(self) -> None:
        """TokenBrowserScreen: Test interactive selection with show vs copy modes."""
        records = [("k1", "GitHub (dev)"), ("k2", "AWS (prod)")]

        def mock_dispatch(args, out, diag):
            if args[0] == "show":
                out.write("654321\n")
            return 0

        app = AuthyApp(dispatch=mock_dispatch, profiles=self.valid_profile)
        async with app.run_test() as pilot:
            # 1. Browser in 'show' mode
            browser = TokenBrowserScreen(
                backend="onepassword",
                profile=self.valid_profile["onepassword"],
                records=records,
                default_action="show",
            )
            app.push_screen(browser)
            await pilot.pause()

            # Select highlighted item -> opens CodeDisplayModal
            browser.action_select_show()
            await pilot.pause()
            self.assertIsInstance(app.screen, CodeDisplayModal)
            self.assertEqual(app.screen.code, "654321")

            # Dismiss CodeDisplayModal
            await pilot.press("escape")
            await pilot.pause()
            self.assertIs(app.screen, browser)

            # 2. Browser in 'copy' mode
            browser.default_action = "copy"
            with patch.object(app, "notify_copy") as mock_notify_copy:
                browser.action_select_copy()
                await pilot.pause()
                mock_notify_copy.assert_called_once()

            # Escape back to dashboard
            browser.action_handle_escape()
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_token_browser_delete_flow(self) -> None:
        """TokenBrowserScreen: Test deletion flow for local entries."""
        records = [("entry1", "Personal/Mail"), ("entry2", "Personal/Bank")]
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.valid_profile)

        async with app.run_test() as pilot:
            browser = TokenBrowserScreen(
                backend="pass-otp",
                profile=self.valid_profile["pass-otp"],
                records=records,
            )
            app.push_screen(browser)
            await pilot.pause()

            # Onepassword does not allow local deletion
            browser.backend = "onepassword"
            browser.action_request_delete()
            await pilot.pause()
            self.assertIs(app.screen, browser)

            # Pass-otp allows local deletion -> pushes DeleteConfirmModal
            browser.backend = "pass-otp"
            with patch.object(app, "delete_record", return_value=True):
                browser.action_request_delete()
                await pilot.pause()
                self.assertIsInstance(app.screen, DeleteConfirmModal)

                # Confirm deletion
                inp = app.screen.query_one("#delete-confirm-input", Input)
                inp.value = "DELETE"
                await pilot.pause()
                app.screen.on_confirm_pressed()
                await pilot.pause()

                # Browser records must be updated
                self.assertEqual(len(browser.raw_records), 1)
                self.assertEqual(browser.raw_records[0][0], "entry2")


class TestTerminalSuspensionAdversarial(unittest.IsolatedAsyncioTestCase):
    """Adversarial stress testing of terminal suspension invariants and error handling."""

    def setUp(self) -> None:
        self.profile = {"onepassword": {"account": "acc1", "vault": "vault1"}}

    async def test_safe_suspend_unhandled_exception_propagation_and_cleanup(self) -> None:
        """safe_suspend(): Verify unhandled exceptions propagate and cleanup executes."""
        app = AuthyApp(profiles=self.profile)
        async with app.run_test():
            mock_driver = make_mock_driver(can_suspend=True)
            app._driver = mock_driver

            # 1. RuntimeError
            with self.assertRaises(RuntimeError):
                with app.safe_suspend():
                    raise RuntimeError("Biometric sensor timeout")
            self.assertFalse(mock_driver.is_application_mode_suspended)

            # 2. ZeroDivisionError
            with self.assertRaises(ZeroDivisionError):
                with app.safe_suspend():
                    _ = 1 / 0
            self.assertFalse(mock_driver.is_application_mode_suspended)

            # 3. MemoryError
            with self.assertRaises(MemoryError):
                with app.safe_suspend():
                    raise MemoryError("Out of cryptographic buffer space")
            self.assertFalse(mock_driver.is_application_mode_suspended)

    async def test_safe_suspend_sigint_keyboard_interrupt_handling(self) -> None:
        """safe_suspend(): Verify KeyboardInterrupt in execute/load/delete is handled safely."""
        app = AuthyApp(profiles=self.profile)
        async with app.run_test():
            mock_driver = make_mock_driver(can_suspend=True)
            app._driver = mock_driver

            # In execute()
            def sigint_dispatch(args, out, diag):
                raise KeyboardInterrupt()

            app.dispatch_callback = sigint_dispatch
            status, summary, lines = app.execute(["show", "item1"])
            self.assertEqual(status, 130)
            self.assertFalse(mock_driver.is_application_mode_suspended)

            # In load_records()
            with patch("authy_local.tui_items.records", side_effect=KeyboardInterrupt):
                rows = app.load_records("onepassword", self.profile["onepassword"])
                self.assertIsNone(rows)
                self.assertFalse(mock_driver.is_application_mode_suspended)

            # In delete_record()
            with patch("authy_local.tui_items.remove", side_effect=KeyboardInterrupt):
                success = app.delete_record("pass-otp", {}, "key1")
                self.assertFalse(success)
                self.assertFalse(mock_driver.is_application_mode_suspended)

    async def test_safe_suspend_driver_restoration_resilience(self) -> None:
        """safe_suspend(): Verify driver restoration exception behavior in safe_suspend and execute."""
        app = AuthyApp(profiles=self.profile)
        async with app.run_test():
            # Driver that raises on resume
            flaky_driver = make_mock_driver(can_suspend=True, raise_on_resume=True)
            app._driver = flaky_driver

            # 1. Direct safe_suspend: driver exception propagates cleanly to caller
            with self.assertRaises(RuntimeError):
                with app.safe_suspend():
                    pass

            # 2. In execute(): driver restoration failure is caught and safely translated to exit code 3
            status, _, lines = app.execute(["show", "item1"])
            self.assertEqual(status, 3)
            self.assertEqual(lines, [MESSAGES[3]])

    async def test_safe_suspend_inactive_and_unsupported_guards(self) -> None:
        """safe_suspend(): Verify early return guards when app is inactive or unsupported."""
        app = AuthyApp(profiles=self.profile)

        # 1. Not running
        self.assertFalse(app.is_running)
        executed = False
        with app.safe_suspend():
            executed = True
        self.assertTrue(executed)

        # 2. Driver is None
        async with app.run_test():
            app._driver = None
            executed = False
            with app.safe_suspend():
                executed = True
            self.assertTrue(executed)

            # 3. Driver can_suspend is False
            app._driver = make_mock_driver(can_suspend=False)
            executed = False
            with app.safe_suspend():
                executed = True
            self.assertTrue(executed)
            app._driver.suspend_application_mode.assert_not_called()

    async def test_execute_app_error_translation(self) -> None:
        """execute(): Verify AppError exception codes are translated without crashing."""
        app = AuthyApp(profiles=self.profile)
        async with app.run_test():

            def app_error_dispatch(args, out, diag):
                raise AppError(5)

            app.dispatch_callback = app_error_dispatch
            status, summary, lines = app.execute(["show", "item1"])
            self.assertEqual(status, 5)
            self.assertEqual(lines, [MESSAGES[5]])


class TestCountdownTimerTotpProgressBarAdversarial(unittest.IsolatedAsyncioTestCase):
    """Adversarial stress testing of TotpProgressBar, clock warp, and memory erasure."""

    def test_totp_progress_bar_boundary_values_and_rendering(self) -> None:
        """TotpProgressBar: Test rendering across all remaining second intervals and bounds."""
        bar = TotpProgressBar(total=30.0, bar_width=20)

        # High time (>15s): green
        bar.remaining_seconds = 29.0
        render_text = bar.render()
        self.assertIn("29s", str(render_text))
        self.assertTrue(bar.has_class("time-normal"))

        # Warning time (6-15s): yellow
        bar.remaining_seconds = 10.0
        render_text = bar.render()
        self.assertIn("10s", str(render_text))
        self.assertTrue(bar.has_class("time-warning"))

        # Critical time (<=5s): red
        bar.remaining_seconds = 3.0
        render_text = bar.render()
        self.assertIn(" 3s", str(render_text))
        self.assertTrue(bar.has_class("time-critical"))

        # Negative time: clamped to 0
        bar.remaining_seconds = -10.0
        self.assertEqual(bar.progress, 0.0)

        # Oversized time: clamped to 30.0
        bar.remaining_seconds = 100.0
        self.assertEqual(bar.progress, 30.0)

        # Expiration state
        bar.is_expired = True
        render_text = bar.render()
        self.assertIn("0s (EXPIRED)", str(render_text))
        self.assertTrue(bar.has_class("time-expired"))

    def test_totp_progress_bar_extreme_bar_widths(self) -> None:
        """TotpProgressBar: Verify extreme bar_width settings do not cause formatting errors."""
        for width in [0, 1, 50, 100, -5]:
            bar = TotpProgressBar(total=30.0, bar_width=width)
            bar.remaining_seconds = 15.0
            render_text = bar.render()
            self.assertIsInstance(render_text, Text)

    async def test_clock_forward_jump_time_step_rollover(self) -> None:
        """CodeDisplayModal: Simulate large forward time jumps across RFC 6238 steps."""
        app = AuthyApp()
        async with app.run_test() as pilot:
            with patch("time.time", return_value=1000 * 30 + 10):
                modal = CodeDisplayModal(code="112233", item_label="Bank")
                app.push_screen(modal)
                await pilot.pause()

                self.assertFalse(modal._is_expired)
                self.assertEqual(modal._initial_step, 1000)

            # Jump forward 10 steps (300 seconds)
            with patch("time.time", return_value=1010 * 30 + 5):
                modal._tick_countdown()
                await pilot.pause()

                # Must transition to expired state
                self.assertTrue(modal._is_expired)
                bar = modal.query_one("#code-progress", TotpProgressBar)
                self.assertTrue(bar.is_expired)
                digits = modal.query_one("#code-digits", Static)
                self.assertIn("(Expired)", str(digits.render()))

            await pilot.press("escape")
            await pilot.pause()

    async def test_clock_backward_time_warp_and_skew(self) -> None:
        """CodeDisplayModal: Simulate backward clock jump (NTP synchronization)."""
        app = AuthyApp()
        async with app.run_test() as pilot:
            with patch("time.time", return_value=1000 * 30 + 20):
                modal = CodeDisplayModal(code="112233", item_label="Bank")
                app.push_screen(modal)
                await pilot.pause()

                self.assertFalse(modal._is_expired)

            # Clock steps back 10 seconds (same step)
            with patch("time.time", return_value=1000 * 30 + 10):
                modal._tick_countdown()
                await pilot.pause()
                self.assertFalse(modal._is_expired)
                bar = modal.query_one("#code-progress", TotpProgressBar)
                self.assertEqual(bar.remaining_seconds, 20.0)

            await pilot.press("escape")
            await pilot.pause()

    async def test_leap_second_step_boundary_ticks(self) -> None:
        """CodeDisplayModal: Simulate exact fractional boundaries around 29.99s -> 30.01s."""
        app = AuthyApp()
        async with app.run_test() as pilot:
            with patch("time.time", return_value=100 * 30 + 29.99):
                modal = CodeDisplayModal(code="445566")
                app.push_screen(modal)
                await pilot.pause()
                self.assertFalse(modal._is_expired)

            # Cross to next step
            with patch("time.time", return_value=101 * 30 + 0.01):
                modal._tick_countdown()
                await pilot.pause()
                self.assertTrue(modal._is_expired)

            await pilot.press("escape")
            await pilot.pause()

    async def test_modal_unmount_and_dismiss_cryptographic_erasure(self) -> None:
        """CodeDisplayModal: Verify strict cryptographic memory wiping upon unmount/dismiss."""
        app = AuthyApp()
        secret_code = "789012"

        async with app.run_test() as pilot:
            modal = CodeDisplayModal(code=secret_code, item_label="Vault")
            app.push_screen(modal)
            await pilot.pause()

            self.assertEqual(modal.code, secret_code)
            self.assertIsNotNone(modal._timer)

            # Dismiss modal via escape
            await pilot.press("escape")
            await pilot.pause()

            # Memory wiping contract: code cleared, timer stopped and cleared
            self.assertEqual(modal.code, "")
            self.assertIsNone(modal._timer)
            self.assertIsNone(modal.refresh_callback)

            # Attempting copy action on wiped modal must be a no-op
            modal.action_copy_code_action()
            self.assertEqual(modal.code, "")

    async def test_expired_code_copy_action_emits_warning(self) -> None:
        """CodeDisplayModal: Copying expired code warns user while still performing copy."""
        app = AuthyApp()
        async with app.run_test() as pilot:
            modal = CodeDisplayModal(code="334455", item_label="ServiceX")
            app.push_screen(modal)
            await pilot.pause()

            modal._is_expired = True
            with (
                patch.object(app, "notify") as mock_notify,
                patch("authy_local.interaction.copy_code"),
            ):
                modal.action_copy_code_action()
                await pilot.pause()
                mock_notify.assert_any_call("Warning: Copying expired code.", timeout=3)

            await pilot.press("escape")
            await pilot.pause()


class TestHighThroughputEventsAdversarial(unittest.IsolatedAsyncioTestCase):
    """Adversarial stress testing of high-throughput event hammering, debouncing, and resizing."""

    def setUp(self) -> None:
        self.dummy_dispatch: Callable = lambda args, out, diag: 0
        self.profile = {"onepassword": {"account": "acc1", "vault": "vault1"}}

    async def test_rapid_search_debouncing_event_burst(self) -> None:
        """TokenBrowserScreen: Rapid search typing burst resets timer without orphan executions."""
        records = [(f"item{i}", f"Service {i}") for i in range(50)]
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.profile)

        async with app.run_test() as pilot:
            browser = TokenBrowserScreen(
                backend="onepassword",
                profile=self.profile["onepassword"],
                records=records,
            )
            app.push_screen(browser)
            await pilot.pause()

            search_input = browser.query_one("#search-input", Input)

            # Fire 30 rapid Input.Changed events
            for i in range(30):
                browser.on_search_changed(Input.Changed(search_input, f"query_{i}"))

            # Only the final timer should be active
            self.assertIsNotNone(browser._debounce_timer)

            # Await debounce resolution (0.035s)
            await asyncio.sleep(0.06)
            await pilot.pause()

            self.assertEqual(browser.current_query, "query_29")

            browser.action_handle_escape()
            await pilot.pause()

    def test_fuzzy_search_highlighting_adversarial_queries(self) -> None:
        """TokenBrowserScreen: Verify _highlight_match handles adversarial edge strings."""
        target_text = "Amazon Web Services (Production Root Account)"

        adversarial_queries = [
            "",  # empty
            "   ",  # whitespace only
            "Amazon",  # prefix match
            "Production",  # substring match
            "web root",  # multi-word match
            "awsprod",  # fuzzy subsequence
            ".*+?^${}()|[]\\",  # regex injection attempt
            "Amazon" * 200,  # massive query
            "\x00\x01\x02\x03",  # control characters
            "nonexistent_token_12345",  # non-matching string
            "🎉 🚀 🔐",  # unicode emojis
        ]

        for query in adversarial_queries:
            rendered = TokenBrowserScreen._highlight_match(target_text, query, "white")
            self.assertIsInstance(rendered, Text)
            self.assertEqual(rendered.plain, target_text)

    async def test_screen_resize_during_active_modals(self) -> None:
        """Verify terminal resize thrashing while each modal is active causes no crashes."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.profile)

        modals = [
            CodeDisplayModal(code="123456", item_label="ItemA"),
            DoctorModal(states={"op": "available"}, summary="Ready"),
            HelpModal(),
            SavedScopeModal(backend="onepassword"),
            DeleteConfirmModal(backend="pass-otp", label="ItemB"),
            MessageModal(title="Alert", lines=["Line 1", "Line 2"]),
        ]

        async with app.run_test() as pilot:
            for modal in modals:
                app.push_screen(modal)
                await pilot.pause()
                self.assertIs(app.screen, modal)

                # Resize to compact
                await pilot.resize_terminal(60, 18)
                await pilot.pause()

                # Resize to sub-threshold
                await pilot.resize_terminal(45, 12)
                await pilot.pause()

                # Resize to standard
                await pilot.resize_terminal(80, 24)
                await pilot.pause()

                self.assertTrue(app.is_running)
                await pilot.press("escape")
                await pilot.pause()
                self.assertIsInstance(app.screen, DashboardScreen)

    async def test_clipboard_failure_fallbacks(self) -> None:
        """Verify UI fallbacks when external desktop clipboard fails."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.profile)

        async with app.run_test() as pilot:
            modal = CodeDisplayModal(code="654321", item_label="ServiceY")
            app.push_screen(modal)
            await pilot.pause()

            # Mock copy_code raising diverse errors
            errors = [
                AppError(3),
                OSError("wl-copy not found in PATH"),
                RuntimeError("Wayland socket disconnected"),
                KeyError("DISPLAY"),
            ]

            for err in errors:
                with patch("authy_local.interaction.copy_code", side_effect=err):
                    with patch.object(app, "notify") as mock_notify:
                        modal.action_copy_code_action()
                        await pilot.pause()
                        # Fallback notification displayed
                        mock_notify.assert_called_with("Copy completed.", timeout=2.5)

            await pilot.press("escape")
            await pilot.pause()

    async def test_event_hammering_protection_activation(self) -> None:
        """Verify _is_event_hammering() activates during high-rate key injection."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.profile)

        async with app.run_test() as pilot:
            self.assertIsInstance(app.screen, DashboardScreen)

            # Trigger rapid on_key calls with delta < 0.01
            now = time.perf_counter()
            for _ in range(50):
                app.on_key(Key("1", "1"))
                app._last_event_time = now - 0.001

            # Hammering flag should be active
            self.assertTrue(app._is_event_hammering())
            self.assertFalse(app._can_open_dialog())

            # Cooldown
            await asyncio.sleep(0.2)
            await pilot.pause()

            self.assertFalse(app._is_event_hammering())
            self.assertTrue(app._can_open_dialog())
