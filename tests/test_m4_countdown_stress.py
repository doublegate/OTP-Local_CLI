"""Adversarial Stress and Life-Cycle Test Suite for Milestone M4.

Focus: TOTP countdown bar, rollover boundary state machine, rapid mount/unmount stress,
asynchronous timer lifecycle, and cryptographic memory erasure.

Authored by Challenger 1 (Empirical Challenger) for adversarial milestone review.
"""

from __future__ import annotations

import asyncio
import gc
import unittest
from collections.abc import Callable
from unittest.mock import MagicMock, patch

from textual.widgets import Button, Static

from authy_local.tui import (
    AuthyApp,
    CodeDisplayModal,
    TotpProgressBar,
)


class TestTotpTimeDilationStress(unittest.IsolatedAsyncioTestCase):
    """Adversarial stress testing of time dilation, clock jumps, and rollover boundaries."""

    def setUp(self) -> None:
        self.dummy_dispatch: Callable = lambda args, out, diag: 0
        self.profile = {"onepassword": {"account": "acc1", "vault": "vault1"}}

    async def test_exact_boundary_rollover_no_refresh(self) -> None:
        """Simulate clock ticks crossing step T -> step T+1 with no refresh callback.

        Verifies:
        1. Boundary tick (29.9s -> 30.1s) immediately triggers rollover.
        2. Modal transitions to expired state with _is_expired = True.
        3. Code digits reflect '(Expired)' and dim red styling.
        4. Progress bar drops to 0 and displays '0s (EXPIRED)'.
        5. Zero stale code is presented as valid.
        """
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.profile)
        secret_code = "654321"

        async with app.run_test() as pilot:
            # Mount modal near end of window (step 100, second 29)
            with patch("time.time", return_value=(100 * 30 + 29)):
                modal = CodeDisplayModal(code=secret_code, item_label="ServiceA")
                app.push_screen(modal)
                await pilot.pause()

                self.assertEqual(modal.code, secret_code)
                self.assertFalse(modal._is_expired)
                self.assertEqual(modal._initial_step, 100)

                # Prior to rollover: bar and label show valid 1s
                bar = modal.query_one("#code-progress", TotpProgressBar)
                self.assertAlmostEqual(bar.remaining_seconds, 1.0)
                self.assertFalse(bar.is_expired)
                label = modal.query_one("#code-timer-label", Static)
                self.assertIn("Valid for 1s", str(label.render()))
                digits = modal.query_one("#code-digits", Static)
                self.assertIn("654  321", str(digits.render()))
                self.assertNotIn("Expired", str(digits.render()))

            # Cross exact boundary into step 101, second 0.1
            with patch("time.time", return_value=(101 * 30 + 0.1)):
                modal._tick_countdown()
                await pilot.pause()

                # MUST transition to expired state
                self.assertTrue(modal._is_expired)
                self.assertTrue(bar.is_expired)
                self.assertEqual(bar.progress, 0)
                self.assertIn("0s (EXPIRED)", str(bar.render()))

                # Digits MUST explicitly display Expired
                digits_text = str(modal.query_one("#code-digits", Static).render())
                self.assertIn("(Expired)", digits_text)
                self.assertIn("654  321", digits_text)

                # Timer label MUST reflect expiration
                label_text = str(modal.query_one("#code-timer-label", Static).render())
                self.assertIn("Code expired (0s)", label_text)

                # Dialog container must have time-expired class
                dialog = modal.query_one("#code-dialog")
                self.assertTrue(dialog.has_class("time-expired"))
                self.assertFalse(dialog.has_class("time-normal"))

            # Clean dismissal
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(modal.code, "")

    async def test_exact_boundary_rollover_with_refresh_success(self) -> None:
        """Simulate clock ticks crossing step T -> step T+1 with successful refresh callback.

        Verifies:
        1. Rollover executes refresh_callback() to obtain new OTP.
        2. self.code updates to new OTP.
        3. Modal remains active (_is_expired = False) and initial_step advances.
        4. Progress bar and label reset to full remaining window time.
        5. Zero stale code is presented.
        """
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.profile)
        mock_refresh = MagicMock(return_value="789012")

        async with app.run_test() as pilot:
            with patch("time.time", return_value=(100 * 30 + 28)):
                modal = CodeDisplayModal(
                    code="123456",
                    item_label="ServiceB",
                    refresh_callback=mock_refresh,
                )
                app.push_screen(modal)
                await pilot.pause()

                self.assertEqual(modal.code, "123456")
                self.assertFalse(modal._is_expired)

            # Rollover to step 101, second 3
            with patch("time.time", return_value=(101 * 30 + 3)):
                modal._tick_countdown()
                await pilot.pause()

                # Refresh callback invoked
                mock_refresh.assert_called_once()
                self.assertEqual(modal.code, "789012")
                self.assertFalse(modal._is_expired)
                self.assertEqual(modal._initial_step, 101)

                # Digits display newly fetched OTP
                digits_text = str(modal.query_one("#code-digits", Static).render())
                self.assertIn("789  012", digits_text)
                self.assertNotIn("123", digits_text)
                self.assertNotIn("Expired", digits_text)

                # Progress bar and label updated for new step (30 - 3 = 27s remaining)
                bar = modal.query_one("#code-progress", TotpProgressBar)
                self.assertFalse(bar.is_expired)
                self.assertAlmostEqual(bar.remaining_seconds, 27.0)
                label_text = str(modal.query_one("#code-timer-label", Static).render())
                self.assertIn("Valid for 27s", label_text)

            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(modal.code, "")

    async def test_rollover_with_refresh_failure_modes(self) -> None:
        """Stress refresh_callback failures: empty string, None, and raised exceptions.

        Verifies modal catches errors gracefully and enters expiration state without crashing.
        """
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.profile)

        async with app.run_test() as pilot:
            # Case 1: refresh returns empty string
            mock_empty = MagicMock(return_value="")
            with patch("time.time", return_value=(100 * 30 + 29)):
                modal1 = CodeDisplayModal(code="111222", refresh_callback=mock_empty)
                app.push_screen(modal1)
                await pilot.pause()

            with patch("time.time", return_value=(101 * 30 + 1)):
                modal1._tick_countdown()
                await pilot.pause()
                self.assertTrue(modal1._is_expired)
                self.assertIn("(Expired)", str(modal1.query_one("#code-digits", Static).render()))

            await pilot.press("escape")
            await pilot.pause()

            # Case 2: refresh raises RuntimeError
            mock_err = MagicMock(side_effect=RuntimeError("GPG agent locked"))
            with patch("time.time", return_value=(100 * 30 + 29)):
                modal2 = CodeDisplayModal(code="333444", refresh_callback=mock_err)
                app.push_screen(modal2)
                await pilot.pause()

            with patch("time.time", return_value=(101 * 30 + 1)):
                modal2._tick_countdown()
                await pilot.pause()
                self.assertTrue(modal2._is_expired)
                self.assertIn("(Expired)", str(modal2.query_one("#code-digits", Static).render()))

            await pilot.press("escape")
            await pilot.pause()

    async def test_multi_step_time_warp_dilation(self) -> None:
        """Simulate severe forward time warp: jumping 5 steps (150s) and 120 steps (3600s).

        Verifies code transitions to expired instantly on next tick without arithmetic faults.
        """
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.profile)

        async with app.run_test() as pilot:
            with patch("time.time", return_value=(100 * 30 + 15)):
                modal = CodeDisplayModal(code="555666")
                app.push_screen(modal)
                await pilot.pause()
                self.assertFalse(modal._is_expired)

            # Warp forward 10 steps (300 seconds)
            with patch("time.time", return_value=(110 * 30 + 12)):
                modal._tick_countdown()
                await pilot.pause()
                self.assertTrue(modal._is_expired)
                self.assertIn("(Expired)", str(modal.query_one("#code-digits", Static).render()))

            # Warp forward 1000 steps (30000 seconds)
            with patch("time.time", return_value=(1110 * 30 + 5)):
                modal._tick_countdown()
                await pilot.pause()
                self.assertTrue(modal._is_expired)

            await pilot.press("escape")
            await pilot.pause()

    async def test_multi_cycle_consecutive_rollover_and_recovery(self) -> None:
        """Simulate continuous multi-step chain (T -> T+1 -> T+2 -> Expired -> Revive via 'r')."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.profile)
        refresh_mock = MagicMock()

        async with app.run_test() as pilot:
            # Cycle 1: Mount at step 50
            with patch("time.time", return_value=(50 * 30 + 20)):
                modal = CodeDisplayModal(code="100001", refresh_callback=refresh_mock)
                app.push_screen(modal)
                await pilot.pause()
                self.assertEqual(modal.code, "100001")

            # Cycle 2: Rollover to step 51 (refresh -> 100002)
            refresh_mock.return_value = "100002"
            with patch("time.time", return_value=(51 * 30 + 1)):
                modal._tick_countdown()
                await pilot.pause()
                self.assertEqual(modal.code, "100002")
                self.assertFalse(modal._is_expired)

            # Cycle 3: Rollover to step 52 (refresh -> 100003)
            refresh_mock.return_value = "100003"
            with patch("time.time", return_value=(52 * 30 + 2)):
                modal._tick_countdown()
                await pilot.pause()
                self.assertEqual(modal.code, "100003")
                self.assertFalse(modal._is_expired)

            # Cycle 4: Rollover to step 53 (refresh fails -> Expired)
            refresh_mock.side_effect = TimeoutError("Op CLI timeout")
            with patch("time.time", return_value=(53 * 30 + 1)):
                modal._tick_countdown()
                await pilot.pause()
                self.assertTrue(modal._is_expired)
                self.assertIn("(Expired)", str(modal.query_one("#code-digits", Static).render()))

            # Cycle 5: Recover via user action 'r' when backend recovers
            refresh_mock.side_effect = None
            refresh_mock.return_value = "100004"
            with patch("time.time", return_value=(53 * 30 + 10)):
                modal.action_refresh_code_action()
                await pilot.pause()
                self.assertEqual(modal.code, "100004")
                self.assertFalse(modal._is_expired)
                self.assertIn("100  004", str(modal.query_one("#code-digits", Static).render()))

            await pilot.press("escape")
            await pilot.pause()


class TestCodeModalRapidOpenCloseStress(unittest.IsolatedAsyncioTestCase):
    """Stress test rapid mount/unmount iterations and asynchronous timer cancellation."""

    def setUp(self) -> None:
        self.dummy_dispatch: Callable = lambda args, out, diag: 0
        self.profile = {"onepassword": {"account": "acc1", "vault": "vault1"}}

    async def test_rapid_mount_unmount_60_iterations_varied_dismissal(self) -> None:
        """Mount and unmount CodeDisplayModal 60+ times in rapid succession.

        Verifies:
        1. Strict memory wiping: self.code == '' on every iteration.
        2. Timer cancellation: self._timer is stopped and None.
        3. Zero timer leaks: modal._timers and app._timers remain empty / bounded.
        4. DOM cleanup: children detached from dismissed modals.
        """
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.profile)

        async with app.run_test() as pilot:
            initial_timers = len(app._timers)

            for i in range(65):
                secret = f"TOKEN_{i:04d}"
                modal = CodeDisplayModal(code=secret, item_label=f"Item_{i}")
                app.push_screen(modal)
                await pilot.pause()

                self.assertEqual(modal.code, secret)
                self.assertIsNotNone(modal._timer)

                # Alternate dismissal methods:
                # 0: Escape key
                # 1: Click btn-dismiss-code Button
                # 2: Direct app.pop_screen()
                dismiss_mode = i % 3
                if dismiss_mode == 0:
                    await pilot.press("escape")
                elif dismiss_mode == 1:
                    modal.query_one("#btn-dismiss-code", Button).press()
                else:
                    app.pop_screen()

                await pilot.pause()

                # CRITICAL VERIFICATIONS
                self.assertEqual(
                    modal.code,
                    "",
                    f"Iteration {i}: modal.code was NOT wiped! Value: {modal.code}",
                )
                self.assertIsNone(
                    modal._timer,
                    f"Iteration {i}: modal._timer was NOT nulled!",
                )
                self.assertEqual(
                    len(modal._timers),
                    0,
                    f"Iteration {i}: lingering timers on modal._timers: {modal._timers}",
                )
                self.assertEqual(
                    len(modal.children),
                    0,
                    f"Iteration {i}: children were NOT detached!",
                )

            # Global timer leak verification
            self.assertEqual(
                len(app._timers),
                initial_timers,
                f"Global timer leak detected! app._timers grew from {initial_timers} to {len(app._timers)}",
            )

    async def test_copy_timer_cancellation_on_immediate_dismiss(self) -> None:
        """Verify that copy button's 2.5s reset timer does not leak when dismissed immediately."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.profile)

        async with app.run_test() as pilot:
            for i in range(10):
                modal = CodeDisplayModal(code=f"COPY_{i:04d}", item_label="CopyItem")
                app.push_screen(modal)
                await pilot.pause()

                # Trigger copy action (creates 2.5s set_timer)
                with patch("authy_local.interaction.copy_code"):
                    await pilot.press("c")
                    await pilot.pause()

                # Immediately dismiss
                await pilot.press("escape")
                await pilot.pause()

                self.assertEqual(modal.code, "")
                self.assertIsNone(modal._timer)

            # Allow time for any lingering timer callbacks to fire
            await asyncio.sleep(0.5)
            await pilot.pause()

            self.assertEqual(len(app._timers), 0)
            self.assertTrue(app.is_running)


class TestCodeModalMemoryLeakAudit(unittest.IsolatedAsyncioTestCase):
    """Memory leakage and heap inspection audit for dismissed secret tokens."""

    def setUp(self) -> None:
        self.dummy_dispatch: Callable = lambda args, out, diag: 0
        self.profile = {"onepassword": {"account": "acc1", "vault": "vault1"}}

    async def test_instance_attribute_sanitization_audit(self) -> None:
        """Inspect all instance attributes of dismissed modal to verify zero secret retention."""
        secret_token = "LEAK_CANARY_847291"
        modal = CodeDisplayModal(code=secret_token, item_label="CriticalCanary")

        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.profile)
        async with app.run_test() as pilot:
            app.push_screen(modal)
            await pilot.pause()
            self.assertEqual(modal.code, secret_token)

            # Dismiss
            await pilot.press("escape")
            await pilot.pause()

            # 1. Direct code attribute
            self.assertEqual(modal.code, "")

            # 2. Inspect entire __dict__
            for attr_name, attr_val in modal.__dict__.items():
                if isinstance(attr_val, str):
                    self.assertNotIn(
                        secret_token,
                        attr_val,
                        f"Secret token retained in modal attribute '{attr_name}': {attr_val}",
                    )

            # 3. Refresh callback nulled
            self.assertIsNone(modal.refresh_callback)

            # 4. Timer nulled
            self.assertIsNone(modal._timer)

            # 5. Children detached
            self.assertEqual(len(modal.children), 0)

    async def test_heap_memory_audit_after_garbage_collection(self) -> None:
        """Perform heap-wide inspection via gc to verify no lingering CodeDisplayModal holds tokens."""
        app = AuthyApp(dispatch=self.dummy_dispatch, profiles=self.profile)

        async with app.run_test() as pilot:
            tokens = [f"CANARY_TOKEN_{idx:05d}" for idx in range(10)]

            for tok in tokens:
                modal = CodeDisplayModal(code=tok, item_label="Canary")
                app.push_screen(modal)
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                del modal

            # Run full garbage collection cycles
            gc.collect()
            gc.collect()

            # Inspect all remaining CodeDisplayModal objects on heap
            lingering_modals = [
                obj for obj in gc.get_objects() if isinstance(obj, CodeDisplayModal)
            ]
            for m in lingering_modals:
                self.assertEqual(
                    m.code,
                    "",
                    f"Lingering modal on heap still retains code: {m.code}",
                )
                for tok in tokens:
                    for attr_name, attr_val in m.__dict__.items():
                        if isinstance(attr_val, str):
                            self.assertNotIn(
                                tok,
                                attr_val,
                                f"Lingering modal retained token {tok} in {attr_name}",
                            )
