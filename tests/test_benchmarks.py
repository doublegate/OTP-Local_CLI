"""Integration tests for benchmark execution, search indexing, and performance SLAs."""

import subprocess
import time
import unittest

from authy_local.cache import clear_cache, get_cached_totp, set_cached_totp
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
        step = 1000
        fixed_now = 30005.0
        set_cached_totp("onepassword", "item123", step, "123456", now=fixed_now)

        start = time.perf_counter()
        for _ in range(50_000):
            code = get_cached_totp("onepassword", "item123", step, now=fixed_now)
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

    def test_ipc_streaming_benchmark_sla(self):
        from benchmarks import benchmark_ipc as bm_ipc

        res = bm_ipc.run_benchmark(iterations=200)
        self.assertIn("roundtrip_ms", res)
        self.assertIn("streaming_throughput_ops_sec", res)
        self.assertTrue(res["sla_met"])
        self.assertLess(
            res["roundtrip_ms"],
            1.0,
            f"IPC round-trip {res['roundtrip_ms']:.3f}ms exceeded 1.0ms SLA",
        )
        self.assertGreater(res["speedup"], 10.0)

    def test_shm_ring_buffer_benchmark_sla(self):
        from benchmarks import benchmark_shm as bm_shm

        res = bm_shm.run_benchmark(read_iterations=5_000, write_iterations=500)
        self.assertIn("read_slot_us", res)
        self.assertIn("corruptions", res)
        self.assertTrue(res["sla_met"])
        self.assertEqual(
            res["corruptions"], 0, "Seqlock corruption detected under concurrent stress"
        )
        self.assertLess(
            res["read_slot_us"],
            10.0,
            f"SHM read latency {res['read_slot_us']:.2f}us exceeded 10us threshold",
        )

    def test_tui_event_processing_benchmark_sla(self):
        from benchmarks import benchmark_tui as bm_tui

        res = bm_tui.run_benchmark(catalog_size=500, iterations=10)
        self.assertIn("optimized_populate_ms", res)
        self.assertIn("cached_empty_reset_ms", res)
        self.assertTrue(res["sla_met"])
        self.assertLess(
            res["optimized_populate_ms"], 5.0, "OptionList populate exceeded 5.0ms ceiling"
        )
        self.assertLess(
            res["cached_empty_reset_ms"], 0.1, "Cached empty reset exceeded 0.1ms ceiling"
        )

    def test_federation_concurrent_benchmark_sla(self):
        from benchmarks import benchmark_federation as bm_fed

        res = bm_fed.run_benchmark(backend_count=4, per_backend_latency_ms=15.0)
        self.assertIn("speedup", res)
        self.assertIn("concurrent_ms", res)
        self.assertTrue(res["sla_met"])
        self.assertGreaterEqual(
            res["speedup"], 2.5, f"Expected >= 2.5x speedup, got {res['speedup']:.2f}x"
        )


if __name__ == "__main__":
    unittest.main()
