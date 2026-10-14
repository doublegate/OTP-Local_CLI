"""Microbenchmark: IPC daemon streaming throughput and round-trip request/response latency."""

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from authy_local.ipc import recv_framed_message, send_framed_message  # noqa: E402


def run_benchmark(iterations: int = 2000) -> dict[str, Any]:
    """Measure IPC daemon streaming throughput and round-trip latency over Unix domain socket."""
    sock_dir = Path("/tmp")
    sock_path = sock_dir / f"otp_bench_ipc_{os.getpid()}_{time.time_ns()}.sock"
    if sock_path.exists():
        try:
            sock_path.unlink()
        except OSError:
            pass

    server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_sock.bind(str(sock_path))
    server_sock.listen(1)

    running = True

    def server_worker():
        server_sock.settimeout(2.0)
        try:
            conn, _ = server_sock.accept()
            while running:
                msg = recv_framed_message(conn)
                if not msg:
                    break
                send_framed_message(conn, {"status": "ok", "echo": msg.get("seq", 0)})
            conn.close()
        except socket.timeout, OSError:
            pass

    t_srv = threading.Thread(target=server_worker, daemon=True)
    t_srv.start()

    # 1. Baseline: Subprocess invocation latency (echo)
    subp_iters = 20
    t0 = time.perf_counter()
    for _ in range(subp_iters):
        subprocess.run(["echo", "ping"], capture_output=True, timeout=5)
    subprocess_baseline_ms = (time.perf_counter() - t0) * 1000 / subp_iters

    # 2. Optimized: Persistent socket CBOR round-trip streaming
    client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client_sock.connect(str(sock_path))

    # Warmup
    for i in range(50):
        send_framed_message(client_sock, {"action": "ping", "seq": i})
        _ = recv_framed_message(client_sock)

    t0 = time.perf_counter()
    for i in range(iterations):
        send_framed_message(client_sock, {"action": "ping", "seq": i})
        _ = recv_framed_message(client_sock)
    elapsed_sec = time.perf_counter() - t0

    running = False
    client_sock.close()
    server_sock.close()
    t_srv.join(timeout=1.0)
    if sock_path.exists():
        try:
            sock_path.unlink()
        except OSError:
            pass

    roundtrip_sec = elapsed_sec / iterations if iterations > 0 else 0
    roundtrip_ms = roundtrip_sec * 1000
    roundtrip_us = roundtrip_sec * 1_000_000
    ops_sec = iterations / elapsed_sec if elapsed_sec > 0 else 0
    speedup = subprocess_baseline_ms / roundtrip_ms if roundtrip_ms > 0 else 1.0

    return {
        "subprocess_baseline_ms": subprocess_baseline_ms,
        "roundtrip_ms": roundtrip_ms,
        "roundtrip_us": roundtrip_us,
        "streaming_throughput_ops_sec": ops_sec,
        "speedup": speedup,
        "sla_met": roundtrip_ms < 1.0 and ops_sec > 5000,
    }


if __name__ == "__main__":
    res = run_benchmark()
    print("=== IPC Daemon Streaming Benchmark ===")
    print(f"Subprocess Baseline Latency:    {res['subprocess_baseline_ms']:.3f} ms")
    print(
        f"IPC Round-Trip Latency:          {res['roundtrip_us']:.3f} µs ({res['roundtrip_ms']:.4f} ms)"
    )
    print(f"Streaming Throughput:            {res['streaming_throughput_ops_sec']:,.0f} req/sec")
    print(f"Speedup vs Subprocess:           {res['speedup']:,.0f}x faster")
    print(f"Interactive SLA (< 1.0 ms):      {'PASS' if res['sla_met'] else 'FAIL'}")
