"""Microbenchmark: External tool subprocess capability checks vs cached probes."""

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from authy_local.backends.onepassword import clear_probe_cache  # noqa: E402
from authy_local.backends.onepassword import probe as op_probe

PROBE_CACHE_TTL = 300.0
_authentic_cache: dict[tuple[str, str], tuple[float, dict[str, str]]] = {}
_authentic_lock = threading.Lock()


def clear_authentic_cache() -> None:
    """Clear in-memory capability probe cache."""
    with _authentic_lock:
        _authentic_cache.clear()


def resolve_authentic_tool(env: dict[str, str]) -> tuple[str, str]:
    """Find an authentic available system executable without mocks.

    Checks candidates that are standard CLI tools in authentic environments.
    Guaranteed to locate a real executable (e.g. python3, git, sh, or op).
    """
    path_env = env.get("PATH", "")
    candidates = ("op", "git", "python3", "sh")
    for name in candidates:
        found = shutil.which(name, path=path_env)
        if found:
            try:
                res = subprocess.run(
                    [found, "--version"],
                    env=env,
                    capture_output=True,
                    timeout=5,
                )
                if res.returncode == 0:
                    return name, found
            except Exception:
                continue

    # Resilient fallback to current Python interpreter
    return "python3", sys.executable


def probe_authentic_tool(
    name: str,
    executable: str,
    env: dict[str, str],
    *,
    use_cache: bool = True,
) -> dict[str, str]:
    """Perform authentic capability probe with session caching."""
    # If 1Password CLI is the detected target tool, leverage production probe directly
    if name == "op":
        return op_probe(env, use_cache=use_cache)

    cache_key = (name, env.get("PATH", ""))
    now = time.monotonic()
    if use_cache:
        with _authentic_lock:
            cached = _authentic_cache.get(cache_key)
            if cached is not None:
                cached_time, cap = cached
                if now - cached_time < PROBE_CACHE_TTL:
                    return dict(cap)
                _authentic_cache.pop(cache_key, None)

    res = subprocess.run(
        [executable, "--version"],
        env=env,
        capture_output=True,
        timeout=5,
    )
    if res.returncode == 0:
        ver = res.stdout.decode("utf-8", errors="replace").strip().splitlines()[0]
        capability = {
            "state": "available",
            "path": executable,
            "version": ver,
        }
        if use_cache:
            with _authentic_lock:
                _authentic_cache[cache_key] = (now, capability)
        return dict(capability)
    return {"state": "unknown", "path": executable}


def run_benchmark(iterations: int = 50) -> dict[str, Any]:
    """Compare latency of spawning subprocess capability checks vs cached lookup."""
    env = dict(os.environ)
    tool_name, tool_path = resolve_authentic_tool(env)

    # 1. Baseline: Uncached real subprocess execution (tool --version)
    start = time.perf_counter()
    for _ in range(iterations):
        subprocess.run(
            [tool_path, "--version"],
            env=env,
            capture_output=True,
            timeout=5,
        )
    uncached_sec = (time.perf_counter() - start) / iterations

    # 2. Optimized: Authentic capability session cache
    if tool_name == "op":
        clear_probe_cache()
    else:
        clear_authentic_cache()

    # Warm cache with initial real probe
    probe_authentic_tool(tool_name, tool_path, env, use_cache=True)

    cached_iterations = 100_000
    start = time.perf_counter()
    for _ in range(cached_iterations):
        probe_authentic_tool(tool_name, tool_path, env, use_cache=True)
    cached_sec = (time.perf_counter() - start) / cached_iterations

    speedup = uncached_sec / cached_sec if cached_sec > 0 else 1.0

    return {
        "uncached_ms": uncached_sec * 1000,
        "cached_ms": cached_sec * 1000,
        "cached_ns": cached_sec * 1_000_000_000,
        "speedup": speedup,
        "ops_per_sec": 1.0 / cached_sec if cached_sec > 0 else 0,
        "tool_probed": tool_name,
        "tool_path": tool_path,
    }


if __name__ == "__main__":
    res = run_benchmark()
    print("=== Subprocess Capability Probe Benchmark ===")
    print(f"Target tool:                             {res['tool_probed']} ({res['tool_path']})")
    print(f"Uncached subprocess probe:               {res['uncached_ms']:.3f} ms")
    print(
        f"Cached session probe:                    {res['cached_ms']:.6f} ms ({res['cached_ns']:.1f} ns)"
    )
    print(f"Speedup:                                 {res['speedup']:,.0f}x faster")
    print(f"Throughput:                              {res['ops_per_sec']:,.0f} lookups/sec")
