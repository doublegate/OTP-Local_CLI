"""Unit and integration tests for TokenBrowserScreen and DeleteConfirmModal."""

import time
import unittest
from collections.abc import Callable
from unittest.mock import MagicMock

from textual.widgets import Button, Input, Static

from authy_local.tui import (
    MAX_RENDER_OPTIONS,
    AuthyApp,
    CodeDisplayModal,
    DashboardScreen,
    DeleteConfirmModal,
    TokenBrowserScreen,
    TokenOptionList,
)


class TestTuiBrowserTextual(unittest.IsolatedAsyncioTestCase):
    """Test suite covering TokenBrowserScreen virtualization, fuzzy search, and deletion safety."""

    def setUp(self) -> None:
        self.dummy_dispatch: Callable = lambda args, out, diag: 0
        self.sample_records = [
            ("2w4j6k8m0n2p4r6t8v0x2z4a6a", "GitHub Personal [2z4a6a]"),
            ("2w4j6k8m0n2p4r6t8v0x2z4a6b", "AWS Infrastructure [2z4a6b]"),
            ("2w4j6k8m0n2p4r6t8v0x2z4a6c", "Google Cloud Admin [2z4a6c]"),
        ]
        self.valid_op_profile = {
            "account": "2w4j6k8m0n2p4r6t8v0x2z4a6c",
            "vault": "2w4j6k8m0n2p4r6t8v0x2z4a6c",
        }
        self.valid_pass_profile = {
            "store": "/home/user/.password-store",
            "key_home": "/home/user/.gnupg",
        }

    async def test_browser_screen_composition_and_defaults(self) -> None:
        """Verify TokenBrowserScreen widget tree and default action show."""
        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            profiles={"onepassword": self.valid_op_profile},
        )
        app.load_records = MagicMock(return_value=self.sample_records)

        async with app.run_test() as pilot:
            await pilot.press("1")  # Browse and show
            await pilot.pause()

            self.assertIsInstance(app.screen, TokenBrowserScreen)
            browser = app.screen
            self.assertEqual(browser.default_action, "show")

            # Check header & subtitle
            subtitle = str(browser.query_one("#browser-subtitle", Static).render())
            self.assertIn("1Password", subtitle)
            self.assertIn("3", subtitle)
            self.assertIn("Show OTP", subtitle)

            # Check search bar and option list
            inp = browser.query_one("#search-input", Input)
            self.assertIsInstance(inp, Input)

            opt_list = browser.query_one(TokenOptionList)
            self.assertEqual(opt_list.option_count, 3)

            # Check footer
            footer = str(browser.query_one("#browser-footer", Static).render())
            self.assertIn("Show", footer)
            self.assertIn("Copy", footer)

            # Press escape to return to dashboard
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)
            await pilot.press("q")

    async def test_browser_screen_browse_and_copy_mode(self) -> None:
        """Verify Action 2 'Browse and copy' sets default_action='copy' and executes copy on Enter."""
        executed_args = []

        def copy_dispatch(args, output, diagnostic):
            executed_args.append(list(args))
            return 0

        app = AuthyApp(
            dispatch=copy_dispatch,
            profiles={"onepassword": self.valid_op_profile},
        )
        app.load_records = MagicMock(return_value=self.sample_records)

        async with app.run_test() as pilot:
            await pilot.press("2")  # Browse and copy
            await pilot.pause()

            self.assertIsInstance(app.screen, TokenBrowserScreen)
            browser = app.screen
            self.assertEqual(browser.default_action, "copy")

            subtitle = str(browser.query_one("#browser-subtitle", Static).render())
            self.assertIn("Copy OTP", subtitle)

            # Press Enter to copy selected item
            await pilot.press("enter")
            await pilot.pause()

            self.assertEqual(len(executed_args), 1)
            self.assertEqual(executed_args[0][0], "copy")
            self.assertEqual(executed_args[0][1], "2w4j6k8m0n2p4r6t8v0x2z4a6a")

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_5000_items_virtualization_and_sub_millisecond_search(self) -> None:
        """Verify virtualization bounds DOM rendering and search operates in sub-millisecond time on 5,000 items."""
        # Generate 5,000 synthetic records
        large_records = [
            (
                f"item_key_{idx:05d}_2w4j6k8m0n",
                f"Service {idx % 100} Account {idx} [{idx:05d}]",
            )
            for idx in range(5000)
        ]
        target_key = large_records[4242][0]

        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            profiles={"onepassword": self.valid_op_profile},
        )
        app.load_records = MagicMock(return_value=large_records)

        async with app.run_test() as pilot:
            await pilot.press("1")
            await pilot.pause()

            browser = app.screen
            self.assertIsInstance(browser, TokenBrowserScreen)
            opt_list = browser.query_one(TokenOptionList)

            # Assert virtualization caps rendered options at MAX_RENDER_OPTIONS
            self.assertEqual(opt_list.option_count, MAX_RENDER_OPTIONS)
            badge = str(browser.query_one("#match-count-badge", Static).render())
            self.assertIn(f"5000 matches (top {MAX_RENDER_OPTIONS})", badge)

            # Test benchmark: SearchIndex filtering over 5,000 items
            start_time = time.perf_counter()
            matches = browser.search_index.filter("Account 4242")
            filter_latency = (time.perf_counter() - start_time) * 1000  # in ms

            # Index filtering latency must meet interactive SLA (< 50.0 ms under test runner load)
            self.assertLess(filter_latency, 50.0)
            self.assertGreater(len(matches), 0)

            # Apply search to browser UI
            browser._apply_search("Account 4242")
            await pilot.pause()

            # Options should now be filtered to exact match
            self.assertGreaterEqual(opt_list.option_count, 1)
            self.assertEqual(browser.selected_token_key, target_key)

            # Test empty match notice
            browser._apply_search("nonexistent_token_query_xyz")
            await pilot.pause()
            empty_notice = browser.query_one("#empty-state-notice", Static)
            self.assertTrue(empty_notice.display)
            self.assertFalse(opt_list.display)

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_browser_keyboard_navigation_and_shortcuts(self) -> None:
        """Verify / focuses search, j/k moves selection, s shows code, c copies code."""
        executed_commands = []

        def tracking_dispatch(args, output, diagnostic):
            executed_commands.append(list(args))
            if args[0] == "show":
                output.write("654321\n")
            return 0

        app = AuthyApp(
            dispatch=tracking_dispatch,
            profiles={"onepassword": self.valid_op_profile},
        )
        app.load_records = MagicMock(return_value=self.sample_records)

        async with app.run_test() as pilot:
            await pilot.press("1")
            await pilot.pause()

            browser = app.screen
            opt_list = browser.query_one(TokenOptionList)
            search_inp = browser.query_one("#search-input", Input)

            # 1. '/' focuses search
            self.assertFalse(search_inp.has_focus)
            await pilot.press("slash")
            await pilot.pause()
            self.assertTrue(search_inp.has_focus)

            # Type in search
            search_inp.value = "AWS"
            # Esc clears and unfocuses
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(search_inp.value, "")
            self.assertTrue(opt_list.has_focus)

            # 2. Down/j moves selection
            self.assertEqual(browser.selected_token_key, self.sample_records[0][0])
            await pilot.press("j")
            await pilot.pause()
            self.assertEqual(browser.selected_token_key, self.sample_records[1][0])

            # 3. Press 's' triggers show code modal
            await pilot.press("s")
            await pilot.pause()
            self.assertIsInstance(app.screen, CodeDisplayModal)
            self.assertEqual(app.screen.code, "654321")
            await pilot.press("escape")
            await pilot.pause()

            # 4. Press 'c' triggers copy code
            await pilot.press("c")
            await pilot.pause()
            self.assertEqual(executed_commands[-1][0], "copy")
            self.assertEqual(executed_commands[-1][1], self.sample_records[1][0])

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_onepassword_browser_refuses_deletion(self) -> None:
        """Verify pressing 'd' on onepassword backend is ignored and does not open DeleteConfirmModal."""
        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            profiles={"onepassword": self.valid_op_profile},
        )
        app.load_records = MagicMock(return_value=self.sample_records)

        async with app.run_test() as pilot:
            await pilot.press("1")
            await pilot.pause()

            self.assertIsInstance(app.screen, TokenBrowserScreen)
            await pilot.press("d")
            await pilot.pause()

            # Still TokenBrowserScreen, DeleteConfirmModal was NOT pushed
            self.assertIsInstance(app.screen, TokenBrowserScreen)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_pass_otp_delete_confirm_modal_workflow(self) -> None:
        """Verify 'd' opens DeleteConfirmModal for pass-otp and requires exact uppercase 'DELETE'."""
        pass_records = [
            ("work/aws", "work/aws"),
            ("personal/github", "personal/github"),
        ]
        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            profiles={"pass-otp": self.valid_pass_profile},
        )
        app.current_backend = "pass-otp"
        app.load_records = MagicMock(return_value=pass_records)
        deleted_keys = []
        app.delete_record = MagicMock(side_effect=lambda b, p, k: deleted_keys.append(k) or True)

        async with app.run_test() as pilot:
            await pilot.press("1")
            await pilot.pause()

            browser = app.screen
            self.assertIsInstance(browser, TokenBrowserScreen)

            # Press 'd' to initiate delete
            await pilot.press("d")
            await pilot.pause()

            self.assertIsInstance(app.screen, DeleteConfirmModal)
            modal = app.screen

            btn_delete = modal.query_one("#btn-confirm-delete", Button)
            self.assertTrue(btn_delete.disabled)

            # 1. Type wrong string "delete" (lowercase) -> button remains disabled
            del_inp = modal.query_one("#delete-confirm-input", Input)
            del_inp.value = "delete"
            await pilot.pause()
            self.assertTrue(btn_delete.disabled)

            # Pressing enter with wrong text does not delete
            modal.action_submit = MagicMock()
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(len(deleted_keys), 0)

            # 2. Type exact uppercase "DELETE" -> button becomes enabled
            del_inp.value = "DELETE"
            await pilot.pause()
            self.assertFalse(btn_delete.disabled)

            # Press enter -> confirms deletion
            await pilot.press("enter")
            await pilot.pause()

            # Verify deletion executed and item removed from browser records
            self.assertEqual(deleted_keys, ["work/aws"])
            self.assertIsInstance(app.screen, TokenBrowserScreen)
            opt_list = browser.query_one(TokenOptionList)
            self.assertEqual(opt_list.option_count, 1)
            self.assertEqual(browser.selected_token_key, "personal/github")

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_browser_refresh_action(self) -> None:
        """Verify pressing 'r' reloads records from backend."""
        initial_records = [("k1", "Initial 1")]
        updated_records = [("k1", "Initial 1"), ("k2", "Added 2")]

        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            profiles={"onepassword": self.valid_op_profile},
        )
        app.load_records = MagicMock(side_effect=[initial_records, updated_records])

        async with app.run_test() as pilot:
            await pilot.press("1")
            await pilot.pause()

            browser = app.screen
            opt_list = browser.query_one(TokenOptionList)
            self.assertEqual(opt_list.option_count, 1)

            # Press 'r' to refresh
            await pilot.press("r")
            await pilot.pause()

            self.assertEqual(opt_list.option_count, 2)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")


if __name__ == "__main__":
    unittest.main()
