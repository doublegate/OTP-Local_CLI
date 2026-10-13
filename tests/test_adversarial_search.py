"""Adversarial stress tests for SearchIndex and fuzzy_filter.

Authored by Challenger 2 (Milestone M1: Search Robustness and ReDoS Verifier).
Validates:
1. ReDoS immunity and catastrophic query resilience.
2. Scale benchmark across 10,000 items under 10ms SLA.
3. Extreme input handling (Unicode, Emojis, ANSI escapes, Null bytes, 1MB payloads).
4. Ranking fidelity verification and empirical inversion boundary analysis.
"""

import sys
import time
import unittest

from authy_local.tui_items import SearchIndex, _subsequence_score, fuzzy_filter
from benchmarks.benchmark_search import generate_catalog


class AdversarialSearchTests(unittest.TestCase):
    def test_redos_catastrophic_patterns(self):
        """Verify immunity against catastrophic backtracking regex patterns."""
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
            "[a-zA-Z]+@[a-zA-Z]+(\\.[a-zA-Z]+)+",
            "(0|1)+0",
            "([a-z0-9_-]+@[a-z0-9_-]+)+",
            "\\b(a+)+\\b",
        ]
        targets = [
            ("k1", "a" * 2000),
            ("k2", "a" * 1000 + "c"),
            ("k3", "x" * 500 + "y"),
            ("k4", "0" * 1000 + "1"),
            ("k5", "user@domain.com"),
            ("k6", "((a+)*)+"),
            ("k7", ".*.*.*.*.*.*.*.*.*.*b"),
            ("k8", "Normal GitHub Token"),
        ]
        index = SearchIndex(targets)

        for pat in redos_patterns:
            t0 = time.perf_counter()
            res_idx = index.filter(pat)
            t1 = time.perf_counter()
            res_fuz = fuzzy_filter(targets, pat)
            t2 = time.perf_counter()

            elapsed_idx = (t1 - t0) * 1000
            elapsed_fuz = (t2 - t1) * 1000

            self.assertIsInstance(res_idx, list)
            self.assertIsInstance(res_fuz, list)
            # ReDoS patterns must complete in sub-millisecond time (< 1ms)
            self.assertLess(
                elapsed_idx, 1.0, f"Pattern {pat!r} took {elapsed_idx:.3f}ms in SearchIndex"
            )
            self.assertLess(
                elapsed_fuz, 1.0, f"Pattern {pat!r} took {elapsed_fuz:.3f}ms in fuzzy_filter"
            )

    def test_massive_string_matching_latency(self):
        """Verify linear scan scaling on massive repetitive strings."""
        targets = [
            ("k1", "a" * 10000 + "b"),
            ("k2", ("ab" * 5000)),
            ("k3", "x" * 10000),
        ]
        index = SearchIndex(targets)

        queries = [
            ("a" * 10000 + "c"),  # long mismatch
            ("a" * 10000 + "b"),  # exact match on 10k chars
            ("a" * 5000 + "b"),  # long subsequence
            (("ab" * 2500) + "b"),  # alternating subsequence
            ("a" * 100000),  # huge query
        ]

        for q in queries:
            t0 = time.perf_counter()
            res = index.filter(q)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            self.assertIsInstance(res, list)
            # Massive string queries must complete within 10ms
            self.assertLess(elapsed_ms, 10.0, f"Query len={len(q)} took {elapsed_ms:.3f}ms")

    def test_extreme_inputs(self):
        """Verify robust handling of Unicode, Emojis, ANSI escapes, Null bytes, and 1MB inputs."""
        extreme_rows = [
            ("k1", "GitHub (Personal)"),
            ("k2", "Café du Monde:user@example.com"),
            ("k3", "München Über-Admin:root"),
            ("k4", "Straße Auth Token"),
            ("k5", "谷歌账号:张伟"),
            ("k6", "アマゾン ウェブ サービス (AWS)"),
            ("k7", "네이버 계정:admin"),
            ("k8", "Яндекс Почта:ivan"),
            ("k9", "حساب المستخدم:admin"),
            ("k10", "חשבון אישי:user"),
            ("k11", "Emoji 👨‍👩‍👧‍👦 Family Token"),
            ("k12", "Flag 🏴‍☠️ Pirate:pass"),
            ("k13", "Thumbs 👍🏽 Medium Skin"),
            ("k14", "\x1b[31;1mRed Alert Server\x1b[0m:admin"),
            ("k15", "Null\x00Byte\x00Key:secret"),
            ("k16", "New\nLine\r\nReturn\tTab"),
            ("k17", "   Spaced    Out   "),
            ("k18", ""),
            ("k19", "A" * 5000),
        ]
        index = SearchIndex(extreme_rows)

        # 1. Unicode diacritics and international scripts
        self.assertEqual([r[0] for r in index.filter("café")], ["k2"])
        self.assertEqual([r[0] for r in index.filter("über")], ["k3"])
        self.assertEqual([r[0] for r in index.filter("strasse")], ["k4"])  # German Eszett
        self.assertEqual([r[0] for r in index.filter("谷歌")], ["k5"])
        self.assertEqual([r[0] for r in index.filter("アマゾン")], ["k6"])
        self.assertEqual([r[0] for r in index.filter("네이버")], ["k7"])
        self.assertEqual([r[0] for r in index.filter("яндекс")], ["k8"])
        self.assertEqual([r[0] for r in index.filter("حساب")], ["k9"])
        self.assertEqual([r[0] for r in index.filter("חשבון")], ["k10"])

        # 2. Complex Emojis
        self.assertEqual([r[0] for r in index.filter("👨‍👩‍👧‍👦")], ["k11"])
        self.assertEqual([r[0] for r in index.filter("🏴‍☠️")], ["k12"])
        self.assertEqual([r[0] for r in index.filter("👍🏽")], ["k13"])

        # 3. ANSI escapes and control chars
        self.assertEqual([r[0] for r in index.filter("\x1b[31;1m")], ["k14"])
        self.assertEqual([r[0] for r in index.filter("\x00")], ["k15"])
        self.assertEqual([r[0] for r in index.filter("Null\x00Byte")], ["k15"])

        # 4. Whitespace and empty queries
        all_keys = [r[0] for r in extreme_rows]
        self.assertEqual([r[0] for r in index.filter("")], all_keys)
        self.assertEqual([r[0] for r in index.filter("   ")], all_keys)
        self.assertEqual([r[0] for r in index.filter("\t\n\r")], all_keys)

        # 5. Multi-kilobyte and 1MB payloads
        t0 = time.perf_counter()
        res_1mb = index.filter("x" * 1_000_000)
        t_1mb = (time.perf_counter() - t0) * 1000
        self.assertEqual(res_1mb, [])
        self.assertLess(t_1mb, 50.0, f"1MB payload query took {t_1mb:.3f}ms")

    def test_scale_benchmark_10k_realistic(self):
        """Verify SearchIndex against 10,000 realistic items satisfies < 10ms SLA."""
        rows_10k = generate_catalog(10000)
        index_10k = SearchIndex(rows_10k)

        queries = [
            "git",
            "aws",
            "security",
            "infra",
            "gh",
            "admin@company.com",
            "tailscale",
            "nonexistent_token_xyz",
            "a",
            "0001",
        ]

        is_tracing = sys.gettrace() is not None or "coverage" in sys.modules
        query_sla = 30.0 if is_tracing else 25.0
        overall_sla = 15.0 if is_tracing else 8.0

        timings = []
        for q in queries:
            times = []
            for _ in range(5):
                t0 = time.perf_counter()
                _ = index_10k.filter(q)
                times.append((time.perf_counter() - t0) * 1000)
            avg_time = sum(times) / len(times)
            timings.append(avg_time)
            self.assertLess(
                avg_time,
                query_sla,
                f"Query {q!r} averaged {avg_time:.3f}ms on 10k items, exceeding {query_sla}ms SLA",
            )

        overall_avg = sum(timings) / len(timings)
        self.assertLess(
            overall_avg,
            overall_sla,
            f"Overall average {overall_avg:.3f}ms exceeded {overall_sla}ms SLA",
        )

    def test_ranking_fidelity_short_queries(self):
        """Verify exact > prefix > boundary substring > mid substring > subsequence for short queries."""
        rows = [
            ("exact", "github"),
            ("prefix", "github-work"),
            ("boundary_sub", "my-github-token"),
            ("mid_sub", "mygithubtoken"),
            ("subseq", "g-i-t-h-u-b"),
        ]
        results = fuzzy_filter(rows, "github")
        ranked_keys = [r[0] for r in results]
        expected = ["exact", "prefix", "boundary_sub", "mid_sub", "subseq"]
        self.assertEqual(ranked_keys, expected)

    def test_ranking_fidelity_subsequence_inversion_defect(self):
        """Empirically demonstrate ranking tier inversion caused by unbounded consecutive_bonus.

        Defect demonstration:
        1. Query length 60: Subsequence match ranks above non-boundary substring match.
        2. Query length 80: Subsequence match ranks above prefix match.
        3. Query length 115: Subsequence match ranks above EXACT match.
        """
        # Case 1: Subsequence defeats Substring at query length 60
        q60 = "a" * 60
        rows_sub = [
            ("substr", f"zzz{q60}zzz"),
            ("subseq", f"{q60[:30]}X{q60[30:]}"),
        ]
        res_sub = [r[0] for r in fuzzy_filter(rows_sub, q60)]
        # When defect is present, 'subseq' inverts above 'substr'
        subseq_inverts_substr = res_sub[0] == "subseq"

        # Case 2: Subsequence defeats Prefix at query length 80
        q80 = "a" * 80
        rows_pre = [
            ("prefix", f"{q80}rest"),
            ("subseq", f"x{q80[:40]}y{q80[40:]}"),
        ]
        res_pre = [r[0] for r in fuzzy_filter(rows_pre, q80)]
        subseq_inverts_prefix = res_pre[0] == "subseq"

        # Case 3: Subsequence defeats Exact match at query length 115
        q115 = "a" * 57 + "b" * 58
        rows_exact = [
            ("exact", q115),
            ("subseq", f"{q115[:57]}X{q115[57:]}"),
        ]
        res_exact = [r[0] for r in fuzzy_filter(rows_exact, q115)]
        subseq_inverts_exact = res_exact[0] == "subseq"

        # Assert that the score inversion is empirically reproducible
        score_exact = 100_000
        score_subseq = _subsequence_score(
            q115, f"{q115[:57]}X{q115[57:]}", len(q115), len(q115) + 1
        )
        self.assertGreater(
            score_subseq,
            score_exact,
            f"Expected subseq score ({score_subseq}) to exceed exact score ({score_exact})",
        )
        self.assertTrue(subseq_inverts_substr, "Subsequence failed to invert substring")
        self.assertTrue(subseq_inverts_prefix, "Subsequence failed to invert prefix")
        self.assertTrue(subseq_inverts_exact, "Subsequence failed to invert exact match")


if __name__ == "__main__":
    unittest.main()
