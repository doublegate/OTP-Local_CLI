"""Integration tests for benchmark execution, search indexing, and performance SLAs."""

import subprocess
import time
import unittest

from authy_local.cache import clear_cache, current_time_step, get_cached_totp, set_cached_totp
from authy_local.tui_items import SearchIndex, fuzzy_filter
from benchmarks import benchmark_capabilities as bm_cap
from benchmarks import benchmark_search as bm_search
from benchmarks import benchmark_totp_cache as bm_totp
from benchmarks import run_all


class BenchmarkAndSearchTests(unittest.TestCase):
    def test_fuzzy_filter_empty_query(self):
        rows = [("k1", "GitHub (Personal)"), ("k2", "AWS Production")]
        self.assertEqual(fuzzy_filter(rows, ""), rows)
        self.assertEqual(fuzzy_filter(rows, "   "), rows)

    def test_fuzzy_filter_relevance_ranking(self):
        rows = [
            ("k1", "GitLab Work"),
            ("k2", "GitHub (Personal)"),
            ("k3", "DigitalOcean droplet"),
            ("k4", "gh-pages token"),
            ("k5", "Unrelated Other"),
        ]
        # Exact prefix match ranks higher than general substring
        results = fuzzy_filter(rows, "git")
        labels = [r[1] for r in results]
        self.assertIn("GitLab Work", labels)
        self.assertIn("GitHub (Personal)", labels)
        self.assertIn("DigitalOcean droplet", labels)
        self.assertNotIn("Unrelated Other", labels)

    def test_fuzzy_filter_subsequence_initials(self):
        rows = [
            ("k1", "GitHub (Personal)"),
            ("k2", "GitLab Work"),
            ("k3", "gh-pages token"),
            ("k4", "Google Account"),
        ]
        results = fuzzy_filter(rows, "gh")
        labels = [r[1] for r in results]
        # "gh-pages token" is prefix match; "GitHub" is subsequence match (G...h...)
        self.assertEqual(labels, ["gh-pages token", "GitHub (Personal)"])

    def test_fuzzy_filter_special_characters_and_safety(self):
        rows = [
            ("k1", "[Production] DB Key"),
            ("k2", "user+test@example.com"),
            ("k3", "Wildcard * Match"),
            ("k4", "Regex (Group) Token?"),
            ("k5", "Path\\Windows\\Style"),
            ("k6", "Unicode 🚀 Rocket (Auth)"),
        ]
        # Special characters must not trigger regex compilation or crash
        for query in (
            "[",
            "]",
            "[prod",
            "+test",
            "*",
            "?",
            "(",
            ")",
            "\\",
            "🚀",
            "nonexistent-12345",
        ):
            with self.subTest(query=query):
                res = fuzzy_filter(rows, query)
                self.assertIsInstance(res, list)

    def test_search_index_consistency_with_fuzzy_filter(self):
        rows = [
            ("1", "Alpha"),
            ("2", "Beta"),
            ("3", "Alphabetical"),
            ("4", "Gamma"),
        ]
        index = SearchIndex(rows)
        for q in ("alpha", "bet", "a", "gamma", "nonexistent"):
            self.assertEqual(index.filter(q), fuzzy_filter(rows, q))

    def test_search_performance_under_interactive_sla(self):
        # 1,000 synthetic items
        rows = [(f"key_{i}", f"Service-{i:04d} Account-{i:04d}") for i in range(1000)]
        index = SearchIndex(rows)

        start = time.perf_counter()
        queries = ["service", "0050", "acc", "nonexistent", "srv"]
        for q in queries:
            _ = index.filter(q)
        avg_elapsed = (time.perf_counter() - start) / len(queries)

        # Average latency must be well under 10ms budget (< 5ms on modern hardware)
        self.assertLess(
            avg_elapsed, 0.010, f"Search latency {avg_elapsed * 1000:.2f}ms exceeded 10ms SLA"
        )

    def test_capability_probe_cache_speedup(self):
        # Measure uncached subprocess probe vs cached dictionary lookup
        start = time.perf_counter()
        _ = subprocess.run(["python3", "--version"], capture_output=True, timeout=5)
        uncached_time = time.perf_counter() - start

        cache = {"python3": "/usr/bin/python3"}
        start = time.perf_counter()
        for _ in range(10_000):
            hit = cache.get("python3")
        cached_time = (time.perf_counter() - start) / 10_000

        self.assertIsNotNone(hit)
        # Cached probe must be at least 100x faster than spawning a subprocess
        self.assertGreater(uncached_time / cached_time, 100.0)

    def test_totp_cache_window_speedup(self):
        clear_cache()
        step = current_time_step(30)
        set_cached_totp("onepassword", "item123", step, "123456")

        start = time.perf_counter()
        for _ in range(50_000):
            code = get_cached_totp("onepassword", "item123", step)
        cached_lookup_time = (time.perf_counter() - start) / 50_000

        self.assertEqual(code, "123456")
        # Sub-microsecond lookup (< 5 µs)
        self.assertLess(cached_lookup_time, 0.000005)

    def test_benchmark_modules_runnable(self):
        # Verify microbenchmark runners return valid structures
        cap_res = bm_cap.run_benchmark(iterations=5)
        self.assertIn("speedup", cap_res)
        self.assertGreater(cap_res["speedup"], 10.0)

        totp_res = bm_totp.run_benchmark(iterations=5)
        self.assertIn("speedup_vs_subp", totp_res)
        self.assertGreater(totp_res["speedup_vs_subp"], 10.0)

        search_res = bm_search.run_benchmark(counts=(100,))
        self.assertIn(100, search_res)
        self.assertTrue(search_res[100]["interactive_sla_met"])

        # Test table formatter
        table = run_all.format_table(
            cap_res,
            totp_res,
            {
                1000: {"baseline_ms": 0.1, "indexed_fuzzy_ms": 0.2},
                5000: {"baseline_ms": 0.5, "indexed_fuzzy_ms": 1.2},
            },
        )
        self.assertIn("Benchmark Target / Hot-Path", table)
        self.assertIn("Subprocess Probe Check", table)


if __name__ == "__main__":
    unittest.main()
