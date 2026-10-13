"""Milestone M5 Adversarial Test Runner Stress & Concurrency Suite.

Authored by Challenger 1 (Empirical Challenger) to test:
1. Concurrency hammering: Rapid pilot interactions on TokenBrowserScreen & TokenOptionList.
2. Search debouncing stress: Rapid keystrokes and queries without debounce starvation or state corruption.
3. Boundary & empty-state slamming: Rapid navigation and actions on 0-item, 1-item, and 5,000-item lists.
4. Modal cycle hammering: Rapid show modal push/pop, help overlay push/pop, delete modal push/pop.
5. Pathological & adversarial queries: Extreme string lengths, control chars, ANSI sequences, unicode/emojis.
"""

import time
import unittest
from collections.abc import Callable
from unittest.mock import MagicMock

from textual.widgets import Input, Static

from authy_local.tui import (
    AuthyApp,
    CodeDisplayModal,
    HelpModal,
    TokenBrowserScreen,
    TokenOptionList,
)


class TestM5RunnerStressChallenger1(unittest.IsolatedAsyncioTestCase):
    """Adversarial stress and concurrency harness for TokenBrowserScreen and TokenOptionList."""

    def setUp(self) -> None:
        self.dummy_dispatch: Callable = lambda args, out, diag: 0
        self.sample_records = [
            ("item_gh_001", "GitHub Personal [001]"),
            ("item_aws_002", "AWS Production [002]"),
            ("item_gcp_003", "Google Cloud Admin [003]"),
            ("item_slack_004", "Slack Workspace [004]"),
            ("item_db_005", "Dropbox Corporate [005]"),
        ]
        self.valid_op_profile = {
            "account": "2w4j6k8m0n2p4r6t8v0x2z4a6c",
            "vault": "2w4j6k8m0n2p4r6t8v0x2z4a6c",
        }
        self.valid_pass_profile = {
            "store": "/home/user/.password-store",
            "key_home": "/home/user/.gnupg",
        }

    async def test_rapid_search_keystroke_and_debounce_hammering(self) -> None:
        """Hammer search input with 50 rapid text modifications and verify debounce resolution."""
        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            profiles={"onepassword": self.valid_op_profile},
        )
        app.load_records = MagicMock(return_value=self.sample_records)

        async with app.run_test() as pilot:
            await pilot.press("1")  # Open browser
            await pilot.pause()

            browser = app.screen
            self.assertIsInstance(browser, TokenBrowserScreen)
            search_input = browser.query_one("#search-input", Input)
            opt_list = browser.query_one(TokenOptionList)

            # Rapidly modify input 50 times faster than the 35ms debounce timer
            search_terms = [
                "g",
                "gi",
                "git",
                "gith",
                "github",
                "git",
                "gi",
                "g",
                "",
                "a",
                "aw",
                "aws",
                "a",
                "",
                "s",
                "sl",
                "sla",
                "slack",
                "slac",
                "sla",
                "sl",
                "s",
                "",
                "d",
                "dr",
                "dro",
                "drop",
                "dropbox",
                "",
                "nonexistent",
                "nonexistent1",
                "nonexistent2",
                "non",
                "no",
                "",
                "x",
                "xy",
                "xyz",
                "",
                "1",
                "00",
                "001",
                "00",
                "0",
                "",
                "Google",
                "Goog",
                "G",
                "AWS Production",
            ]

            for term in search_terms:
                search_input.value = term
                # Do NOT await sleep(0.035) — intentionally interleave faster than debounce
                await pilot.pause(0.002)

            # Allow debounce timer to settle
            await pilot.pause(0.08)

            # State must reflect the final search term ("AWS Production")
            self.assertEqual(browser.current_query, "AWS Production")
            self.assertEqual(opt_list.option_count, 1)
            self.assertEqual(browser.selected_token_key, "item_aws_002")

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_rapid_navigation_and_boundary_slamming(self) -> None:
        """Slam navigation keys up/down/j/k rapidly across boundaries and verify zero index crashes."""
        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            profiles={"onepassword": self.valid_op_profile},
        )
        app.load_records = MagicMock(return_value=self.sample_records)

        async with app.run_test() as pilot:
            await pilot.press("1")
            await pilot.pause()

            browser = app.screen
            self.assertIsInstance(browser, TokenBrowserScreen)
            opt_list = browser.query_one(TokenOptionList)

            # 1. OptionList starts at index 0
            self.assertEqual(opt_list.highlighted, 0)
            self.assertEqual(browser.selected_token_key, "item_gh_001")

            # 2. Moving up from index 0 circularly wraps to the last item (index 4)
            await pilot.press("up")
            await pilot.pause(0.005)
            self.assertEqual(opt_list.highlighted, len(self.sample_records) - 1)
            self.assertEqual(browser.selected_token_key, "item_db_005")

            # 3. Moving down from the last item circularly wraps back to index 0
            await pilot.press("down")
            await pilot.pause(0.005)
            self.assertEqual(opt_list.highlighted, 0)
            self.assertEqual(browser.selected_token_key, "item_gh_001")

            # 4. Rapidly hammer down 4 times to step through to index 4
            for _ in range(4):
                await pilot.press("down")
                await pilot.pause(0.005)
            self.assertEqual(opt_list.highlighted, 4)
            self.assertEqual(browser.selected_token_key, "item_db_005")

            # 5. Alternate j and k rapidly 30 times without losing selection integrity
            for _ in range(15):
                await pilot.press("k")
                await pilot.pause(0.002)
                await pilot.press("j")
                await pilot.pause(0.002)
            self.assertEqual(opt_list.highlighted, 4)
            self.assertEqual(browser.selected_token_key, "item_db_005")

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_empty_catalog_action_slamming(self) -> None:
        """Slam all action keys (enter, s, c, d, r, j, k) on an empty catalog without crashing."""
        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            profiles={"onepassword": self.valid_op_profile},
        )
        app.load_records = MagicMock(return_value=[])

        async with app.run_test() as pilot:
            await pilot.press("1")
            await pilot.pause()

            browser = app.screen
            self.assertIsInstance(browser, TokenBrowserScreen)
            empty_notice = browser.query_one("#empty-state-notice", Static)
            self.assertTrue(empty_notice.display)
            self.assertIsNone(browser.selected_token_key)

            # Hammer all action keys repeatedly
            for key in ("enter", "s", "c", "d", "r", "j", "k", "up", "down", "slash"):
                for _ in range(5):
                    await pilot.press(key)
            await pilot.pause()

            # Ensure browser screen remains stably mounted and no unhandled error occurred
            self.assertIsInstance(app.screen, TokenBrowserScreen)
            self.assertIsNone(browser.selected_token_key)

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_rapid_modal_push_pop_cycles(self) -> None:
        """Rapidly push and pop CodeDisplayModal and HelpOverlayModal 20 times in quick succession."""
        show_calls = 0

        def counting_dispatch(args, out, diag):
            nonlocal show_calls
            if args[0] == "show":
                show_calls += 1
                out.write("987654\n")
            return 0

        app = AuthyApp(
            dispatch=counting_dispatch,
            profiles={"onepassword": self.valid_op_profile},
        )
        app.load_records = MagicMock(return_value=self.sample_records)

        async with app.run_test() as pilot:
            await pilot.press("1")
            await pilot.pause()

            browser = app.screen
            self.assertIsInstance(browser, TokenBrowserScreen)

            # 1. Rapidly push and dismiss CodeDisplayModal 15 times
            for _ in range(15):
                await pilot.press("s")
                await pilot.pause(0.005)
                self.assertIsInstance(app.screen, CodeDisplayModal)
                await pilot.press("escape")
                await pilot.pause(0.005)
                self.assertIsInstance(app.screen, TokenBrowserScreen)

            self.assertEqual(show_calls, 15)

            # 2. Rapidly push and dismiss HelpOverlayModal 15 times
            for _ in range(15):
                await pilot.press("f1")
                await pilot.pause(0.005)
                self.assertIsInstance(app.screen, HelpModal)
                await pilot.press("escape")
                await pilot.pause(0.005)
                self.assertIsInstance(app.screen, TokenBrowserScreen)

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_pathological_search_queries_stress(self) -> None:
        """Feed adversarial, extreme, and pathological search queries into TokenBrowserScreen."""
        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            profiles={"onepassword": self.valid_op_profile},
        )
        app.load_records = MagicMock(return_value=self.sample_records)

        async with app.run_test() as pilot:
            await pilot.press("1")
            await pilot.pause()

            browser = app.screen
            self.assertIsInstance(browser, TokenBrowserScreen)

            pathological_inputs = [
                # Extremely long queries
                "A" * 10000,
                "github" + "x" * 5000,
                # Regex characters that could blow up non-escaped regexes
                ".*+?^${}()|[]\\",
                "[a-z]+.*(?=test)",
                "(((((((((())))))))))",
                # Special control & ANSI escape sequences
                "\x1b[31;1mANSI_RED\x1b[0m",
                "\x00\x01\x02\x03\x04\x05\x06\x07\x08",
                "\t\n\r\v\f",
                # Unicode & emojis & zero-width chars
                "🔑🔒 Authenticator 🚀 日本語 العربية",
                "\u200b\u200c\u200d\ufeff",
                # Whitespace edge cases
                "      ",
                "   GitHub   ",
            ]

            for query in pathological_inputs:
                with self.subTest(query=query[:20]):
                    browser._apply_search(query)
                    await pilot.pause(0.002)
                    # Screen must remain valid and operational
                    self.assertIsInstance(app.screen, TokenBrowserScreen)

            # Re-verify that normal query immediately recovers full functionality
            browser._apply_search("GitHub")
            await pilot.pause(0.01)
            opt_list = browser.query_one(TokenOptionList)
            self.assertEqual(opt_list.option_count, 1)
            self.assertEqual(browser.selected_token_key, "item_gh_001")

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_5000_items_rapid_filter_and_refresh_hammering(self) -> None:
        """Concurrently hammer 5,000 items with rapid filter switches and refresh reload calls."""
        large_records = [
            (f"key_{idx:05d}", f"Service {idx % 200} Account {idx} [{idx:05d}]")
            for idx in range(5000)
        ]
        large_records[42] = ("key_00042", "UniqueSpecialService Alpha [00042]")

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

            # Rapidly cycle between filters and refreshes 20 times
            t0 = time.perf_counter()
            for i in range(20):
                if i % 2 == 0:
                    browser._apply_search(f"Service {i % 10}")
                elif i % 3 == 0:
                    browser.action_refresh_list()
                else:
                    browser._apply_search("")
                await pilot.pause(0.002)

            elapsed = (time.perf_counter() - t0) * 1000
            # 20 operations across 5,000 items should complete with high responsiveness (< 1500ms total)
            self.assertLess(elapsed, 1500.0)

            # Verify final search state
            browser._apply_search("UniqueSpecialService Alpha")
            await pilot.pause(0.01)
            self.assertEqual(opt_list.option_count, 1)
            self.assertEqual(browser.selected_token_key, "key_00042")

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")


if __name__ == "__main__":
    unittest.main()
