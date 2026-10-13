"""Microbenchmark: External tool subprocess capability checks vs cached probes."""

import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from authy_local.backends.onepassword import clear_probe_cache, probe  # noqa: E402


def run_benchmark(iterations: int = 50) -> dict[str, Any]:
    """Compare latency of spawning subprocess capability checks vs cached lookup."""
    env = dict(os.environ)

    # 1. Baseline: Uncached subprocess execution (binary --version)
    start = time.perf_counter()
    for _ in range(iterations):
        subprocess.run(
            ["python3", "--version"],
            env=env,
            capture_output=True,
            timeout=5,
        )
    uncached_sec = (time.perf_counter() - start) / iterations

    # 2. Optimized: Actual authy_local onepassword.probe() session cache
    clear_probe_cache()
    with (
        patch("shutil.which", return_value="/usr/bin/op"),
        patch(
            "authy_local.backends.onepassword.run",
            return_value=SimpleNamespace(returncode=0, stdout=b"2.39.0\n"),
        ),
    ):
        # Warm the capability cache
        probe(env)

        cached_iterations = 200_000
        start = time.perf_counter()
        for _ in range(cached_iterations):
            probe(env)
        cached_sec = (time.perf_counter() - start) / cached_iterations

    speedup = uncached_sec / cached_sec if cached_sec > 0 else 1.0

    return {
        "uncached_ms": uncached_sec * 1000,
        "cached_ms": cached_sec * 1000,
        "cached_ns": cached_sec * 1_000_000_000,
        "speedup": speedup,
        "ops_per_sec": 1.0 / cached_sec if cached_sec > 0 else 0,
    }


if __name__ == "__main__":
    res = run_benchmark()
    print("=== Subprocess Capability Probe Benchmark ===")
    print(f"Uncached subprocess (python3 --version): {res['uncached_ms']:.3f} ms")
    print(
        f"Cached session probe:                    {res['cached_ms']:.6f} ms ({res['cached_ns']:.1f} ns)"
    )
    print(f"Speedup:                                 {res['speedup']:,.0f}x faster")
