"""Adversarial Stress Test Suite for Milestone M2 (Textual TUI Foundation).

Authored by Challenger 1 (Empirical Challenger) to rigorously stress test:
1. Boundary sizing: Resize below 60x18, extreme geometries (10x5, 1x1), rapid resize thrashing,
   verify MinSizeWarning displays and dismisses cleanly, and no unhandled crashes occur.
2. Rapid event stress: Hammer action keybindings (1-8, b, p, ?, arrows, j/k, Enter) across
   600+ rapid events; verify OptionList modulo wrapping and workspace synchronization.
3. Concurrency & reactive updates: Rapidly update app.current_backend and app.session_status
   from concurrent async tasks and background OS threads.
4. Suspension error injection: Verify safe_suspend and execute() behavior when callbacks
   raise diverse unexpected exceptions (AppError, KeyboardInterrupt, ZeroDivisionError,
   RuntimeError, PermissionError), ensuring no state corruption.
"""

import asyncio
import random
import threading
import time
import unittest
from unittest.mock import MagicMock

from textual.events import Key

from authy_local.errors import MESSAGES, AppError
from authy_local.tui import (
    ACTIONS,
    ActionListView,
    AuthyApp,
    DashboardScreen,
    DetailWorkspace,
    HeaderBar,
    MinSizeWarning,
    SessionStatusPanel,
)


class TestM2AdversarialTui(unittest.IsolatedAsyncioTestCase):
    """Adversarial stress harness for AuthyApp under Textual's headless pilot."""

    async def test_boundary_sizing_extremes_and_recovery(self) -> None:
        """Boundary sizing: Test min dimensions (60x18), sub-thresholds, and recovery."""
        app = AuthyApp()
        async with app.run_test() as pilot:
            screen = app.screen
            self.assertIsInstance(screen, DashboardScreen)
            warning = screen.query_one(MinSizeWarning)

            # 1. Standard viewport (80x24)
            await pilot.resize_terminal(80, 24)
            await pilot.pause()
            self.assertFalse(screen.has_class("too-small"))
            self.assertFalse(screen.has_class("compact-width"))
            self.assertFalse(screen.has_class("compact-height"))
            self.assertFalse(warning.display)

            # 2. Exact boundary threshold (60x18)
            await pilot.resize_terminal(60, 18)
            await pilot.pause()
            self.assertFalse(screen.has_class("too-small"))
            self.assertTrue(screen.has_class("compact-width"))
            self.assertTrue(screen.has_class("compact-height"))
            self.assertFalse(warning.display)

            # 3. Sub-threshold width only (59x18)
            await pilot.resize_terminal(59, 18)
            await pilot.pause()
            self.assertTrue(screen.has_class("too-small"))
            self.assertTrue(warning.display)

            # 4. Sub-threshold height only (60x17)
            await pilot.resize_terminal(60, 17)
            await pilot.pause()
            self.assertTrue(screen.has_class("too-small"))
            self.assertTrue(warning.display)

            # 5. Both sub-threshold (59x17)
            await pilot.resize_terminal(59, 17)
            await pilot.pause()
            self.assertTrue(screen.has_class("too-small"))
            self.assertTrue(warning.display)

            # 6. Extreme tiny viewport (10x5)
            await pilot.resize_terminal(10, 5)
            await pilot.pause()
            self.assertTrue(screen.has_class("too-small"))

            # 7. Extreme unit viewport (1x1)
            await pilot.resize_terminal(1, 1)
            await pilot.pause()
            self.assertTrue(screen.has_class("too-small"))

            # 8. Receiving input while too-small must not raise unhandled exceptions
            for k in ["1", "2", "j", "k", "down", "up", "b", "p"]:
                app._driver.send_message(Key(k, k))
            await pilot.pause()
            self.assertTrue(app.is_running)

            # 9. Clean recovery to standard viewport (80x24)
            await pilot.resize_terminal(80, 24)
            await pilot.pause()
            self.assertFalse(screen.has_class("too-small"))
            self.assertFalse(warning.display)

    async def test_boundary_rapid_resize_thrashing(self) -> None:
        """Boundary sizing: Rapidly alternate viewports across compact, standard, and tiny."""
        app = AuthyApp()
        viewports = [
            (80, 24),
            (55, 15),
            (75, 20),
            (30, 10),
            (100, 35),
            (60, 18),
            (59, 18),
            (60, 17),
            (70, 24),
            (85, 24),
        ]
        random.seed(2026)

        async with app.run_test() as pilot:
            sidebar = app.screen.query_one(ActionListView)
            workspace = app.screen.query_one(DetailWorkspace)

            sidebar.highlighted = 3
            await pilot.pause()

            # Thrash through 50 random resize events
            for _ in range(50):
                w, h = random.choice(viewports)
                await pilot.resize_terminal(w, h)
                await pilot.pause()

            # Restore to standard dimensions
            await pilot.resize_terminal(80, 24)
            await pilot.pause()

            # Verify widget integrity and highlighted option retention
            self.assertTrue(app.is_running)
            self.assertEqual(sidebar.highlighted, 3)
            self.assertEqual(workspace.selected_index, 3)

    async def test_rapid_event_stress_hammering(self) -> None:
        """Rapid event stress: Hammer 600+ key events in rapid succession."""
        doctor_invocations = 0

        def stress_dispatch(args, out, diag):
            nonlocal doctor_invocations
            if args[0] == "doctor":
                doctor_invocations += 1
                out.write("platform: available\nop: available\n")
                return 0
            return 0

        app = AuthyApp(dispatch=stress_dispatch)
        stress_keys = [
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
            "b",
            "p",
            "question_mark",
            "up",
            "down",
            "j",
            "k",
            "enter",
        ]
        random.seed(42)
        event_stream = [random.choice(stress_keys) for _ in range(600)]

        t_start = time.perf_counter()
        async with app.run_test() as pilot:
            for k in event_stream:
                char = k if len(k) == 1 else None
                app._driver.send_message(Key(k, char))

            await pilot.pause()
            t_elapsed = time.perf_counter() - t_start

            sidebar = app.screen.query_one(ActionListView)
            workspace = app.screen.query_one(DetailWorkspace)

            # Assert complete handling of all 600 events
            self.assertTrue(app.is_running)
            self.assertGreater(doctor_invocations, 0)
            self.assertIsNotNone(sidebar.highlighted)
            self.assertGreaterEqual(sidebar.highlighted, 0)
            self.assertLess(sidebar.highlighted, len(ACTIONS))
            self.assertEqual(workspace.selected_index, sidebar.highlighted)

            # Verification that 600 events dispatched in under 5 seconds
            self.assertLess(t_elapsed, 5.0)

    async def test_action_option_list_wrapping_invariants(self) -> None:
        """Rapid event stress: Verify OptionList wraps circularly without bounds errors."""
        app = AuthyApp()
        async with app.run_test() as pilot:
            sidebar = app.screen.query_one(ActionListView)
            workspace = app.screen.query_one(DetailWorkspace)

            # Hammer cursor_down actions (10 full cycles)
            for _ in range(10 * len(ACTIONS)):
                sidebar.action_cursor_down()
            await pilot.pause()
            self.assertEqual(sidebar.highlighted, 0)
            self.assertEqual(workspace.selected_index, 0)

            # Advance by 5 steps
            for _ in range(5):
                sidebar.action_cursor_down()
            await pilot.pause()
            self.assertEqual(sidebar.highlighted, 5)
            self.assertEqual(workspace.selected_index, 5)

            # Hammer cursor_up actions (10 full backward cycles)
            for _ in range(10 * len(ACTIONS)):
                sidebar.action_cursor_up()
            await pilot.pause()
            self.assertEqual(sidebar.highlighted, 5)
            self.assertEqual(workspace.selected_index, 5)

    async def test_concurrency_async_reactive_state_updates(self) -> None:
        """Concurrency: 4 concurrent async tasks rapidly mutating reactive fields."""
        app = AuthyApp()
        async with app.run_test() as pilot:
            header = app.screen.query_one(HeaderBar)
            status_panel = app.screen.query_one(SessionStatusPanel)
            backends = ["onepassword", "pass-otp", "totpm"]

            async def async_mutator(task_id: int):
                for i in range(100):
                    app.current_backend = backends[(task_id + i) % 3]
                    app.session_status = f"Task {task_id} iteration {i}"
                    await asyncio.sleep(0.0001)

            tasks = [asyncio.create_task(async_mutator(i)) for i in range(4)]
            await asyncio.gather(*tasks)
            await pilot.pause()

            self.assertIn(header.backend, backends)
            self.assertTrue(status_panel.status.startswith("Task "))
            self.assertTrue(app.is_running)

    async def test_concurrency_multithreaded_reactive_hammer(self) -> None:
        """Concurrency: 8 background OS threads concurrently mutating reactive properties."""
        app = AuthyApp()
        async with app.run_test() as pilot:
            thread_errors = []
            backends = ["onepassword", "pass-otp", "totpm"]

            def thread_worker(tid: int):
                try:
                    for i in range(50):
                        app.current_backend = backends[(tid + i) % 3]
                        app.session_status = f"Thread-{tid}:{i}"
                        time.sleep(0.0002)
                except Exception as exc:
                    thread_errors.append(exc)

            threads = [threading.Thread(target=thread_worker, args=(t,)) for t in range(8)]
            for t in threads:
                t.start()

            # Non-blocking async loop yield while threads execute
            while any(t.is_alive() for t in threads):
                await asyncio.sleep(0.005)

            for t in threads:
                t.join()

            await pilot.pause()
            self.assertEqual(thread_errors, [])
            self.assertTrue(app.is_running)

    async def test_suspension_error_injection_execute_resilience(self) -> None:
        """Suspension error injection: Verify execute() safely catches diverse errors."""
        app = AuthyApp()

        # 1. Injected AppError variations
        for exit_code in [2, 4, 5, 6, 7]:

            def error_dispatch(args, out, diag, code=exit_code):
                raise AppError(code)

            app.dispatch_callback = error_dispatch
            status, summary, lines = app.execute(["show", "item1"])
            self.assertEqual(status, exit_code)
            self.assertEqual(lines, [MESSAGES.get(exit_code, MESSAGES[3])])
            self.assertIsNone(summary)

        # 2. Injected KeyboardInterrupt (SIGINT)
        def interrupt_dispatch(args, out, diag):
            raise KeyboardInterrupt()

        app.dispatch_callback = interrupt_dispatch
        status, _, _ = app.execute(["show", "item1"])
        self.assertEqual(status, 130)

        # 3. Injected diverse unhandled exceptions
        for exc in [
            ZeroDivisionError("divide by zero"),
            KeyError("missing_key"),
            PermissionError("denied"),
            RuntimeError("backend process terminated"),
        ]:

            def exc_dispatch(args, out, diag, to_raise=exc):
                raise to_raise

            app.dispatch_callback = exc_dispatch
            status, _, lines = app.execute(["show", "item1"])
            self.assertEqual(status, 3)
            self.assertEqual(lines, [MESSAGES[3]])

        # 4. Injected buffer overflow (> 128 KB sink ceiling)
        def overflow_dispatch(args, out, diag):
            out.write("X" * 140000)
            return 0

        app.dispatch_callback = overflow_dispatch
        status, _, _ = app.execute(["doctor"])
        self.assertEqual(status, 5)

        # 5. Injected preview callback error
        def preview_error(wheel, out, diag):
            raise RuntimeError("corrupted wheel")

        app.preview_callback = preview_error
        status, _, lines = app.execute(["preview", "corrupt.whl"])
        self.assertEqual(status, 3)
        self.assertEqual(lines, [MESSAGES[3]])

    async def test_suspension_headless_driver_safe_fallback(self) -> None:
        """Suspension: Verify safe_suspend falls back gracefully under HeadlessDriver."""
        app = AuthyApp()
        executed = False
        async with app.run_test() as pilot:
            with app.safe_suspend():
                executed = True
            await pilot.pause()
            self.assertTrue(executed)
            self.assertTrue(app.is_running)

    async def test_suspension_interactive_mock_lifecycle(self) -> None:
        """Suspension: Verify mock driver lifecycle when suspend is supported."""
        app = AuthyApp()
        async with app.run_test() as pilot:
            mock_driver = MagicMock()
            mock_driver.can_suspend = True
            mock_driver.is_application_mode_suspended = False
            app._driver = mock_driver

            # Normal suspension lifecycle
            with app.safe_suspend():
                pass
            await pilot.pause()
            self.assertTrue(mock_driver.suspend_application_mode.called)
            self.assertTrue(mock_driver.resume_application_mode.called)

    async def test_suspension_unhandled_exception_investigation(self) -> None:
        """Suspension: Empirically document exception handling behavior during suspension."""
        app = AuthyApp()
        async with app.run_test():
            mock_driver = MagicMock()
            mock_driver.can_suspend = True
            app._driver = mock_driver

            # Test A: RuntimeError inside safe_suspend when can_suspend=True
            caught_exc = None
            try:
                with app.safe_suspend():
                    raise RuntimeError("simulated database failure")
            except Exception as err:
                caught_exc = err

            self.assertIsNotNone(caught_exc)
            # Verify that safe_suspend preserves the underlying exception without generator masking
            self.assertEqual(str(caught_exc), "simulated database failure")

            # Test B: In execute(), the generator error is caught and converted to status 3
            app.dispatch_callback = lambda args, out, diag: (_ for _ in ()).throw(
                RuntimeError("crash")
            )
            status, _, lines = app.execute(["doctor"])
            self.assertEqual(status, 3)
            self.assertEqual(lines, [MESSAGES[3]])


if __name__ == "__main__":
    unittest.main()
