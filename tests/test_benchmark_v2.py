"""Comprehensive Benchmark and Compatibility Validation Suite for v2.0.0 (Phase 12 / Sprint 12.2)."""

import time
import unittest
import warnings
from unittest.mock import patch

from authy_local import (
    AsyncFederatedResolver,
    AsyncMockBackend,
    SecureBuffer,
    legacy_copy_code,
    legacy_list_accounts,
    legacy_show_code,
)


class TestBenchmarkV2(unittest.IsolatedAsyncioTestCase):
    async def test_multi_account_concurrent_throughput_speedup(self):
        """Verify minimum 3x throughput speedup across multi-vault queries as required by exit criteria."""
        backend_count = 6
        per_backend_latency = 0.04  # 40ms simulated I/O per backend

        backends = [
            AsyncMockBackend(
                name=f"vault_{i}",
                tokens={f"service_{i}_{j}": "JBSWY3DPEHPK3PXP" for j in range(5)},
                latency=per_backend_latency,
            )
            for i in range(backend_count)
        ]

        # 1. Measure sequential execution time across all backends
        t_seq_start = time.monotonic()
        seq_items = []
        for b in backends:
            if await b.is_available():
                items = await b.list_items()
                seq_items.extend(items)
        t_seq_elapsed = time.monotonic() - t_seq_start

        # 2. Measure concurrent AsyncFederatedResolver execution time
        resolver = AsyncFederatedResolver(backends=backends)
        t_conc_start = time.monotonic()
        conc_items = await resolver.search(query="")
        t_conc_elapsed = time.monotonic() - t_conc_start

        self.assertEqual(len(conc_items), 30)

        speedup = t_seq_elapsed / max(0.001, t_conc_elapsed)
        # Assert at least 3.0x throughput speedup
        self.assertGreaterEqual(
            speedup,
            3.0,
            f"Expected >= 3.0x speedup, but achieved {speedup:.2f}x (seq: {t_seq_elapsed:.3f}s, conc: {t_conc_elapsed:.3f}s)",
        )

    def test_memory_security_zeroize_overhead(self):
        """Verify SecureBuffer allocation and cryptographic zeroization overhead is under 150us."""
        rounds = 200
        t0 = time.monotonic()
        for _ in range(rounds):
            with SecureBuffer(64) as buf:
                buf.write(b"TOP_SECRET_MFA_SEED_TEST_VECTOR_1234567890")
                _ = buf.read()
        elapsed = time.monotonic() - t0
        avg_us = (elapsed / rounds) * 1_000_000
        self.assertLess(
            avg_us, 150.0, f"Average buffer overhead {avg_us:.2f}us exceeded 150us threshold"
        )


class TestLegacyCompatibilityV2(unittest.TestCase):
    @patch("authy_local.backends.onepassword.retrieve")
    def test_legacy_show_code_emits_deprecation_warning(self, mock_retrieve):
        mock_retrieve.return_value = "123456"
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            code = legacy_show_code("GitHub", backend="onepassword")
            self.assertEqual(code, "123456")
            self.assertTrue(any(issubclass(item.category, DeprecationWarning) for item in w))
            self.assertTrue(any("deprecated in v2.0.0" in str(item.message) for item in w))

    @patch("authy_local.compat.get_backend_records")
    def test_legacy_list_accounts_emits_deprecation_warning(self, mock_records):
        mock_records.return_value = [("GitHub", "vault"), ("GitLab", "vault")]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            items = legacy_list_accounts(backend="onepassword")
            self.assertEqual(items, ["GitHub", "GitLab"])
            self.assertTrue(any(issubclass(item.category, DeprecationWarning) for item in w))

    @patch("authy_local.compat.legacy_show_code")
    @patch("authy_local.compat.copy_to_clipboard")
    def test_legacy_copy_code_emits_deprecation_warning(self, mock_copy, mock_show):
        mock_show.return_value = "654321"
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            ok = legacy_copy_code("AWS", backend="onepassword")
            self.assertTrue(ok)
            self.assertEqual(mock_copy.call_count, 1)
            self.assertTrue(any(issubclass(item.category, DeprecationWarning) for item in w))


if __name__ == "__main__":
    unittest.main()
