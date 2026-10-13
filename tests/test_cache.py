"""Comprehensive unit tests for ephemeral in-memory TOTP window cache."""

import threading
import time
import unittest
from unittest.mock import patch

from authy_local.cache import (
    MAX_CACHE_ENTRIES,
    cache_stats,
    clear_cache,
    current_time_step,
    get_cached_totp,
    invalidate_item,
    set_cached_totp,
)


class TestInMemoryTotpCache(unittest.TestCase):
    def setUp(self):
        clear_cache()

    def tearDown(self):
        clear_cache()

    def test_cache_miss_returns_none(self):
        self.assertIsNone(get_cached_totp("onepassword", "item1", 100))
        self.assertIsNone(get_cached_totp("pass-otp", "github", 100))

    def test_set_and_get_roundtrip(self):
        step = current_time_step(30)
        set_cached_totp("onepassword", "item1", step, "123456")
        self.assertEqual(get_cached_totp("onepassword", "item1", step), "123456")

    def test_backend_isolation(self):
        step = 500
        set_cached_totp("onepassword", "shared_id", step, "111111", now=step * 30 + 1)
        set_cached_totp("pass-otp", "shared_id", step, "222222", now=step * 30 + 1)
        set_cached_totp("totpm", "shared_id", step, "333333", now=step * 30 + 1)

        self.assertEqual(
            get_cached_totp("onepassword", "shared_id", step, now=step * 30 + 2), "111111"
        )
        self.assertEqual(
            get_cached_totp("pass-otp", "shared_id", step, now=step * 30 + 2), "222222"
        )
        self.assertEqual(get_cached_totp("totpm", "shared_id", step, now=step * 30 + 2), "333333")

    def test_item_id_isolation(self):
        step = current_time_step(30)
        set_cached_totp("onepassword", "item_a", step, "111111")
        set_cached_totp("onepassword", "item_b", step, "222222")

        self.assertEqual(get_cached_totp("onepassword", "item_a", step), "111111")
        self.assertEqual(get_cached_totp("onepassword", "item_b", step), "222222")
        self.assertIsNone(get_cached_totp("onepassword", "item_c", step))

    def test_time_step_window_expiry(self):
        with patch("time.time", return_value=3000.0):
            step_3000 = current_time_step(30)  # 100
            set_cached_totp("onepassword", "item1", step_3000, "123456")
            self.assertEqual(get_cached_totp("onepassword", "item1", step_3000), "123456")

        # Advance time into the next 30-second window
        with patch("time.time", return_value=3031.0):
            step_3031 = current_time_step(30)  # 101
            # Cache miss for new window
            self.assertIsNone(get_cached_totp("onepassword", "item1", step_3031))
            # Previous window has expired and returns None
            self.assertIsNone(get_cached_totp("onepassword", "item1", step_3000))

    def test_custom_period_support(self):
        # 60-second period
        step = current_time_step(period=60, now=120.0)  # step = 2
        set_cached_totp("pass-otp", "custom_item", step, "987654", period=60, now=125.0)
        # Still valid at second 179
        self.assertEqual(get_cached_totp("pass-otp", "custom_item", step, now=179.0), "987654")
        # Expired at second 180
        self.assertIsNone(get_cached_totp("pass-otp", "custom_item", step, now=180.0))

    def test_code_format_validation(self):
        step = current_time_step(30)
        # Valid 6-digit and 8-digit codes
        set_cached_totp("onepassword", "item1", step, "123456")
        set_cached_totp("onepassword", "item2", step, "12345678")
        self.assertEqual(get_cached_totp("onepassword", "item1", step), "123456")
        self.assertEqual(get_cached_totp("onepassword", "item2", step), "12345678")

        # Invalid lengths and characters
        for invalid in ("12345", "1234567", "123456789", "abcdef", "12 456", ""):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    set_cached_totp("onepassword", "item1", step, invalid)

    def test_input_validation_errors(self):
        step = current_time_step(30)
        with self.assertRaises(ValueError):
            set_cached_totp("", "item", step, "123456")
        with self.assertRaises(ValueError):
            set_cached_totp("onepassword", "", step, "123456")
        with self.assertRaises(ValueError):
            set_cached_totp("onepassword", "item", -1, "123456")
        with self.assertRaises(ValueError):
            set_cached_totp("onepassword", "item", step, "123456", period=0)

        # get_cached_totp with invalid types returns None
        self.assertIsNone(get_cached_totp(123, "item", step))  # type: ignore
        self.assertIsNone(get_cached_totp("onepassword", None, step))  # type: ignore
        self.assertIsNone(get_cached_totp("onepassword", "item", "step"))  # type: ignore

    def test_clear_cache_purges_all(self):
        step = current_time_step(30)
        set_cached_totp("onepassword", "item1", step, "111111")
        set_cached_totp("pass-otp", "item2", step, "222222")
        self.assertEqual(cache_stats()["size"], 2)

        clear_cache()
        self.assertEqual(cache_stats()["size"], 0)
        self.assertIsNone(get_cached_totp("onepassword", "item1", step))
        self.assertIsNone(get_cached_totp("pass-otp", "item2", step))

    def test_invalidate_item_selective(self):
        step = current_time_step(30)
        set_cached_totp("pass-otp", "target_item", step, "111111")
        set_cached_totp("pass-otp", "other_item", step, "222222")

        removed = invalidate_item("pass-otp", "target_item")
        self.assertEqual(removed, 1)
        self.assertIsNone(get_cached_totp("pass-otp", "target_item", step))
        self.assertEqual(get_cached_totp("pass-otp", "other_item", step), "222222")

    def test_bounded_capacity_lru_eviction(self):
        t0 = 10000.0
        step = int(t0 // 30)

        # Fill up to capacity
        for i in range(MAX_CACHE_ENTRIES):
            set_cached_totp("onepassword", f"item_{i:04d}", step, "123456", now=t0)
        self.assertEqual(cache_stats()["size"], MAX_CACHE_ENTRIES)

        # First inserted item is present
        self.assertEqual(get_cached_totp("onepassword", "item_0000", step, now=t0), "123456")

        # Insert one more to force LRU eviction
        set_cached_totp("onepassword", "item_overflow", step, "654321", now=t0)
        self.assertLessEqual(cache_stats()["size"], MAX_CACHE_ENTRIES)
        # item_0001 (which was never touched after insert) was evicted
        self.assertIsNone(get_cached_totp("onepassword", "item_0001", step, now=t0))
        # item_0000 was touched, so it remained
        self.assertEqual(get_cached_totp("onepassword", "item_0000", step, now=t0), "123456")
        self.assertEqual(get_cached_totp("onepassword", "item_overflow", step, now=t0), "654321")

    def test_thread_safety_concurrent_access(self):
        threads = []
        errors = []
        step = current_time_step(30)

        def worker(thread_idx):
            try:
                for i in range(100):
                    item_id = f"thread_{thread_idx}_item_{i % 10}"
                    code = f"{100000 + (thread_idx * 10 + i % 10):06d}"
                    set_cached_totp("onepassword", item_id, step, code)
                    val = get_cached_totp("onepassword", item_id, step)
                    if val is not None and len(val) != 6:
                        errors.append(f"Invalid code length: {val}")
            except Exception as e:
                errors.append(str(e))

        for idx in range(10):
            t = threading.Thread(target=worker, args=(idx,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(errors, [])

    def test_sub_microsecond_performance(self):
        step = current_time_step(30)
        set_cached_totp("onepassword", "bench_item", step, "123456")

        start = time.perf_counter()
        iterations = 10000
        for _ in range(iterations):
            get_cached_totp("onepassword", "bench_item", step)
        elapsed = time.perf_counter() - start

        # Assert 10,000 lookups complete in < 20ms (< 2 µs per lookup)
        self.assertLess(
            elapsed, 0.020, f"Cache lookup too slow: {elapsed * 1000:.2f}ms for {iterations} ops"
        )


if __name__ == "__main__":
    unittest.main()
