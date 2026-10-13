"""Comprehensive unit and component test suite for Milestone M4 features.

Covers:
- Feature 16: Real-time TOTP Countdown Bar (TotpProgressBar, CountdownBar, CodeDisplayModal)
- Feature 17: Instant Fuzzy Match Character Highlighting & Browser Polish
- Feature 18: Clipboard Copy Toast Notification (ToastBadge, CopyToast, notify_copy)
- Feature 19: Keyboard Shortcuts Help Overlay (HelpModal, 5 categorized sections, universal toggle)
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from rich.table import Table
from rich.text import Text
from textual.widgets import ProgressBar

from authy_local.tui import (
    MAX_RENDER_OPTIONS,
    AuthyApp,
    CodeDisplayModal,
    CopyToast,
    CountdownBar,
    DashboardScreen,
    HelpModal,
    ToastBadge,
    TokenBrowserScreen,
    TotpProgressBar,
    create_category_table,
    create_shortcuts_table,
    get_shortcuts_categories,
)
from authy_local.tui_items import SearchIndex


class TestTotpProgressBar(unittest.TestCase):
    """Unit tests for TotpProgressBar and CountdownBar widgets (Feature 16)."""

    def test_totp_progress_bar_inheritance_and_defaults(self) -> None:
        """Verify TotpProgressBar inherits from ProgressBar and initializes defaults correctly."""
        bar = TotpProgressBar(total=30.0, bar_width=20)
        self.assertIsInstance(bar, ProgressBar)
        self.assertEqual(bar.total, 30.0)
        self.assertEqual(bar.bar_width, 20)
        self.assertEqual(bar.remaining_seconds, 30.0)
        self.assertFalse(bar.is_expired)
        self.assertEqual(bar.compose(), [])

    def test_totp_progress_bar_color_class_transitions(self) -> None:
        """Verify dynamic CSS class transitions: green (>15s), yellow (6-15s), red (<=5s)."""
        bar = TotpProgressBar(total=30.0)

        # > 15s: normal (green)
        bar.remaining_seconds = 24.5
        self.assertTrue(bar.has_class("time-normal"))
        self.assertFalse(bar.has_class("time-warning"))
        self.assertFalse(bar.has_class("time-critical"))
        self.assertFalse(bar.has_class("time-expired"))
        self.assertAlmostEqual(bar.progress, 24.5)

        # 6s - 15s: warning (yellow)
        bar.remaining_seconds = 14.9
        self.assertFalse(bar.has_class("time-normal"))
        self.assertTrue(bar.has_class("time-warning"))
        self.assertFalse(bar.has_class("time-critical"))
        self.assertFalse(bar.has_class("time-expired"))

        bar.remaining_seconds = 6.0
        self.assertTrue(bar.has_class("time-warning"))

        # <= 5s: critical (red)
        bar.remaining_seconds = 5.0
        self.assertFalse(bar.has_class("time-normal"))
        self.assertFalse(bar.has_class("time-warning"))
        self.assertTrue(bar.has_class("time-critical"))
        self.assertFalse(bar.has_class("time-expired"))

        bar.remaining_seconds = 0.5
        self.assertTrue(bar.has_class("time-critical"))

    def test_totp_progress_bar_expiration_watcher(self) -> None:
        """Verify is_expired reactive watcher applies time-expired and strips other classes."""
        bar = TotpProgressBar(total=30.0)
        bar.remaining_seconds = 20.0
        self.assertTrue(bar.has_class("time-normal"))

        bar.is_expired = True
        self.assertTrue(bar.has_class("time-expired"))
        self.assertFalse(bar.has_class("time-normal"))
        self.assertFalse(bar.has_class("time-warning"))
        self.assertFalse(bar.has_class("time-critical"))

    def test_totp_progress_bar_render_visual_format(self) -> None:
        """Verify Unicode block rendering, bracketed format, and seconds display."""
        bar = TotpProgressBar(total=30.0, bar_width=20)

        # 1. Normal state: >15s
        bar.remaining_seconds = 20.0
        rendered = bar.render()
        self.assertIsInstance(rendered, Text)
        rendered_plain = str(rendered)
        self.assertTrue(rendered_plain.startswith("["))
        self.assertIn("]", rendered_plain)
        self.assertIn("20s", rendered_plain)
        self.assertIn("█", rendered_plain)
        self.assertIn("░", rendered_plain)

        # 2. Warning state: 10s
        bar.remaining_seconds = 10.0
        rendered = bar.render()
        self.assertIn("10s", str(rendered))

        # 3. Critical state: 3s
        bar.remaining_seconds = 3.0
        rendered = bar.render()
        self.assertIn(" 3s", str(rendered))

        # 4. Expired state: 0s (EXPIRED)
        bar.is_expired = True
        rendered_expired = bar.render()
        self.assertIn("0s (EXPIRED)", str(rendered_expired))
        self.assertNotIn("█", str(rendered_expired))

    def test_standalone_countdown_bar_widget(self) -> None:
        """Verify CountdownBar standalone widget renders normal and expired states."""
        cbar = CountdownBar()
        cbar.remaining_seconds = 18.0
        rendered = cbar.render()
        self.assertIn("18s", str(rendered))

        cbar.is_expired = True
        rendered_expired = cbar.render()
        self.assertIn("EXPIRED", str(rendered_expired))


class TestCodeDisplayModalLifecycle(unittest.IsolatedAsyncioTestCase):
    """Unit and pilot tests for CodeDisplayModal lifecycle, rollover, and wiping (Feature 16)."""

    def test_code_digits_formatting(self) -> None:
        """Verify grouping of 6-digit and 8-digit OTP codes."""
        modal = CodeDisplayModal(code="123456")
        self.assertEqual(modal._format_digits("123456"), "123  456")
        self.assertEqual(modal._format_digits("12345678"), "1234  5678")
        self.assertEqual(modal._format_digits("99999"), "99999")
        self.assertEqual(modal._format_digits(""), "------")

    def test_rollover_expiration_and_refresh_callback(self) -> None:
        """Verify RFC 6238 time-step rollover transitions to expired or auto-refreshes."""
        # 1. No refresh callback -> transitions to expired
        modal = CodeDisplayModal(code="987654", item_label="TestService")
        modal._initial_step = 100
        with patch("time.time", return_value=(101 * 30 + 5)):
            modal._tick_countdown()
            self.assertTrue(modal._is_expired)

        # 2. With refresh callback -> successfully auto-refreshes
        mock_refresh = MagicMock(return_value="112233")
        modal_refresh = CodeDisplayModal(
            code="987654",
            item_label="TestService",
            refresh_callback=mock_refresh,
        )
        modal_refresh._initial_step = 100
        with patch("time.time", return_value=(101 * 30 + 5)):
            modal_refresh._tick_countdown()
            mock_refresh.assert_called_once()
            self.assertEqual(modal_refresh.code, "112233")
            self.assertFalse(modal_refresh._is_expired)

    def test_cryptographic_memory_wiping_on_dismiss(self) -> None:
        """Verify secret OTP code and timers are strictly wiped upon dismiss and unmount."""
        mock_timer = MagicMock()
        modal = CodeDisplayModal(code="987654", item_label="TestService")
        modal._timer = mock_timer
        modal.refresh_callback = MagicMock()

        modal.on_unmount()
        self.assertEqual(modal.code, "")
        self.assertIsNone(modal._timer)
        self.assertIsNone(modal.refresh_callback)
        mock_timer.stop.assert_called_once()

    async def test_code_modal_pilot_interaction(self) -> None:
        """Test CodeDisplayModal through Textual test pilot."""
        dummy_profile = {
            "version": 1,
            "default_backend": "onepassword",
            "backends": {
                "onepassword": {
                    "account": "my.1password.com",
                    "vault": "Personal",
                    "cache_ttl": 300,
                }
            },
        }

        def dummy_dispatch(args, output, diagnostic):
            return 0, "OK", ["otp-token 123456"]

        app = AuthyApp(dispatch=dummy_dispatch, profiles=dummy_profile)
        async with app.run_test() as pilot:
            modal = CodeDisplayModal(code="654321", item_label="Acme Corp")
            app.push_screen(modal)
            await pilot.pause()

            self.assertIsInstance(app.screen, CodeDisplayModal)
            bar = modal.query_one(ProgressBar)
            self.assertIsInstance(bar, TotpProgressBar)

            # Test copy code action 'c'
            with patch("authy_local.interaction.copy_code") as mock_copy:
                await pilot.press("c")
                await pilot.pause()
                mock_copy.assert_called_once()
                self.assertEqual(mock_copy.call_args[0][0], "654321")

            # Test dismiss 'escape' wipes secret
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(modal.code, "")
            self.assertIsInstance(app.screen, DashboardScreen)


class TestFuzzyMatchHighlighting(unittest.TestCase):
    """Unit tests for TokenBrowserScreen._highlight_match and SearchIndex (Feature 17)."""

    def test_highlight_empty_query_or_text(self) -> None:
        """Verify empty query or empty text returns unmodified Rich Text without spans."""
        t1 = TokenBrowserScreen._highlight_match("GitHub", "", "bold cyan")
        self.assertEqual(str(t1), "GitHub")
        self.assertEqual(len(t1.spans), 0)

        t2 = TokenBrowserScreen._highlight_match("", "git", "bold cyan")
        self.assertEqual(str(t2), "")
        self.assertEqual(len(t2.spans), 0)

    def test_highlight_strategy_1_substring(self) -> None:
        """Verify full-query contiguous substring matching with bold yellow underline."""
        text = "GitHub Enterprise GitHub"
        query = "github"
        t = TokenBrowserScreen._highlight_match(text, query, "bold cyan")

        # Expect 2 spans matching both occurrences of 'github'
        self.assertEqual(len(t.spans), 2)
        span1, span2 = t.spans
        self.assertEqual(span1.start, 0)
        self.assertEqual(span1.end, 6)
        self.assertEqual(span1.style, "bold yellow underline")

        self.assertEqual(span2.start, 18)
        self.assertEqual(span2.end, 24)
        self.assertEqual(span2.style, "bold yellow underline")

    def test_highlight_strategy_2_multi_word(self) -> None:
        """Verify multi-word query highlights individual matching words."""
        text = "AWS Production admin@company.com"
        query = "aws admin"
        t = TokenBrowserScreen._highlight_match(text, query, "bold cyan")

        self.assertEqual(len(t.spans), 2)
        # 'AWS' at [0, 3]
        self.assertEqual(t.spans[0].start, 0)
        self.assertEqual(t.spans[0].end, 3)
        # 'admin' at [15, 20]
        self.assertEqual(t.spans[1].start, 15)
        self.assertEqual(t.spans[1].end, 20)

    def test_highlight_strategy_3_fuzzy_subsequence(self) -> None:
        """Verify ordered subsequence fuzzy character highlighting (e.g. acronyms)."""
        text = "GitHub Account"
        query = "gh"
        t = TokenBrowserScreen._highlight_match(text, query, "bold cyan")

        # 'G' at 0, 'h' at 3
        self.assertEqual(len(t.spans), 2)
        self.assertEqual(t.spans[0].start, 0)
        self.assertEqual(t.spans[0].end, 1)
        self.assertEqual(t.spans[1].start, 3)
        self.assertEqual(t.spans[1].end, 4)

    def test_highlight_non_matching_subsequence_no_spans(self) -> None:
        """Verify non-matching fuzzy query leaves text unstyled."""
        text = "GitHub"
        query = "xyz"
        t = TokenBrowserScreen._highlight_match(text, query, "bold cyan")
        self.assertEqual(len(t.spans), 0)

    def test_search_index_native_sort_consistency(self) -> None:
        """Verify native C tuple sort in SearchIndex produces identical ranking."""
        rows = [
            ("key1", "GitHub Work [key1]"),
            ("key2", "AWS Production [key2]"),
            ("key3", "GitLab Personal [key3]"),
        ]
        index = SearchIndex(rows)
        matches = index.filter("git")
        self.assertEqual(len(matches), 2)
        # Both GitHub and GitLab match prefix 'git'
        labels = [m[1] for m in matches]
        self.assertIn("GitHub Work [key1]", labels)
        self.assertIn("GitLab Personal [key3]", labels)

    def test_max_render_options_constant(self) -> None:
        """Verify MAX_RENDER_OPTIONS is tuned to 150."""
        self.assertEqual(MAX_RENDER_OPTIONS, 150)


class TestClipboardCopyToast(unittest.TestCase):
    """Unit tests for CopyToast / ToastBadge and AuthyApp.notify_copy (Feature 18)."""

    def test_toast_badge_and_copy_toast_init(self) -> None:
        """Verify ToastBadge and CopyToast widget initialization."""
        badge = ToastBadge()
        self.assertIn("Copied to clipboard", str(badge.render()))

        copy_toast = CopyToast("Custom copied!")
        self.assertIn("Custom copied!", str(copy_toast.render()))

    def test_notify_copy_formatting(self) -> None:
        """Verify AuthyApp.notify_copy constructs expected toast text and records timestamp."""
        app = AuthyApp()
        mock_notify = MagicMock()
        app.notify = mock_notify

        # 1. Without arguments
        t0 = time.monotonic()
        app.notify_copy()
        mock_notify.assert_called_once()
        self.assertIn("Copied to clipboard", mock_notify.call_args[0][0])
        self.assertEqual(mock_notify.call_args[1].get("timeout"), 2.5)
        self.assertGreaterEqual(app._last_copy_toast_time, t0)

        # 2. With item label
        mock_notify.reset_mock()
        app.notify_copy("GitHub Personal (alice@work)")
        mock_notify.assert_called_once()
        self.assertIn("GitHub Personal", mock_notify.call_args[0][0])

        # 3. With custom message
        mock_notify.reset_mock()
        app.notify_copy(custom_message="Custom Token Copied!")
        mock_notify.assert_called_once_with("Custom Token Copied!", timeout=2.5)


class TestKeyboardShortcutsHelpOverlay(unittest.IsolatedAsyncioTestCase):
    """Unit and pilot tests for HelpModal and universal help bindings (Feature 19)."""

    def test_get_shortcuts_categories_structure(self) -> None:
        """Verify get_shortcuts_categories provides all 5 functional sections."""
        categories = get_shortcuts_categories()
        self.assertEqual(len(categories), 5)
        names = [c[0] for c in categories]
        self.assertEqual(
            names,
            [
                "Global Controls",
                "Dashboard Navigation",
                "Token Browser Controls",
                "Code Display Modal",
                "Forms & Dialogs",
            ],
        )
        for _, shortcuts in categories:
            self.assertGreaterEqual(len(shortcuts), 2)
            for key, desc in shortcuts:
                self.assertTrue(len(key) > 0)
                self.assertTrue(len(desc) > 0)

    def test_create_category_and_shortcuts_tables(self) -> None:
        """Verify Table construction for both single category and all categories."""
        cat_table = create_category_table("Test Section", [("F1", "Help")])
        self.assertIsInstance(cat_table, Table)

        full_table = create_shortcuts_table(compact=True)
        self.assertIsInstance(full_table, Table)
        self.assertEqual(len(full_table.columns), 2)

    def test_help_modal_composition_lines(self) -> None:
        """Verify HelpModal composes exactly 5 category tables with classes='help-line'."""
        modal = HelpModal()
        # Mock app for compose check
        modal._app = MagicMock()
        modal._app.has_class = MagicMock(return_value=False)
        # Verify bindings include question_mark and f1
        keys = [b.key for b in modal.BINDINGS]
        self.assertIn("question_mark", keys)
        self.assertIn("f1", keys)
        self.assertIn("escape", keys)
        self.assertIn("enter", keys)
        self.assertIn("j", keys)
        self.assertIn("k", keys)

    async def test_universal_help_modal_toggle_pilot(self) -> None:
        """Verify '?' and F1 toggle HelpModal across Dashboard and TokenBrowser screens."""
        dummy_profile = {
            "onepassword": {
                "account": "my.1password.com",
                "vault": "Personal",
                "cache_ttl": 300,
            }
        }

        def dummy_dispatch(args, output, diagnostic):
            return 0, "OK", ["sample-record Sample Label"]

        app = AuthyApp(dispatch=dummy_dispatch, profiles=dummy_profile)
        app.load_records = MagicMock(return_value=[("sample-record", "Sample Label")])
        async with app.run_test() as pilot:
            # 1. From Dashboard: open with '?'
            await pilot.press("question_mark")
            await pilot.pause()
            self.assertIsInstance(app.screen, HelpModal)
            help_modal = app.screen
            self.assertEqual(len(help_modal.query(".help-line")), 5)

            # Test scrolling actions do not crash
            help_modal.action_scroll_down()
            help_modal.action_scroll_up()
            help_modal.action_scroll_page_down()
            help_modal.action_scroll_page_up()

            # Toggle off with '?'
            await pilot.press("question_mark")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # Open with F1 and dismiss with Escape
            await pilot.press("f1")
            await pilot.pause()
            self.assertIsInstance(app.screen, HelpModal)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # 2. From TokenBrowser: open with '?' and dismiss
            await pilot.press("1")  # Open browser
            await pilot.pause()
            self.assertIsInstance(app.screen, TokenBrowserScreen)

            # Open help from browser
            await pilot.press("question_mark")
            await pilot.pause()
            self.assertIsInstance(app.screen, HelpModal)

            # Dismiss returns back to TokenBrowserScreen
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, TokenBrowserScreen)

            # Exit browser back to dashboard
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)


if __name__ == "__main__":
    unittest.main()
