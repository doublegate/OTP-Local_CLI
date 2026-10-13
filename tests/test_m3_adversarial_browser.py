"""Adversarial Stress Test Suite for Milestone M3 (Token Browser Scale & Deletion).

Authored by Challenger 2 (Empirical Challenger) to rigorously stress test:
1. Scale stress test: Populate TokenBrowserScreen with 5,000 realistic items,
   measuring search index filtering and UI filter rendering latencies.
2. Search query stress: Adversarial queries (empty string, Unicode, emojis,
   10,000-character strings, null bytes, special regex metacharacters `.*+?^${}()|[]\\`).
3. Deletion bypass stress: Test permutations of "delete", "Delete", " DELETE ", "DELETE\\n"
   in DeleteConfirmModal to ensure ONLY exact case-sensitive "DELETE" triggers deletion.
4. 1Password backend deletion refusal: Strict multi-layer refusal under `onepassword` backend
   (UI keybinding refusal, action method refusal, App.delete_record refusal, and remove() AppError).
"""

import sys
import time
import unittest
from collections.abc import Callable
from unittest.mock import MagicMock

from textual.widgets import Button, Input, Static

from authy_local.errors import AppError
from authy_local.tui import (
    MAX_RENDER_OPTIONS,
    AuthyApp,
    DeleteConfirmModal,
    TokenBrowserScreen,
    TokenOptionList,
)
from authy_local.tui_items import remove


class TestM3AdversarialBrowser(unittest.IsolatedAsyncioTestCase):
    """Adversarial stress harness for TokenBrowserScreen and DeleteConfirmModal."""

    def setUp(self) -> None:
        self.dummy_dispatch: Callable = lambda args, out, diag: 0
        self.valid_op_profile = {
            "account": "2w4j6k8m0n2p4r6t8v0x2z4a6c",
            "vault": "2w4j6k8m0n2p4r6t8v0x2z4a6c",
        }
        self.valid_pass_profile = {
            "store": "/home/user/.password-store",
            "key_home": "/home/user/.gnupg",
        }

    async def test_scale_stress_5000_items_latency(self) -> None:
        """Scale stress test: Populate with 5,000 items and verify filter rendering latency."""
        # 1. Synthesize 5,000 realistic records
        services = [
            "GitHub",
            "AWS",
            "Google",
            "GitLab",
            "Slack",
            "Cloudflare",
            "Dropbox",
            "Stripe",
            "Zoom",
            "Bitbucket",
        ]
        large_records = [
            (
                f"item_key_{idx:05d}_hash",
                f"{services[idx % len(services)]} User-{idx:04d} [{idx:05d}]",
            )
            for idx in range(5000)
        ]

        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            profiles={"onepassword": self.valid_op_profile},
        )
        app.load_records = MagicMock(return_value=large_records)

        async with app.run_test() as pilot:
            # Mount TokenBrowserScreen
            await pilot.press("1")
            await pilot.pause()

            self.assertIsInstance(app.screen, TokenBrowserScreen)
            browser = app.screen
            opt_list = browser.query_one(TokenOptionList)

            # Initial render bounds DOM options to MAX_RENDER_OPTIONS
            self.assertEqual(opt_list.option_count, MAX_RENDER_OPTIONS)
            badge = str(browser.query_one("#match-count-badge", Static).render())
            self.assertIn(f"5000 matches (top {MAX_RENDER_OPTIONS})", badge)

            # 2. Pure search index filtering latency across 5,000 items
            is_tracing = sys.gettrace() is not None or "coverage" in sys.modules
            sla_ms = 35.0 if is_tracing else 25.0

            selective_queries = [
                "[04242]",
                "User-4242",
                "NonexistentToken_XYZ",
                "GitHub User-0001",
                "[00100]",
            ]
            for query in selective_queries:
                start_time = time.perf_counter()
                matches = browser.search_index.filter(query)
                filter_latency_ms = (time.perf_counter() - start_time) * 1000

                self.assertIsInstance(matches, list)
                self.assertLess(
                    filter_latency_ms,
                    sla_ms,
                    f"Index filter latency for {query!r} exceeded {sla_ms}ms: {filter_latency_ms:.2f}ms",
                )

            # 3. Full filter + UI OptionList render latency for selective queries
            for query in ["[04242]", "[00001]", "[01234]"]:
                start_time = time.perf_counter()
                browser._apply_search(query)
                total_latency_ms = (time.perf_counter() - start_time) * 1000

                self.assertLess(
                    total_latency_ms,
                    sla_ms,
                    f"Full filter rendering latency for {query!r} exceeded {sla_ms}ms: {total_latency_ms:.2f}ms",
                )
                self.assertGreaterEqual(opt_list.option_count, 1)

            # 4. Zero-match query latency
            start_time = time.perf_counter()
            browser._apply_search("totally_absent_token_query")
            zero_match_latency_ms = (time.perf_counter() - start_time) * 1000
            self.assertLess(
                zero_match_latency_ms,
                sla_ms,
                f"Zero-match render latency exceeded {sla_ms}ms: {zero_match_latency_ms:.2f}ms",
            )
            self.assertEqual(opt_list.option_count, 0)
            self.assertTrue(browser.query_one("#empty-state-notice", Static).display)

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_search_query_adversarial_stress(self) -> None:
        """Search query stress: Test empty string, Unicode, emojis, 10k chars, null bytes, regex specials."""
        records = [
            ("key_std", "Standard GitHub Token [gh01]"),
            ("key_uni_ar", "خدمة حساب توكن عربي [ar01]"),
            ("key_uni_zh", "測試服務 帳號 金鑰 [zh01]"),
            ("key_uni_ru", "Сервис Токен Доступ [ru01]"),
            ("key_uni_de", "Überprüfung Schlüssel Größe [de01]"),
            ("key_emoji", "Token 🔥🎉💀🚀🔑 Security [em01]"),
            ("key_null", "Null\x00Byte Service Token [nb01]"),
            ("key_regex", "Regex .*+?^${}()|[]\\ Token [rx01]"),
            ("key_long", "Long " + "x" * 2000 + " Service [lg01]"),
        ]

        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            profiles={"onepassword": self.valid_op_profile},
        )
        app.load_records = MagicMock(return_value=records)

        async with app.run_test() as pilot:
            await pilot.press("1")
            await pilot.pause()

            browser = app.screen
            self.assertIsInstance(browser, TokenBrowserScreen)
            opt_list = browser.query_one(TokenOptionList)

            adversarial_battery = [
                # Empty / whitespace
                ("", len(records)),
                ("   ", len(records)),
                ("\t\n", len(records)),
                # Unicode
                ("خدمة", 1),
                ("測試服務", 1),
                ("Сервис", 1),
                ("Überprüfung", 1),
                # Emojis
                ("🔥🎉", 1),
                ("💀🚀", 1),
                ("🔑", 1),
                # Null bytes
                ("\x00", 1),
                ("Null\x00Byte", 1),
                # Regex specials (must NOT trigger ReDoS or regex syntax errors)
                (".*+?^${}()|[]\\", 1),
                (".*", 1),
                ("(?=.*[a-z])", 0),
                ("(a+)+", 0),
                ("[a-z0-9_-]+", 0),
                ("[", len(records)),  # "[" is in every label's "[id]"
                ("]", len(records)),
                ("(", 1),  # matches key_regex
                (")", 1),  # matches key_regex
                ("\\", 1),
                ("^$", 1),  # literal match in key_regex
                ("^xyz$", 0),
                (".*.*.*.*.*.*b", 0),
                # 10,000-character massive string queries (must reject instantly without lag)
                ("a" * 10000, 0),
                (" " + "z" * 10000 + " ", 0),
                (".*" * 5000, 0),
                ("🔥" * 5000, 0),
            ]

            for query, expected_min_matches in adversarial_battery:
                start_time = time.perf_counter()
                browser._apply_search(query)
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                # Must not raise exceptions, must finish promptly (< 50ms under test harness)
                self.assertLess(
                    elapsed_ms,
                    50.0,
                    f"Adversarial query {query[:30]!r} (len={len(query)}) took too long: {elapsed_ms:.2f}ms",
                )

                if expected_min_matches > 0:
                    self.assertGreaterEqual(
                        opt_list.option_count,
                        expected_min_matches,
                        f"Query {query!r} expected at least {expected_min_matches} matches, got {opt_list.option_count}",
                    )
                else:
                    self.assertEqual(
                        opt_list.option_count,
                        0,
                        f"Query {query[:30]!r} should have 0 matches, got {opt_list.option_count}",
                    )

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_deletion_bypass_stress_permutations(self) -> None:
        """Deletion bypass stress: Test permutations of delete to ensure ONLY exact 'DELETE' authorizes removal."""
        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            profiles={"pass-otp": self.valid_pass_profile},
        )
        app.current_backend = "pass-otp"

        async with app.run_test() as pilot:
            bypass_permutations = [
                "delete",
                "Delete",
                " DELETE ",
                "DELETE\n",
                "DELETE ",
                " DELETE",
                "delete\n",
                "DeLeTe",
                "dElEtE",
                "",
                "   ",
                "\t",
                "DEL",
                "DELET",
                "DELETEE",
                "DELETE\x00",
                "DELETE\x00extra",
                "DELETE; DROP TABLE tokens;",
                "' OR '1'='1",
                "DELETE\r\n",
            ]

            for bypass_attempt in bypass_permutations:
                dismissed_value = None

                def on_dismiss(val: bool) -> None:
                    nonlocal dismissed_value
                    dismissed_value = val

                modal = DeleteConfirmModal("pass-otp", "test_entry_label")
                app.push_screen(modal, on_dismiss)
                await pilot.pause()

                inp = modal.query_one("#delete-confirm-input", Input)
                btn = modal.query_one("#btn-confirm-delete", Button)

                # 1. Verify button remains disabled
                inp.value = bypass_attempt
                await pilot.pause()
                self.assertTrue(
                    btn.disabled,
                    f"Confirm button must be disabled for bypass attempt: {bypass_attempt!r}",
                )

                # 2. Verify submitting the input does NOT dismiss True
                modal.on_input_submitted(Input.Submitted(inp, bypass_attempt))
                await pilot.pause()
                self.assertIsNone(
                    dismissed_value,
                    f"Submitting {bypass_attempt!r} must NOT trigger deletion!",
                )

                # 3. Verify programmatic button press does NOT dismiss True
                modal.on_confirm_pressed()
                await pilot.pause()
                self.assertIsNone(
                    dismissed_value,
                    f"on_confirm_pressed() with {bypass_attempt!r} must NOT trigger deletion!",
                )

                # Dismiss safely with escape
                modal.dismiss(False)
                await pilot.pause()
                self.assertFalse(dismissed_value)

            # Finally, verify that ONLY exact case-sensitive "DELETE" succeeds
            authorized_dismiss = None

            def on_auth_dismiss(val: bool) -> None:
                nonlocal authorized_dismiss
                authorized_dismiss = val

            modal = DeleteConfirmModal("pass-otp", "test_entry_label")
            app.push_screen(modal, on_auth_dismiss)
            await pilot.pause()

            inp = modal.query_one("#delete-confirm-input", Input)
            btn = modal.query_one("#btn-confirm-delete", Button)

            inp.value = "DELETE"
            await pilot.pause()
            self.assertFalse(
                btn.disabled,
                "Confirm button must be enabled when input exactly equals 'DELETE'",
            )

            # Submitting exact DELETE dismisses with True
            modal.on_input_submitted(Input.Submitted(inp, "DELETE"))
            await pilot.pause()
            self.assertTrue(
                authorized_dismiss,
                "Submitting exact 'DELETE' must authorize deletion with True",
            )

    async def test_onepassword_backend_strict_deletion_refusal(self) -> None:
        """Verify strict multi-layer refusal of deletion under onepassword backend."""
        op_records = [
            ("2w4j6k8m0n2p4r6t8v0x2z4a6a", "GitHub Personal [2z4a6a]"),
            ("2w4j6k8m0n2p4r6t8v0x2z4a6b", "AWS Infrastructure [2z4a6b]"),
        ]
        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            profiles={"onepassword": self.valid_op_profile},
        )
        app.load_records = MagicMock(return_value=op_records)
        delete_spy = MagicMock()
        app.delete_record = delete_spy

        async with app.run_test() as pilot:
            # Mount TokenBrowserScreen with onepassword backend
            await pilot.press("1")
            await pilot.pause()

            browser = app.screen
            self.assertIsInstance(browser, TokenBrowserScreen)
            self.assertEqual(browser.backend, "onepassword")

            # Layer 1: Pressing 'd' in the UI must NOT open DeleteConfirmModal
            await pilot.press("d")
            await pilot.pause()
            self.assertIsInstance(
                app.screen,
                TokenBrowserScreen,
                "Pressing 'd' under onepassword must NOT open DeleteConfirmModal",
            )
            delete_spy.assert_not_called()

            # Layer 2: Directly calling action_request_delete() must strictly return early
            browser.action_request_delete()
            await pilot.pause()
            self.assertIsInstance(
                app.screen,
                TokenBrowserScreen,
                "Direct action_request_delete() call under onepassword must not push modal",
            )
            delete_spy.assert_not_called()

            # Layer 3: Calling app.delete_record() with onepassword must strictly return False
            real_delete_record = AuthyApp.delete_record
            res = real_delete_record(app, "onepassword", self.valid_op_profile, op_records[0][0])
            self.assertFalse(
                res,
                "app.delete_record('onepassword', ...) must strictly return False",
            )

            # Layer 4: Calling remove() from tui_items with onepassword must raise AppError(2)
            with self.assertRaises(AppError) as ctx:
                remove("onepassword", self.valid_op_profile, op_records[0][0], {})
            self.assertEqual(
                ctx.exception.exit_code,
                2,
                "remove('onepassword', ...) must raise AppError(2)",
            )

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")


if __name__ == "__main__":
    unittest.main()
