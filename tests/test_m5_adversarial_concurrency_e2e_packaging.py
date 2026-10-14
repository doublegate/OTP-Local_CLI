"""Empirical Tier 5 Adversarial Concurrency, E2E Pipeline & Clean-Room Packaging Suite.

Authored by Challenger M5-2 (Adversarial Concurrency, E2E & Package Clean-Room Challenger) to verify:
1. POSIX Shared Memory Concurrency & Seqlock Invariance:
   - High-throughput concurrent multi-threaded reader/writer stress without deadlocks or torn reads.
   - Linear collision probing under concurrent churn for colliding slot hashes.
   - Multi-process concurrency verifying process-level locking and memory visibility.
   - Mutex lock contention and timeout resilience.
2. Daemon Unix IPC Concurrency & Framing Robustness:
   - High-throughput concurrent requests (cache, get_totp, verify, list, status) across worker pools.
   - Concurrency barrier burst storm (simultaneous connections at exact millisecond).
   - Slow-client head-of-line blocking avoidance.
   - Pathological and malformed framing stress (oversized headers, truncated payloads, garbled bytes).
3. Clean-Room Wheel Smoke Packaging:
   - Isolated clean virtual environment installation using offline dist/wheels.
   - Execution verification of all CLI entrypoints: --version, --help, doctor, doctor --json, daemon --help.
   - Clean-room module imports without developer tree leakage.
4. Opaque-Box E2E Integration:
   - Complete execution of all four E2E tiers (Tier 1-4).
"""

import concurrent.futures
import json
import multiprocessing
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import venv
from pathlib import Path
from typing import Any

from authy_local.daemon import DaemonServer
from authy_local.ipc import (
    MAX_IPC_MESSAGE_SIZE,
    pid_path,
    recv_framed_message,
    send_ipc_request,
    socket_path,
)
from authy_local.shm import (
    SLOT_COUNT,
    ShmRingBuffer,
    _account_hash,
)

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# Multi-Process Worker Functions (top-level for pickle compatibility)
# --------------------------------------------------------------------------


def _mp_writer_worker(shm_name: str, account: str, iterations: int, done_queue: Any) -> None:
    """Worker process writing updates to a shared memory segment."""
    try:
        shm = ShmRingBuffer(name=shm_name, create=False)
        for i in range(iterations):
            now = time.time()
            code = f"{i % 1000000:06d}"
            ok = shm.write_slot(account, code, now + 60, now + 60)
            if not ok:
                done_queue.put((False, f"Failed write at iteration {i}"))
                shm.close()
                return
            time.sleep(0.0001)
        shm.close()
        done_queue.put((True, iterations))
    except Exception as exc:
        done_queue.put((False, str(exc)))


def _mp_reader_worker(shm_name: str, account: str, iterations: int, done_queue: Any) -> None:
    """Worker process reading updates from a shared memory segment."""
    try:
        shm = ShmRingBuffer(name=shm_name, create=False)
        reads_done = 0
        corruptions = 0
        for _ in range(iterations):
            val = shm.read_slot(account)
            if val is not None:
                code = val.get("code", "")
                if len(code) != 6 or not code.isdigit():
                    corruptions += 1
            reads_done += 1
            time.sleep(0.0001)
        shm.close()
        done_queue.put((True, reads_done, corruptions))
    except Exception as exc:
        done_queue.put((False, 0, str(exc)))


# --------------------------------------------------------------------------
# Suite 1: POSIX Shared Memory Concurrency & Stress
# --------------------------------------------------------------------------


class TestShmConcurrencyAndStress(unittest.TestCase):
    """Empirical adversarial stress testing of POSIX SHM ring buffer."""

    def setUp(self) -> None:
        self.shm_name = f"test-adv-shm-{os.getpid()}-{time.time_ns() % 1000000}"
        self.shm = ShmRingBuffer(name=self.shm_name, create=True)

    def tearDown(self) -> None:
        if self.shm is not None:
            self.shm.unlink()

    def test_shm_concurrent_high_throughput_readers_writers(self) -> None:
        """Adversarial stress: 8 readers + 4 writers concurrently accessing SHM."""
        num_readers = 8
        num_writers = 4
        writes_per_writer = 500
        stop_event = threading.Event()
        corruptions = [0]
        torn_reads = [0]
        total_reads = [0]
        counter_lock = threading.Lock()

        # Seed initial slots
        now = time.time()
        for w in range(num_writers):
            self.shm.write_slot(f"user_{w}@corp.internal", "111111", now + 60, now + 60)

        def writer_task(writer_id: int):
            account = f"user_{writer_id}@corp.internal"
            writer_shm = ShmRingBuffer(name=self.shm_name, create=False)
            try:
                for i in range(writes_per_writer):
                    cur_now = time.time()
                    code = f"{(writer_id * 100000 + i) % 1000000:06d}"
                    for _ in range(5):
                        if writer_shm.write_slot(account, code, cur_now + 60, cur_now + 60):
                            break
                        time.sleep(0.0001)
                    else:
                        with counter_lock:
                            corruptions[0] += 1
                    time.sleep(0.0001)
            finally:
                writer_shm.close()

        def reader_task():
            local_reads = 0
            reader_shm = ShmRingBuffer(name=self.shm_name, create=False)
            try:
                while not stop_event.is_set():
                    for w in range(num_writers):
                        account = f"user_{w}@corp.internal"
                        res = reader_shm.read_slot(account)
                        local_reads += 1
                        if res is not None:
                            code = res.get("code", "")
                            if len(code) != 6 or not code.isdigit():
                                with counter_lock:
                                    torn_reads[0] += 1
            finally:
                reader_shm.close()
            with counter_lock:
                total_reads[0] += local_reads

        # Launch readers and writers
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=num_readers + num_writers
        ) as executor:
            reader_futures = [executor.submit(reader_task) for _ in range(num_readers)]
            writer_futures = [executor.submit(writer_task, w) for w in range(num_writers)]

            # Wait for writers to complete
            concurrent.futures.wait(writer_futures, timeout=10.0)
            stop_event.set()
            concurrent.futures.wait(reader_futures, timeout=5.0)

        self.assertEqual(corruptions[0], 0, "Encountered write failures during concurrent stress")
        self.assertEqual(
            torn_reads[0], 0, "Encountered torn/corrupted reads during concurrent stress"
        )
        self.assertGreater(total_reads[0], 1000, "Expected significant read throughput under load")
        self.assertEqual(self.shm.sequence % 2, 0, "Seqlock counter must be even after all writes")
        self.assertEqual(
            self.shm.active_count, num_writers, "Active count must match distinct accounts"
        )

    def test_shm_concurrent_hash_collision_churn(self) -> None:
        """Adversarial stress: Concurrent updates on accounts with colliding hash slots."""
        # Find two accounts that map to the identical base slot index
        base_h = _account_hash("account_alpha") % SLOT_COUNT
        colliding_account = None
        for i in range(1, 100_000):
            cand = f"col_cand_{i}"
            if _account_hash(cand) % SLOT_COUNT == base_h:
                colliding_account = cand
                break

        self.assertIsNotNone(colliding_account, "Could not find synthetic hash collision")
        acc1 = "account_alpha"
        acc2 = colliding_account

        stop_event = threading.Event()
        mismatches = [0]
        counter_lock = threading.Lock()

        def writer1():
            for i in range(400):
                now = time.time()
                code = f"1{i % 100000:05d}"
                self.shm.write_slot(acc1, code, now + 60, now + 60)
                time.sleep(0.0001)

        def writer2():
            for i in range(400):
                now = time.time()
                code = f"2{i % 100000:05d}"
                self.shm.write_slot(acc2, code, now + 60, now + 60)
                time.sleep(0.0001)

        def reader():
            while not stop_event.is_set():
                r1 = self.shm.read_slot(acc1)
                r2 = self.shm.read_slot(acc2)
                if r1 is not None:
                    code1 = r1.get("code", "")
                    if not code1.startswith("1"):
                        with counter_lock:
                            mismatches[0] += 1
                if r2 is not None:
                    code2 = r2.get("code", "")
                    if not code2.startswith("2"):
                        with counter_lock:
                            mismatches[0] += 1

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            rf = executor.submit(reader)
            w1 = executor.submit(writer1)
            w2 = executor.submit(writer2)
            concurrent.futures.wait([w1, w2], timeout=10.0)
            stop_event.set()
            concurrent.futures.wait([rf], timeout=5.0)

        self.assertEqual(mismatches[0], 0, "Hash collision probing leaked data between accounts")
        self.assertEqual(self.shm.active_count, 2)

    def test_shm_multiprocess_readers_writers(self) -> None:
        """Adversarial stress: Independent child processes concurrently reading/writing."""
        ctx = multiprocessing.get_context("spawn")
        done_q1 = ctx.Queue()
        done_q2 = ctx.Queue()
        account = "mp_user@system.test"

        # Initialize slot
        now = time.time()
        self.shm.write_slot(account, "000000", now + 60, now + 60)

        p_writer = ctx.Process(
            target=_mp_writer_worker, args=(self.shm_name, account, 300, done_q1)
        )
        p_reader = ctx.Process(
            target=_mp_reader_worker, args=(self.shm_name, account, 600, done_q2)
        )

        p_writer.start()
        p_reader.start()

        p_writer.join(timeout=10.0)
        p_reader.join(timeout=10.0)

        self.assertFalse(p_writer.is_alive(), "Writer process deadlocked")
        self.assertFalse(p_reader.is_alive(), "Reader process deadlocked")

        w_res = done_q1.get(timeout=2.0)
        r_res = done_q2.get(timeout=2.0)

        self.assertTrue(w_res[0], f"Writer process failed: {w_res[1]}")
        self.assertTrue(r_res[0], f"Reader process failed: {r_res}")
        self.assertEqual(r_res[2], 0, f"Reader detected {r_res[2]} corruptions")

    def test_shm_lock_timeout_and_contention_resilience(self) -> None:
        """Verify acquire_lock respects timeout boundaries without deadlocking."""
        t1_held = threading.Event()
        t1_release = threading.Event()
        t2_timed_out = threading.Event()
        t2_eventual_success = threading.Event()

        def holder_thread():
            got = self.shm.acquire_lock(timeout=1.0)
            if got:
                t1_held.set()
                t1_release.wait(timeout=3.0)
                self.shm.release_lock()

        def contender_thread():
            t1_held.wait(timeout=2.0)
            # Try acquire with small timeout - must fail
            got1 = self.shm.acquire_lock(timeout=0.05)
            if not got1:
                t2_timed_out.set()
            # Signal holder to release
            t1_release.set()
            # Try acquire again with adequate timeout - must succeed
            got2 = self.shm.acquire_lock(timeout=1.0)
            if got2:
                t2_eventual_success.set()
                self.shm.release_lock()

        t1 = threading.Thread(target=holder_thread)
        t2 = threading.Thread(target=contender_thread)

        t1.start()
        t2.start()

        t1.join(timeout=4.0)
        t2.join(timeout=4.0)

        self.assertTrue(t2_timed_out.is_set(), "Contender did not time out when lock was held")
        self.assertTrue(
            t2_eventual_success.is_set(), "Contender failed to acquire lock after release"
        )


# --------------------------------------------------------------------------
# Suite 2: Daemon Unix IPC Concurrency & Framing Robustness
# --------------------------------------------------------------------------


class TestDaemonIpcConcurrencyAndStress(unittest.TestCase):
    """Adversarial stress testing of resident daemon UNIX domain socket and IPC."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="test_adv_daemon_")
        self.env = {
            "HOME": self.temp_dir,
            "XDG_RUNTIME_DIR": os.path.join(self.temp_dir, "run"),
        }
        os.makedirs(self.env["XDG_RUNTIME_DIR"], mode=0o700, exist_ok=True)
        self.sock_path = socket_path(self.env)
        self.pid_path = pid_path(self.env)
        self.shm_name = f"test-adv-ipc-shm-{os.getpid()}-{time.time_ns() % 1000000}"

        self.server = DaemonServer(
            sock_path=self.sock_path,
            pid_file=self.pid_path,
            shm_name=self.shm_name,
            env=self.env,
        )
        self.server_thread = threading.Thread(target=self.server.start, daemon=True)
        self.server_thread.start()

        # Wait for daemon socket to be ready
        for _ in range(50):
            if self.sock_path.exists():
                break
            time.sleep(0.05)
        self.assertTrue(self.sock_path.exists(), "Daemon socket failed to bind")

    def tearDown(self) -> None:
        self.server._running = False
        self.server_thread.join(timeout=2.0)
        self.server.cleanup()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_daemon_high_throughput_concurrent_requests(self) -> None:
        """Adversarial stress: 16 concurrent workers issuing 400 mixed IPC requests."""
        num_workers = 16
        requests_per_worker = 25
        secret = "JBSWY3DPEHPK3PXP"

        # Pre-cache an account
        resp_cache = send_ipc_request(
            {"action": "cache_token", "account": "stress@test.com", "secret": secret},
            sock_path=self.sock_path,
            timeout=2.0,
        )
        self.assertEqual(resp_cache.get("status"), "ok")

        def worker_task(worker_id: int):
            results = []
            for i in range(requests_per_worker):
                action_idx = (worker_id + i) % 4
                if action_idx == 0:
                    req = {"action": "ping", "seq": i}
                elif action_idx == 1:
                    req = {"action": "status"}
                elif action_idx == 2:
                    req = {"action": "get_totp", "account": "stress@test.com"}
                else:
                    req = {"action": "list_tokens"}

                resp = send_ipc_request(req, sock_path=self.sock_path, timeout=3.0)
                results.append(resp is not None and resp.get("status") == "ok")
            return results

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker_task, w) for w in range(num_workers)]
            all_results = []
            for f in futures:
                all_results.extend(f.result())

        self.assertEqual(len(all_results), num_workers * requests_per_worker)
        self.assertTrue(
            all(all_results), "Encountered IPC failures under high-throughput concurrency"
        )

    def test_daemon_concurrency_barrier_burst_storm(self) -> None:
        """Adversarial stress: 40 threads connecting at the exact same millisecond."""
        burst_size = 40
        barrier = threading.Barrier(burst_size)

        def burst_client():
            barrier.wait(timeout=5.0)
            t0 = time.perf_counter()
            resp = send_ipc_request({"action": "ping"}, sock_path=self.sock_path, timeout=3.0)
            elapsed = time.perf_counter() - t0
            return resp, elapsed

        with concurrent.futures.ThreadPoolExecutor(max_workers=burst_size) as executor:
            futures = [executor.submit(burst_client) for _ in range(burst_size)]
            responses = [f.result() for f in futures]

        for resp, elapsed in responses:
            self.assertIsNotNone(resp, "Client timed out or received None during burst storm")
            self.assertEqual(resp.get("status"), "ok")
            self.assertLess(elapsed, 2.0, f"Client latency {elapsed:.3f}s exceeded burst SLA")

    def test_daemon_slow_client_resilience(self) -> None:
        """Adversarial attack: Slow client holds connection while fast clients query."""
        slow_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        slow_sock.connect(str(self.sock_path))

        try:
            # Concurrently launch 10 fast queries while slow_sock is open without transmitting
            fast_count = 10
            t0 = time.perf_counter()

            def fast_client():
                return send_ipc_request({"action": "status"}, sock_path=self.sock_path, timeout=1.0)

            with concurrent.futures.ThreadPoolExecutor(max_workers=fast_count) as executor:
                futures = [executor.submit(fast_client) for _ in range(fast_count)]
                results = [f.result() for f in futures]

            total_elapsed = time.perf_counter() - t0

            for res in results:
                self.assertIsNotNone(res)
                self.assertEqual(res.get("status"), "ok")

            # Must finish well under 0.3s proving no head-of-line blocking behind slow connection
            self.assertLess(
                total_elapsed, 0.3, f"Fast clients took {total_elapsed:.3f}s; head-of-line blocked"
            )
        finally:
            slow_sock.close()

    def test_daemon_oversized_payload_rejection(self) -> None:
        """Adversarial attack: Client transmits length header exceeding MAX_IPC_MESSAGE_SIZE."""
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(self.sock_path))
        try:
            # Declare length of 128 KiB (MAX is 64 KiB)
            client.sendall(struct.pack(">I", MAX_IPC_MESSAGE_SIZE + 1000))
            # Server must detect oversized message, emit framed error payload, and close connection
            resp = recv_framed_message(client)
            self.assertIsNotNone(resp)
            self.assertEqual(resp.get("status"), "error")
            self.assertIn("Invalid message length", resp.get("message", ""))
            # Subsequent recv must return EOF (b"")
            chunk = client.recv(1024)
            self.assertEqual(
                chunk, b"", "Server did not close connection after oversized payload error"
            )
        finally:
            client.close()

        # Confirm daemon remains responsive after attack
        post_resp = send_ipc_request({"action": "ping"}, sock_path=self.sock_path, timeout=1.0)
        self.assertIsNotNone(post_resp)
        self.assertEqual(post_resp.get("status"), "ok")

    def test_daemon_truncated_framing_rejection(self) -> None:
        """Adversarial attack: Client transmits partial header and abruptly terminates."""
        # 1. Partial 2-byte header
        c1 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c1.connect(str(self.sock_path))
        c1.sendall(b"\x00\x00")
        c1.close()

        # 2. 4-byte header claiming 100 bytes, sending only 10 bytes then closing
        c2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c2.connect(str(self.sock_path))
        c2.sendall(struct.pack(">I", 100) + b"\x01\x02\x03\x04\x05")
        c2.close()

        # 3. Confirm daemon is healthy and unblocked
        resp = send_ipc_request({"action": "ping"}, sock_path=self.sock_path, timeout=1.0)
        self.assertIsNotNone(resp)
        self.assertEqual(resp.get("status"), "ok")


# --------------------------------------------------------------------------
# Suite 3: Clean-Room Wheel Smoke Packaging
# --------------------------------------------------------------------------


class TestCleanRoomWheelSmokePackaging(unittest.TestCase):
    """Empirical adversarial verification of clean-room wheel installation and entrypoints."""

    def test_clean_room_wheel_installation_and_entrypoints(self) -> None:
        """Verify wheel installs cleanly in isolated venv and all entrypoints execute."""
        scratch_base = Path("/tmp/Authy-to-1Password_Local")
        scratch_base.mkdir(exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="challenger-smoke-", dir=scratch_base) as tmp_dir:
            temp_home = Path(tmp_dir)
            venv_dir = temp_home / "isolated_venv"
            venv.create(venv_dir, with_pip=True)

            wheels = sorted((ROOT / "dist").glob("authy_local-*.whl"))
            self.assertEqual(
                len(wheels),
                1,
                f"Expected exactly 1 current wheel in dist/, found: {wheels}",
            )
            target_wheel = wheels[0]
            wheelhouse = ROOT / "dist/wheels"
            self.assertTrue(
                wheelhouse.is_dir(), f"Wheelhouse directory {wheelhouse} does not exist"
            )

            python_bin = venv_dir / "bin/python"
            pip_args = [
                str(python_bin),
                "-m",
                "pip",
                "install",
                "--no-cache-dir",
                "--no-index",
                "--find-links",
                str(wheelhouse),
                str(target_wheel),
            ]
            env = {
                "HOME": str(temp_home),
                "PATH": "",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            }

            install_run = subprocess.run(
                pip_args,
                cwd=temp_home,
                env=env,
                capture_output=True,
                text=True,
                timeout=45,
            )
            self.assertEqual(
                install_run.returncode,
                0,
                f"Wheel installation failed: stdout={install_run.stdout}, stderr={install_run.stderr}",
            )

            otp_local_bin = venv_dir / "bin/otp-local"
            self.assertTrue(otp_local_bin.exists(), "otp-local entrypoint was not installed")

            # 1. Test --version
            v_run = subprocess.run(
                [str(otp_local_bin), "--version"],
                cwd=temp_home,
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(v_run.returncode, 0)
            self.assertIn("2.0.1", v_run.stdout)

            # 2. Test --help
            h_run = subprocess.run(
                [str(otp_local_bin), "--help"],
                cwd=temp_home,
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(h_run.returncode, 0)
            self.assertIn("usage: otp-local", h_run.stdout)

            # 3. Test doctor
            doc_run = subprocess.run(
                [str(otp_local_bin), "doctor"],
                cwd=temp_home,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertIn(doc_run.returncode, (0, 3), "Doctor returned unexpected exit code")
            self.assertIn("platform: available", doc_run.stdout)
            self.assertIn("python: available", doc_run.stdout)

            # 4. Test doctor --json
            doc_json = subprocess.run(
                [str(otp_local_bin), "doctor", "--json"],
                cwd=temp_home,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertIn(doc_json.returncode, (0, 3))
            parsed = json.loads(doc_json.stdout)
            self.assertIn("platform", parsed)
            self.assertIn("python", parsed)

            # 5. Test subcommands --help
            for subcmd in ("daemon", "list", "search", "tui", "enroll"):
                sub_run = subprocess.run(
                    [str(otp_local_bin), subcmd, "--help"],
                    cwd=temp_home,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                self.assertEqual(
                    sub_run.returncode,
                    0,
                    f"Subcommand {subcmd} --help failed: {sub_run.stderr}",
                )

            # 6. Verify clean-room import of modules without developer repo in sys.path
            import_script = (
                "from authy_local import cli, daemon, ipc, shm, tui, doctor, federation; "
                "import textual, fido2, pluggy; print('CLEAN_IMPORT_OK')"
            )
            imp_run = subprocess.run(
                [str(python_bin), "-I", "-B", "-c", import_script],
                cwd=temp_home,
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(imp_run.returncode, 0)
            self.assertIn("CLEAN_IMPORT_OK", imp_run.stdout)


# --------------------------------------------------------------------------
# Suite 4: Opaque-Box E2E Pipeline Integration
# --------------------------------------------------------------------------


class TestE2EOpaqueBoxPipelineIntegration(unittest.TestCase):
    """Empirical verification of opaque-box E2E tiers 1 through 4."""

    def test_e2e_all_tiers_pass_cleanly(self) -> None:
        """Run all 4 tiers of E2E tests and assert 100% green exit code 0."""
        e2e_files = [
            "tests/e2e/test_e2e_tier1.py",
            "tests/e2e/test_e2e_tier2.py",
            "tests/e2e/test_e2e_tier3.py",
            "tests/e2e/test_e2e_tier4.py",
        ]
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            *e2e_files,
            "-q",
        ]
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{ROOT / 'src'}:{ROOT / 'tests'}"

        res = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            res.returncode,
            0,
            f"E2E test suite failed:\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}",
        )
        self.assertIn("passed", res.stdout)


if __name__ == "__main__":
    unittest.main()
