"""Microbenchmark: POSIX SHM ring buffer read/write concurrency and zero-copy throughput."""

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from authy_local.shm import ShmRingBuffer  # noqa: E402


def run_benchmark(read_iterations: int = 50_000, write_iterations: int = 5_000) -> dict[str, Any]:
    """Benchmark zero-copy atomic read and write throughput in POSIX shared memory."""
    shm_name = f"bench-shm-{os.getpid()}-{time.time_ns() % 1000000}"
    shm = ShmRingBuffer(name=shm_name, create=True)

    try:
        now = time.time()
        account = "test_user@benchmark.local"
        shm.write_slot(account, "123456", now + 60, now + 60)

        # 1. Baseline: Minimal disk/tmpfs file I/O read
        tmp_file = Path(f"/tmp/{shm_name}.tmp")
        tmp_file.write_text("123456\n", encoding="ascii")
        t0 = time.perf_counter()
        file_iters = 1000
        for _ in range(file_iters):
            _ = tmp_file.read_text(encoding="ascii")
        file_io_sec = (time.perf_counter() - t0) / file_iters
        tmp_file.unlink(missing_ok=True)

        # 2. Optimized: Zero-copy lockless seqlock read
        t0 = time.perf_counter()
        for _ in range(read_iterations):
            _ = shm.read_slot(account)
        read_elapsed = time.perf_counter() - t0
        read_sec = read_elapsed / read_iterations if read_iterations > 0 else 0

        # 3. Synchronized write
        t0 = time.perf_counter()
        for i in range(write_iterations):
            shm.write_slot(account, f"{i % 1000000:06d}", now + 60, now + 60)
        write_elapsed = time.perf_counter() - t0
        write_sec = write_elapsed / write_iterations if write_iterations > 0 else 0

        # 4. Concurrent Reader/Writer stress (concurrency verification)
        stop_event = threading.Event()
        corruptions = [0]
        read_counts = [0]

        def reader():
            while not stop_event.is_set():
                val = shm.read_slot(account)
                if val is not None and len(val.get("code", "")) != 6:
                    corruptions[0] += 1
                read_counts[0] += 1

        t_r1 = threading.Thread(target=reader, daemon=True)
        t_r2 = threading.Thread(target=reader, daemon=True)
        t_r1.start()
        t_r2.start()

        conc_writes = 2000
        t0 = time.perf_counter()
        for i in range(conc_writes):
            shm.write_slot(account, f"{i % 1000000:06d}", now + 60, now + 60)
        conc_elapsed = time.perf_counter() - t0
        stop_event.set()
        t_r1.join(timeout=1.0)
        t_r2.join(timeout=1.0)

        total_conc_ops = conc_writes + read_counts[0]
        conc_ops_sec = total_conc_ops / conc_elapsed if conc_elapsed > 0 else 0

        read_us = read_sec * 1_000_000
        read_ns = read_sec * 1_000_000_000
        write_us = write_sec * 1_000_000
        speedup = file_io_sec / read_sec if read_sec > 0 else 1.0

        return {
            "file_io_baseline_us": file_io_sec * 1_000_000,
            "read_slot_us": read_us,
            "read_slot_ns": read_ns,
            "write_slot_us": write_us,
            "read_ops_sec": 1.0 / read_sec if read_sec > 0 else 0,
            "write_ops_sec": 1.0 / write_sec if write_sec > 0 else 0,
            "concurrent_ops_sec": conc_ops_sec,
            "speedup_vs_file": speedup,
            "corruptions": corruptions[0],
            "sla_met": read_us < 10.0 and corruptions[0] == 0,
        }

    finally:
        shm.unlink()


if __name__ == "__main__":
    res = run_benchmark()
    print("=== POSIX SHM Ring Buffer Benchmark ===")
    print(f"File I/O Baseline:           {res['file_io_baseline_us']:.3f} µs")
    print(
        f"SHM Zero-Copy Read Latency:  {res['read_slot_us']:.3f} µs ({res['read_slot_ns']:.1f} ns)"
    )
    print(f"SHM Write Latency:           {res['write_slot_us']:.3f} µs")
    print(f"Read Throughput:             {res['read_ops_sec']:,.0f} ops/sec")
    print(f"Write Throughput:            {res['write_ops_sec']:,.0f} ops/sec")
    print(
        f"Concurrent Stress Throughput:{res['concurrent_ops_sec']:,.0f} ops/sec (Corruptions: {res['corruptions']})"
    )
    print(f"Speedup vs File I/O:         {res['speedup_vs_file']:,.0f}x faster")
    print(f"SLA Met (< 10 µs, 0 errors): {'PASS' if res['sla_met'] else 'FAIL'}")
