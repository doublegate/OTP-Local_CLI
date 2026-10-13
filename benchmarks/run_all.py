"""Unified Benchmark Verification Suite for Authy-to-1Password Local.

Executes all microbenchmarks and formats the results into a clear before/after
performance comparison table satisfying Acceptance Criteria §Performance Verification.
"""

import sys
import time
from pathlib import Path

# Ensure src and benchmarks directories are in python path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from benchmarks import benchmark_capabilities as bm_cap  # noqa: E402
from benchmarks import benchmark_search as bm_search  # noqa: E402
from benchmarks import benchmark_totp_cache as bm_totp  # noqa: E402


def format_table(cap_res: dict, totp_res: dict, search_res: dict) -> str:
    lines = []
    lines.append("+" + "-" * 32 + "+" + "-" * 22 + "+" + "-" * 22 + "+" + "-" * 18 + "+")
    lines.append(
        f"| {'Benchmark Target / Hot-Path':<30} | {'Baseline (Before)':<20} | {'Optimized (After)':<20} | {'Improvement / SLA':<16} |"
    )
    lines.append("+" + "=" * 32 + "+" + "=" * 22 + "+" + "=" * 22 + "+" + "=" * 18 + "+")

    # 1. Capability Probe Caching
    lines.append(
        f"| {'Subprocess Probe Check':<30} | {cap_res['uncached_ms']:>17.3f} ms | {cap_res['cached_ms']:>17.6f} ms | {cap_res['speedup']:>14,.0f}x faster |"
    )

    # 2. TOTP Window Retrieval
    lines.append(
        f"| {'TOTP Retrieval (Minimal)':<30} | {totp_res['uncached_subprocess_ms']:>17.3f} ms | {totp_res['cached_us']:>17.3f} µs | {totp_res['speedup_vs_subp']:>14,.0f}x faster |"
    )
    lines.append(
        f"| {'TOTP Retrieval (1Password CLI)':<30} | {totp_res['op_cli_typical_ms']:>17.1f} ms | {totp_res['cached_us']:>17.3f} µs | {totp_res['speedup_vs_op']:>14,.0f}x faster |"
    )

    # 3. Search Filtering (1,000 items)
    s1k = search_res[1000]
    base_1k = s1k.get("direct_fuzzy_ms", s1k.get("baseline_ms", 0.0))
    speedup_1k = (
        f"{base_1k / s1k['indexed_fuzzy_ms']:.1f}x faster"
        if s1k.get("indexed_fuzzy_ms", 0) > 0
        else "< 1 ms (PASS)"
    )
    lines.append(
        f"| {'Search Filter (1,000 items)':<30} | {base_1k:>17.3f} ms | {s1k['indexed_fuzzy_ms']:>17.3f} ms | {speedup_1k:>16} |"
    )

    # 4. Search Filtering (5,000 items)
    s5k = search_res[5000]
    base_5k = s5k.get("direct_fuzzy_ms", s5k.get("baseline_ms", 0.0))
    speedup_5k = (
        f"{base_5k / s5k['indexed_fuzzy_ms']:.1f}x faster"
        if s5k.get("indexed_fuzzy_ms", 0) > 0
        else "< 2 ms (PASS)"
    )
    lines.append(
        f"| {'Search Filter (5,000 items)':<30} | {base_5k:>17.3f} ms | {s5k['indexed_fuzzy_ms']:>17.3f} ms | {speedup_5k:>16} |"
    )

    lines.append("+" + "-" * 32 + "+" + "-" * 22 + "+" + "-" * 22 + "+" + "-" * 18 + "+")
    return "\n".join(lines)


def main():
    print("Running Authy-to-1Password Benchmark Verification Suite...")
    t0 = time.time()

    cap_res = bm_cap.run_benchmark()
    totp_res = bm_totp.run_benchmark()
    search_res = bm_search.run_benchmark()

    table = format_table(cap_res, totp_res, search_res)
    print("\n" + table + "\n")
    print(f"Total benchmark run time: {time.time() - t0:.2f} seconds.")


if __name__ == "__main__":
    main()
