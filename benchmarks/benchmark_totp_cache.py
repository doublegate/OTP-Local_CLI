"""Microbenchmark: Uncached TOTP secret decryption vs in-memory window cache."""

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from authy_local.cache import (  # noqa: E402
    clear_cache,
    current_time_step,
    get_cached_totp,
    set_cached_totp,
)


def run_benchmark(iterations: int = 30) -> dict[str, Any]:
    """Measure uncached subprocess extraction vs ephemeral in-memory cache lookup."""
    # 1. Baseline: Minimal external process execution simulating CLI decryption
    start = time.perf_counter()
    for _ in range(iterations):
        subprocess.run(
            ["echo", "654321"],
            capture_output=True,
            timeout=5,
        )
    uncached_sec = (time.perf_counter() - start) / iterations

    # Typical 1Password CLI / GPG invocation latency is ~150ms to 400ms
    op_cli_sec = 0.150

    # 2. Optimized: Actual authy_local in-memory TOTP window cache
    clear_cache()
    backend = "onepassword"
    item_id = "synthetic_item_id_abcdef"
    step = current_time_step(30)
    set_cached_totp(backend, item_id, step, "654321")

    cached_iterations = 200_000
    start = time.perf_counter()
    for _ in range(cached_iterations):
        get_cached_totp(backend, item_id, step)
    cached_sec = (time.perf_counter() - start) / cached_iterations

    speedup_subp = uncached_sec / cached_sec if cached_sec > 0 else 1.0
    speedup_op = op_cli_sec / cached_sec if cached_sec > 0 else 1.0

    return {
        "uncached_subprocess_ms": uncached_sec * 1000,
        "op_cli_typical_ms": op_cli_sec * 1000,
        "cached_ms": cached_sec * 1000,
        "cached_us": cached_sec * 1_000_000,
        "cached_ns": cached_sec * 1_000_000_000,
        "speedup_vs_subp": speedup_subp,
        "speedup_vs_op": speedup_op,
        "ops_per_sec": 1.0 / cached_sec if cached_sec > 0 else 0,
    }


if __name__ == "__main__":
    res = run_benchmark()
    print("=== TOTP Window Cache Benchmark ===")
    print(f"Uncached subprocess (minimal echo):  {res['uncached_subprocess_ms']:.3f} ms")
    print(f"Uncached 1Password CLI (typical):   {res['op_cli_typical_ms']:.1f} ms")
    print(
        f"In-memory cached window lookup:     {res['cached_us']:.3f} µs ({res['cached_ns']:.1f} ns)"
    )
    print(f"Speedup vs minimal subprocess:      {res['speedup_vs_subp']:,.0f}x faster")
    print(f"Speedup vs typical 1Password CLI:   {res['speedup_vs_op']:,.0f}x faster")
