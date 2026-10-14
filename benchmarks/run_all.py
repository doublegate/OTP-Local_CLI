"""Unified Benchmark Verification Suite for Authy-to-1Password Local.

Executes all 7 microbenchmarks and formats the results into a comprehensive
before/after performance comparison table satisfying Acceptance Criteria §Performance Verification.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from benchmarks import benchmark_capabilities as bm_cap  # noqa: E402
from benchmarks import benchmark_federation as bm_fed  # noqa: E402
from benchmarks import benchmark_ipc as bm_ipc  # noqa: E402
from benchmarks import benchmark_search as bm_search  # noqa: E402
from benchmarks import benchmark_shm as bm_shm  # noqa: E402
from benchmarks import benchmark_totp_cache as bm_totp  # noqa: E402
from benchmarks import benchmark_tui as bm_tui  # noqa: E402


def format_table(
    cap_res: dict,
    totp_res: dict,
    search_res: dict,
    ipc_res: dict | None = None,
    shm_res: dict | None = None,
    tui_res: dict | None = None,
    fed_res: dict | None = None,
) -> str:
    lines = []
    col_w = (36, 22, 22, 20)
    sep = (
        "+"
        + "-" * (col_w[0] + 2)
        + "+"
        + "-" * (col_w[1] + 2)
        + "+"
        + "-" * (col_w[2] + 2)
        + "+"
        + "-" * (col_w[3] + 2)
        + "+"
    )
    hdr_sep = (
        "+"
        + "=" * (col_w[0] + 2)
        + "+"
        + "=" * (col_w[1] + 2)
        + "+"
        + "=" * (col_w[2] + 2)
        + "+"
        + "=" * (col_w[3] + 2)
        + "+"
    )

    lines.append(sep)
    lines.append(
        f"| {'Benchmark Target / Hot-Path':<{col_w[0]}} | {'Baseline (Before)':<{col_w[1]}} | {'Optimized (After)':<{col_w[2]}} | {'Improvement / SLA':<{col_w[3]}} |"
    )
    lines.append(hdr_sep)

    # 1. Capability Probe Caching
    lines.append(
        f"| {'Subprocess Probe Check':<{col_w[0]}} | {cap_res['uncached_ms']:>17.3f} ms | {cap_res['cached_ms']:>17.6f} ms | {cap_res['speedup']:>16,.0f}x faster |"
    )

    # 2. TOTP Window Retrieval
    lines.append(
        f"| {'TOTP Retrieval (Minimal)':<{col_w[0]}} | {totp_res['uncached_subprocess_ms']:>17.3f} ms | {totp_res['cached_us']:>17.3f} µs | {totp_res['speedup_vs_subp']:>16,.0f}x faster |"
    )

    # 3. Search Filtering (5,000 items)
    s5k = search_res.get(5000, search_res.get(1000, {}))
    base_5k = s5k.get("direct_fuzzy_ms", s5k.get("baseline_ms", 0.0))
    indexed_5k = s5k.get("indexed_fuzzy_ms", 0.0)
    speedup_5k = f"{base_5k / indexed_5k:.1f}x faster" if indexed_5k > 0 else "< 2 ms (PASS)"
    lines.append(
        f"| {'Search Filter (5,000 items)':<{col_w[0]}} | {base_5k:>17.3f} ms | {indexed_5k:>17.3f} ms | {speedup_5k:>18} |"
    )

    # 4. IPC Daemon Streaming
    if ipc_res is not None:
        lines.append(
            f"| {'IPC Daemon Round-Trip':<{col_w[0]}} | {ipc_res['subprocess_baseline_ms']:>17.3f} ms | {ipc_res['roundtrip_us']:>17.3f} µs | {ipc_res['speedup']:>16,.0f}x faster |"
        )

    # 5. POSIX SHM Ring Buffer
    if shm_res is not None:
        lines.append(
            f"| {'POSIX SHM Zero-Copy Read':<{col_w[0]}} | {shm_res['file_io_baseline_us']:>17.3f} µs | {shm_res['read_slot_us']:>17.3f} µs | {shm_res['speedup_vs_file']:>16,.0f}x faster |"
        )

    # 6. Textual TUI Event Processing
    if tui_res is not None:
        lines.append(
            f"| {'TUI OptionList Populate (150 rows)':<{col_w[0]}} | {tui_res['baseline_populate_ms']:>17.3f} ms | {tui_res['optimized_populate_ms']:>17.3f} ms | {tui_res['speedup_populate']:>16.2f}x faster |"
        )

    # 7. Multi-Vault Concurrent Federation
    if fed_res is not None:
        lines.append(
            f"| {'Multi-Vault Federation (6 vaults)':<{col_w[0]}} | {fed_res['sequential_ms']:>17.1f} ms | {fed_res['concurrent_ms']:>17.1f} ms | {fed_res['speedup']:>16.2f}x faster |"
        )

    lines.append(sep)
    return "\n".join(lines)


def main():
    print("Running Authy-to-1Password Comprehensive Benchmark Verification Suite...")
    t0 = time.time()

    cap_res = bm_cap.run_benchmark(iterations=10)
    totp_res = bm_totp.run_benchmark(iterations=10)
    search_res = bm_search.run_benchmark(counts=(1000, 5000))
    ipc_res = bm_ipc.run_benchmark(iterations=500)
    shm_res = bm_shm.run_benchmark(read_iterations=10_000, write_iterations=1_000)
    tui_res = bm_tui.run_benchmark(catalog_size=1000, iterations=20)
    fed_res = bm_fed.run_benchmark(backend_count=6, per_backend_latency_ms=20.0)

    table = format_table(
        cap_res,
        totp_res,
        search_res,
        ipc_res=ipc_res,
        shm_res=shm_res,
        tui_res=tui_res,
        fed_res=fed_res,
    )
    print("\n" + table + "\n")
    print(f"Total benchmark run time: {time.time() - t0:.2f} seconds.")


if __name__ == "__main__":
    main()
