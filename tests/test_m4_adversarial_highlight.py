"""Adversarial stress and verification tests for Highlighting & Virtualization (Milestone M4).

Authored by Challenger 2 (Milestone M4: Highlighting & Virtualization Challenger 2).
Adversarially validates:
1. Highlight accuracy & ReDoS immunity: complex queries (unbalanced brackets,
   regex chars, Unicode, emojis, 5,000-character strings, null bytes) never crash,
   raise exceptions, or hang.
2. Highlight fidelity: matching spans strictly correspond to actual character indices,
   preserve underlying plain text, and do not corrupt column alignment.
3. Latency benchmark on 5,000 items: option row rendering latency strictly < 5ms
   with MAX_RENDER_OPTIONS = 150.
"""

import sys
import time
import unittest
from unittest.mock import MagicMock

from rich.text import Text
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from authy_local.tui import (
    MAX_RENDER_OPTIONS,
    AuthyApp,
    TokenBrowserScreen,
    parse_token_parts,
)
from benchmarks.benchmark_search import generate_catalog


class TestHighlightAccuracyAndReDoS(unittest.TestCase):
    """Stress tests verifying that _highlight_match never crashes, raises, or hangs."""

    @classmethod
    def setUpClass(cls) -> None:
        # Warm up highlight matcher and JIT/tracer instrumentation before timed tests
        TokenBrowserScreen._highlight_match("warmup", "warm", "bold cyan")

    def test_unbalanced_brackets_and_special_symbols(self) -> None:
        """Verify queries with unbalanced brackets and symbols execute safely without regex errors."""
        adversarial_bracket_queries = [
            "[",
            "]",
            "[[[",
            "]]]",
            "([",
            "])}",
            "((((((",
            "))))))",
            "}{[()}",
            "][][][",
            r"\[",
            r"\]",
            r"\\",
            "<?xml?>",
            "/* comment */",
            "-->",
            "<script>",
            "{{{token}}}",
            "((a+)*)+",
            "[[[00100]]]",
        ]
        target_texts = [
            "GitHub Enterprise [2z4a6a]",
            "AWS Infrastructure (prod)",
            "Google Cloud {vault-root}",
            "[[[00100]]] PagerDuty",
            "Special: <xml> (test)",
            "",
            "   ",
        ]

        is_tracing = (
            sys.gettrace() is not None
            or "coverage" in sys.modules
            or (
                hasattr(sys, "monitoring")
                and sys.monitoring.get_tool(getattr(sys.monitoring, "COVERAGE_ID", 1)) is not None
            )
        )
        limit_ms = 25.0 if is_tracing else 5.0

        for query in adversarial_bracket_queries:
            for text in target_texts:
                t0 = time.perf_counter()
                res = TokenBrowserScreen._highlight_match(text, query, "bold cyan")
                elapsed_ms = (time.perf_counter() - t0) * 1000

                self.assertIsInstance(res, Text)
                self.assertEqual(res.plain, text)
                self.assertLess(
                    elapsed_ms,
                    limit_ms,
                    f"Query {query!r} on text {text!r} took {elapsed_ms:.3f}ms",
                )

    def test_regex_special_characters_and_redos_patterns(self) -> None:
        """Verify queries containing regex quantifiers and ReDoS bombs do not hang."""
        redos_patterns = [
            "(a+)+$",
            "(a|aa)+$",
            "(a*)*b",
            ".*.*.*.*.*.*.*.*.*.*b",
            "^(([a-z])+.)+[A-Z]([a-z])+$",
            "((a+)*)+",
            "(a|a?)+$",
            "a?" * 30 + "a" * 30,
            "(.*a){25}",
            "(x+x+)+y",
            r"[a-zA-Z]+@[a-zA-Z]+(\.[a-zA-Z]+)+",
            "(0|1)+0",
            r"([a-z0-9_-]+@[a-z0-9_-]+)+",
            r"\b(a+)+\b",
            r"\d+\s*\w+",
            r"^.*$",
            r"+++***",
            r"???$$$",
        ]
        targets = [
            "a" * 1000,
            "a" * 500 + "b",
            "user@domain.com",
            "Normal GitHub Token",
            "((a+)*)+",
            "0" * 500 + "1",
        ]

        is_tracing = (
            sys.gettrace() is not None
            or "coverage" in sys.modules
            or (
                hasattr(sys, "monitoring")
                and sys.monitoring.get_tool(getattr(sys.monitoring, "COVERAGE_ID", 1)) is not None
            )
        )
        limit_ms = 25.0 if is_tracing else 5.0

        for pattern in redos_patterns:
            for target in targets:
                t0 = time.perf_counter()
                res = TokenBrowserScreen._highlight_match(target, pattern, "bold cyan")
                elapsed_ms = (time.perf_counter() - t0) * 1000

                self.assertIsInstance(res, Text)
                self.assertEqual(res.plain, target)
                self.assertLess(
                    elapsed_ms,
                    limit_ms,
                    f"Pattern {pattern!r} on target len={len(target)} took {elapsed_ms:.3f}ms",
                )

    def test_massive_5000_character_strings(self) -> None:
        """Verify linear scaling and resilience when matching 5,000-character strings."""
        long_5k = "a" * 5000
        short_text = "GitHub Account (admin@company.com)"

        is_tracing = (
            sys.gettrace() is not None
            or "coverage" in sys.modules
            or (
                hasattr(sys, "monitoring")
                and sys.monitoring.get_tool(getattr(sys.monitoring, "COVERAGE_ID", 1)) is not None
            )
        )

        # 1. 5k query on short text (no match, fast exit)
        t0 = time.perf_counter()
        res1 = TokenBrowserScreen._highlight_match(short_text, long_5k, "bold cyan")
        t1 = (time.perf_counter() - t0) * 1000
        self.assertLess(t1, 100.0 if is_tracing else 5.0)
        self.assertEqual(len(res1.spans), 0)

        # 2. Short query on 5k text
        t0 = time.perf_counter()
        res2 = TokenBrowserScreen._highlight_match(long_5k, "a", "bold cyan")
        t2 = (time.perf_counter() - t0) * 1000
        limit_ms = 250.0 if is_tracing else 35.0
        self.assertLess(t2, limit_ms)
        self.assertEqual(res2.plain, long_5k)

        # 3. 5k query matching 5k text exactly
        t0 = time.perf_counter()
        res3 = TokenBrowserScreen._highlight_match(long_5k, long_5k, "bold cyan")
        t3 = (time.perf_counter() - t0) * 1000
        self.assertLess(t3, 100.0 if is_tracing else 5.0)
        self.assertEqual(len(res3.spans), 1)
        self.assertEqual(res3.spans[0].start, 0)
        self.assertEqual(res3.spans[0].end, 5000)

        # 4. 5k alternating mismatch
        t0 = time.perf_counter()
        res4 = TokenBrowserScreen._highlight_match("ab" * 2500, "c" * 5000, "bold cyan")
        t4 = (time.perf_counter() - t0) * 1000
        self.assertLess(t4, 100.0 if is_tracing else 5.0)
        self.assertEqual(len(res4.spans), 0)

    def test_extreme_boundary_inputs(self) -> None:
        """Verify empty strings, null bytes, newlines, and ANSI escapes are safely handled."""
        weird_inputs = [
            ("", ""),
            ("text", ""),
            ("", "query"),
            ("   \t\n   ", "   \t\n   "),
            ("Null \x00 byte \x00 token", "\x00"),
            ("Escaped \x1b[31mRed\x1b[0m Color", "red"),
            ("Newlines\nIn\nLabel\r\n", "in"),
            ("\t\tTabs\t\t", "tabs"),
        ]

        for text, query in weird_inputs:
            res = TokenBrowserScreen._highlight_match(text, query, "bold cyan")
            self.assertIsInstance(res, Text)
            # Rich Text normalizes \r\n line endings to \n
            self.assertEqual(res.plain, text.replace("\r\n", "\n"))


class TestHighlightFidelityAndAlignment(unittest.TestCase):
    """Fidelity tests verifying span character indices, styles, and column alignment."""

    def test_span_bounds_and_validity(self) -> None:
        """Verify all generated spans strictly satisfy 0 <= start < end <= len(text)."""
        samples = [
            ("GitHub Enterprise Server", "github"),
            ("AWS Production Billing", "aws billing"),
            ("Tailscale Personal VPN", "tpv"),
            ("Google Cloud Platform", "gcp"),
            ("1Password Family Vault", "1pfv"),
            ("DigitalOcean Droplets", "do"),
            ("Cloudflare Workers KV", "cf worker"),
        ]

        for text, query in samples:
            res = TokenBrowserScreen._highlight_match(text, query, "bold cyan")
            text_len = len(text)
            for s in res.spans:
                self.assertGreaterEqual(s.start, 0)
                self.assertLess(s.start, s.end)
                self.assertLessEqual(s.end, text_len)
                self.assertEqual(s.style, "bold yellow underline")

    def test_span_character_fidelity_strategy_1_substring(self) -> None:
        """Verify Strategy 1 spans extract the exact query string (case-insensitively)."""
        text = "GitHub Enterprise GitHub Cloud"
        query = "github"
        res = TokenBrowserScreen._highlight_match(text, query, "bold cyan")

        self.assertEqual(len(res.spans), 2)
        for s in res.spans:
            extracted = text[s.start : s.end]
            self.assertEqual(extracted.casefold(), query.casefold())

    def test_span_character_fidelity_strategy_2_multi_word(self) -> None:
        """Verify Strategy 2 spans extract individual space-separated words."""
        text = "AWS Production admin@company.com"
        query = "aws admin"
        res = TokenBrowserScreen._highlight_match(text, query, "bold cyan")

        self.assertEqual(len(res.spans), 2)
        words = query.casefold().split()
        for s in res.spans:
            extracted = text[s.start : s.end]
            self.assertIn(extracted.casefold(), words)

    def test_span_character_fidelity_strategy_3_subsequence(self) -> None:
        """Verify Strategy 3 single-character spans form the query characters in order."""
        text = "GitHub Personal Token"
        query = "gpt"
        res = TokenBrowserScreen._highlight_match(text, query, "bold cyan")

        self.assertEqual(len(res.spans), 3)
        chars = [text[s.start : s.end] for s in res.spans]
        reconstructed = "".join(chars).casefold()
        self.assertEqual(reconstructed, query.casefold())

    def test_column_alignment_79_chars_invariant(self) -> None:
        """Verify that highlighting never corrupts the 79-character row column alignment."""
        test_tokens = [
            ("totpm", "srv1:acc1", "Label 1"),
            (
                "onepassword",
                "2w4j6k8m0n2p4r6t8v0x2z4a6a",
                "GitHub Personal (user@gh.com) [2z4a6a]",
            ),
            ("pass-otp", "Personal/email", "email"),
            ("totpm", "Short:A", "Short A"),
            (
                "totpm",
                "VeryLongServiceNameExceedingThirtyTwoCharacters:VeryLongAccountNameExceedingThirtyCharacters",
                "Long",
            ),
            ("totpm", "🔑 EmojiService:🚀 EmojiAcc", "Emoji"),
            ("totpm", "微信支付:tencent_user", "CJK"),
            ("totpm", "Café:barista@cafe.fr", "Accents"),
        ]

        queries = [
            "",
            "git",
            "user",
            "emoji",
            "🔑",
            "32",
            "long",
            "srv",
            "acc",
            "a" * 50,
            "[",
            ".*",
            "a?",
            "gh",
        ]

        for backend, key, label in test_tokens:
            srv, acc, short_id = parse_token_parts(backend, key, label)
            for query in queries:
                row = Text()
                row.append(f"{1:<5}", style="dim")
                row.append_text(
                    TokenBrowserScreen._highlight_match(f"{srv:<32}"[:32], query, "bold cyan")
                )
                row.append(" ")
                row.append_text(
                    TokenBrowserScreen._highlight_match(f"{acc:<30}"[:30], query, "white")
                )
                row.append(" ")
                row.append(f"{short_id:<10}"[:10], style="dim")

                # Assert exact 79-character length
                self.assertEqual(
                    len(row.plain),
                    79,
                    f"Row length {len(row.plain)} != 79 for backend={backend}, query={query!r}",
                )
                # Assert fixed column boundary positions
                self.assertEqual(row.plain[0:5], f"{1:<5}")
                self.assertEqual(row.plain[37], " ", "Column separator 1 shifted")
                self.assertEqual(row.plain[68], " ", "Column separator 2 shifted")

    def test_unicode_and_emoji_fidelity(self) -> None:
        """Verify Unicode and emoji tokens produce exact matching spans without corruption."""
        samples = [
            ("🔑 1Password Vault", "🔑", 0, 1),
            ("🚀 Production Deploy", "🚀", 0, 1),
            ("🛡️ Multi-Factor Auth", "🛡️", 0, 2),
            ("微信支付 Tencent", "微信", 0, 2),
            ("Яндекс.Паспорт", "яндекс", 0, 6),
            ("الجزيرة للإعلام", "الجزيرة", 0, 7),
            ("Café du Monde", "café", 0, 4),
            ("München Über-Token", "münchen", 0, 7),
        ]

        for text, query, exp_start, exp_end in samples:
            res = TokenBrowserScreen._highlight_match(text, query, "bold cyan")
            self.assertEqual(res.plain, text)
            self.assertGreaterEqual(len(res.spans), 1)
            first_span = res.spans[0]
            self.assertEqual(first_span.start, exp_start)
            self.assertEqual(first_span.end, exp_end)
            self.assertEqual(text[first_span.start : first_span.end], text[exp_start:exp_end])


class TestVirtualizationAndLatencyBenchmark5000(unittest.IsolatedAsyncioTestCase):
    """Benchmark asserting row rendering latency < 5ms on 5,000 items with MAX_RENDER_OPTIONS = 150."""

    def test_max_render_options_constant_is_150(self) -> None:
        """Verify MAX_RENDER_OPTIONS is tuned to 150."""
        self.assertEqual(MAX_RENDER_OPTIONS, 150)

    def test_rendering_latency_5000_items_under_5ms(self) -> None:
        """Assert that rendering 150 virtualized rows with match highlighting takes < 5ms."""
        is_tracing = (
            sys.gettrace() is not None
            or "coverage" in sys.modules
            or (
                hasattr(sys, "monitoring")
                and sys.monitoring.get_tool(getattr(sys.monitoring, "COVERAGE_ID", 1)) is not None
            )
        )
        limit_avg_ms = 10.0 if is_tracing else 5.0
        limit_max_ms = 45.0 if is_tracing else 15.0

        catalog = generate_catalog(5000)
        options_to_render = catalog[:MAX_RENDER_OPTIONS]
        test_queries = ["git", "aws", "admin", "gh", "dev", "sec", "123", ""]

        for query in test_queries:
            # Measure row rendering loop across 30 iterations
            durations_ms: list[float] = []
            for _ in range(30):
                t0 = time.perf_counter()
                rendered_options: list[Option] = []
                for idx, (key, label) in enumerate(options_to_render):
                    srv, acc, short_id = parse_token_parts("totpm", key, label)
                    row = Text()
                    row.append(f"{idx + 1:<5}", style="dim")
                    row.append_text(
                        TokenBrowserScreen._highlight_match(f"{srv:<32}"[:32], query, "bold cyan")
                    )
                    row.append(" ")
                    row.append_text(
                        TokenBrowserScreen._highlight_match(f"{acc:<30}"[:30], query, "white")
                    )
                    row.append(" ")
                    row.append(f"{short_id:<10}"[:10], style="dim")
                    rendered_options.append(Option(prompt=row, id=f"opt-{idx}"))
                elapsed_ms = (time.perf_counter() - t0) * 1000
                durations_ms.append(elapsed_ms)

            avg_ms = sum(durations_ms) / len(durations_ms)
            min_ms = min(durations_ms)
            max_ms = max(durations_ms)

            self.assertEqual(len(rendered_options), MAX_RENDER_OPTIONS)
            self.assertGreater(min_ms, 0.0)
            # Empirical SLA: average rendering latency must stay strictly below limit_avg_ms
            self.assertLess(
                avg_ms,
                limit_avg_ms,
                f"Query {query!r} avg rendering latency exceeded {limit_avg_ms}ms: {avg_ms:.3f}ms",
            )
            # Maximum single-iteration latency should stay below limit_max_ms jitter allowance
            self.assertLess(
                max_ms,
                limit_max_ms,
                f"Query {query!r} max rendering latency exceeded {limit_max_ms}ms: {max_ms:.3f}ms",
            )

    async def test_live_browser_virtualization_cap(self) -> None:
        """Verify live Textual TokenBrowserScreen caps rendered options to MAX_RENDER_OPTIONS."""
        catalog = generate_catalog(5000)
        app = AuthyApp(
            dispatch=lambda *a: 0,
            profiles={"onepassword": {"account": "a", "vault": "v"}},
        )
        app.load_records = MagicMock(return_value=catalog)

        async with app.run_test() as pilot:
            await pilot.press("1")  # Browse and show
            await pilot.pause()

            browser = app.screen
            self.assertIsInstance(browser, TokenBrowserScreen)
            opt_list = browser.query_one("#token-option-list", OptionList)

            # 1. Broad query matching > 900 items
            browser._apply_search("git")
            await pilot.pause()
            self.assertEqual(opt_list.option_count, MAX_RENDER_OPTIONS)
            badge = str(browser.query_one("#match-count-badge", Static).render())
            self.assertIn("top 150", badge)

            # 2. Empty query over all 5,000 items
            browser._apply_search("")
            await pilot.pause()
            self.assertEqual(opt_list.option_count, MAX_RENDER_OPTIONS)
            badge = str(browser.query_one("#match-count-badge", Static).render())
            self.assertIn("top 150", badge)

            # 3. Selective query matching fewer than 150 items
            browser._apply_search("04242")
            await pilot.pause()
            self.assertLessEqual(opt_list.option_count, MAX_RENDER_OPTIONS)
            badge = str(browser.query_one("#match-count-badge", Static).render())
            self.assertIn("5000 items", badge)
