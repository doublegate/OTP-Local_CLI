"""Adversarial stress test suite for Milestone M3 concurrency, locking, and synchronization.

Tests:
1. POSIX SHM Seqlock Torn Reads: High-concurrency writer/reader threads and processes
   verifying zero torn reads and strict payload invariant integrity.
2. POSIX SHM Collision & Capacity: Linear collision probing across 16 slots, ring buffer
   wrap-around, expired slot replacement, and bounded capacity.
3. Daemon Concurrent Request Burst: 50 concurrent clients over Unix domain socket with
   slow clients holding connections, verifying zero head-of-line blocking and no deadlocks.
4. PAM C JSON Escaping: Adversarial input strings containing quotes, backslashes, control
   characters, Unicode multi-byte sequences, JSON injections, and buffer overflow bounds.
"""

import concurrent.futures
import ctypes
import ctypes.util
import multiprocessing
import os
import shutil
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from authy_local.daemon import DaemonServer
from authy_local.enrollment import generate_totp_code, parse_secret_or_uri
from authy_local.ipc import (
    recv_framed_message,
    send_framed_message,
    send_ipc_request,
)
from authy_local.shm import (
    HEADER_SIZE,
    MAX_PROBE,
    SLOT_COUNT,
    SLOT_SIZE,
    ShmRingBuffer,
    _account_hash,
)

PAM_SUCCESS = 0
PAM_AUTH_ERR = 7
PAM_USER_UNKNOWN = 10


# Multiprocessing helper functions defined at top-level for spawn/fork compatibility
def _mp_writer_worker(shm_name: str, account: str, stop_ev, writes_counter, base_time: float):
    w_shm = ShmRingBuffer(name=shm_name, create=False)
    epoch = 0
    while not stop_ev.is_set():
        epoch += 1
        code = f"{(epoch % 1000000):06d}"
        period = (epoch % 50) + 1
        valid_until = base_time + 10000.0 + epoch
        w_shm.write_slot(
            account=account,
            code=code,
            expiry=valid_until,
            valid_until=valid_until,
            epoch=epoch,
            digits=6,
            period=period,
        )
    with writes_counter.get_lock():
        writes_counter.value += epoch
    w_shm.close()


def _mp_reader_worker(
    shm_name: str,
    accounts: list[str],
    num_reads: int,
    torn_counter,
    successful_reads,
    base_time: float,
):
    r_shm = ShmRingBuffer(name=shm_name, create=False)
    succ = 0
    torn = 0
    for i in range(num_reads):
        acct = accounts[i % len(accounts)]
        res = r_shm.read_slot(acct)
        if res is not None:
            succ += 1
            c = int(res["code"])
            ep = res["epoch"]
            pr = res["period"]
            vu = res["valid_until"]
            if c != ep % 1000000 or pr != (ep % 50) + 1 or vu != base_time + 10000.0 + ep:
                torn += 1
    r_shm.close()
    with torn_counter.get_lock():
        torn_counter.value += torn
    with successful_reads.get_lock():
        successful_reads.value += succ


class PamMessage(ctypes.Structure):
    _fields_ = [("msg_style", ctypes.c_int), ("msg", ctypes.c_char_p)]


class PamResponse(ctypes.Structure):
    _fields_ = [("resp", ctypes.c_void_p), ("resp_retcode", ctypes.c_int)]


PAM_CONV_FUNC = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(ctypes.POINTER(PamMessage)),
    ctypes.POINTER(ctypes.POINTER(PamResponse)),
    ctypes.c_void_p,
)


class PamConv(ctypes.Structure):
    _fields_ = [("conv", PAM_CONV_FUNC), ("appdata_ptr", ctypes.c_void_p)]


class TestShmSeqlockTornReadStress(unittest.TestCase):
    """Adversarial stress testing for POSIX SHM Seqlock synchronization."""

    def setUp(self) -> None:
        self.shm_name = f"test-adv-shm-{os.getpid()}-{time.time_ns() % 1000000}"
        self.shm = ShmRingBuffer(name=self.shm_name, create=True)

    def tearDown(self) -> None:
        if self.shm is not None:
            self.shm.unlink()

    def test_seqlock_multi_threaded_torn_read_stress(self) -> None:
        """Verify 0 torn reads occur across 80,000 rapid concurrent reads during active writes."""
        stop_event = threading.Event()
        ready_event = threading.Event()
        writes_done = [0]
        successful_reads = [0]
        torn_reads = [0]
        base_time = time.time()

        def writer_loop():
            epoch = 0
            while not stop_event.is_set():
                epoch += 1
                code = f"{(epoch % 1000000):06d}"
                period = (epoch % 50) + 1
                valid_until = base_time + 10000.0 + epoch
                self.shm.write_slot(
                    account="victim_thread_acct",
                    code=code,
                    expiry=valid_until,
                    valid_until=valid_until,
                    epoch=epoch,
                    digits=6,
                    period=period,
                )
                writes_done[0] += 1
                if epoch >= 50 and not ready_event.is_set():
                    ready_event.set()

        def reader_loop():
            reader_shm = ShmRingBuffer(name=self.shm_name, create=False)
            for idx in range(10000):
                if idx % 250 == 0:
                    time.sleep(0)
                res = reader_shm.read_slot("victim_thread_acct")
                if res is not None:
                    successful_reads[0] += 1
                    c = int(res["code"])
                    ep = res["epoch"]
                    pr = res["period"]
                    vu = res["valid_until"]
                    # Assert atomic payload integrity invariant
                    if c != ep % 1000000 or pr != (ep % 50) + 1 or vu != base_time + 10000.0 + ep:
                        torn_reads[0] += 1
            reader_shm.close()

        w_thread = threading.Thread(target=writer_loop)
        w_thread.start()
        ready_event.wait(timeout=5.0)

        readers = [threading.Thread(target=reader_loop) for _ in range(8)]
        for t in readers:
            t.start()
        for t in readers:
            t.join()

        stop_event.set()
        w_thread.join()

        self.assertGreater(writes_done[0], 100, "Writer loop failed to perform writes")
        self.assertGreater(successful_reads[0], 50000, "Insufficient successful reads")
        self.assertEqual(torn_reads[0], 0, "Torn read detected in multi-threaded seqlock test!")

    def test_seqlock_multi_process_torn_read_stress(self) -> None:
        """Verify 0 torn reads occur with isolated writer and reader OS processes."""
        try:
            multiprocessing.set_start_method("fork")
        except RuntimeError:
            pass

        stop_ev = multiprocessing.Event()
        writes_counter = multiprocessing.Value("i", 0)
        torn_counter = multiprocessing.Value("i", 0)
        successful_reads = multiprocessing.Value("i", 0)
        base_time = time.time()
        accounts = ["mp_acct_1", "mp_acct_2"]

        # 2 writer processes
        writers = [
            multiprocessing.Process(
                target=_mp_writer_worker,
                args=(self.shm_name, acct, stop_ev, writes_counter, base_time),
            )
            for acct in accounts
        ]
        for p in writers:
            p.start()

        # 4 reader processes (5,000 queries each = 20,000 queries)
        readers = [
            multiprocessing.Process(
                target=_mp_reader_worker,
                args=(self.shm_name, accounts, 5000, torn_counter, successful_reads, base_time),
            )
            for _ in range(4)
        ]
        for p in readers:
            p.start()
        for p in readers:
            p.join()

        stop_ev.set()
        for p in writers:
            p.join()

        self.assertGreater(writes_counter.value, 1000, "Multi-process writers did not run")
        self.assertGreater(
            successful_reads.value, 10000, "Multi-process readers failed to retrieve slots"
        )
        self.assertEqual(torn_counter.value, 0, "Torn read detected in multi-process seqlock test!")


class TestShmCollisionAndCapacityStress(unittest.TestCase):
    """Adversarial stress testing for 16-slot linear collision probing and capacity limits."""

    def setUp(self) -> None:
        self.shm_name = f"test-adv-coll-{os.getpid()}-{time.time_ns() % 1000000}"
        self.shm = ShmRingBuffer(name=self.shm_name, create=True)

    def tearDown(self) -> None:
        if self.shm is not None:
            self.shm.unlink()

    def test_linear_collision_probing_16_slots(self) -> None:
        """Verify 16 colliding hashes fill probe chain and all are independently retrieved."""
        target_slot = 42
        colliding = []
        i = 0
        while len(colliding) < 20:
            acct = f"user_probe_{i}"
            if _account_hash(acct) % SLOT_COUNT == target_slot:
                colliding.append(acct)
            i += 1

        now = time.time()
        # Insert 16 colliding accounts
        for idx, acct in enumerate(colliding[:16]):
            wrote = self.shm.write_slot(acct, f"{idx:06d}", now + 120, now + 120)
            self.assertTrue(wrote)

        self.assertEqual(self.shm.active_count, 16)

        # Verify exact slot placement across (target_slot + probe) % SLOT_COUNT
        for p in range(MAX_PROBE):
            slot_idx = (target_slot + p) % SLOT_COUNT
            offset = HEADER_SIZE + slot_idx * SLOT_SIZE
            slot_h, _, _ = struct.unpack_from(">Qdd", self.shm.buf, offset)
            self.assertEqual(
                slot_h,
                _account_hash(colliding[p]),
                f"Probe offset {p} does not hold account {colliding[p]}",
            )

        # Verify all 16 accounts can be read back cleanly
        for idx, acct in enumerate(colliding[:16]):
            res = self.shm.read_slot(acct)
            self.assertIsNotNone(res, f"Failed to read colliding account {acct}")
            self.assertEqual(res["code"], f"{idx:06d}")

    def test_expired_slot_replacement_under_collision(self) -> None:
        """Verify that expired slots in collision chain are replaced without evicting active slots."""
        target_slot = 77
        colliding = []
        i = 0
        while len(colliding) < 20:
            acct = f"user_exp_{i}"
            if _account_hash(acct) % SLOT_COUNT == target_slot:
                colliding.append(acct)
            i += 1

        now = time.time()
        # Fill 16 slots
        for idx, acct in enumerate(colliding[:16]):
            self.shm.write_slot(acct, f"{idx:06d}", now + 60, now + 60)

        # Artificially expire 4 slots (probe positions 2, 5, 8, 11)
        expired_indices = [2, 5, 8, 11]
        for idx in expired_indices:
            self.shm.write_slot(colliding[idx], "EXPD00", now - 10, now - 10)

        # Insert 4 new colliding accounts (items 16..19)
        for idx, acct in enumerate(colliding[16:20]):
            wrote = self.shm.write_slot(acct, f"NEW{idx:03d}", now + 60, now + 60)
            self.assertTrue(wrote)

        # Verify the 4 new accounts are readable
        for idx, acct in enumerate(colliding[16:20]):
            res = self.shm.read_slot(acct)
            self.assertIsNotNone(res, f"Failed to read newly inserted account {acct}")
            self.assertEqual(res["code"], f"NEW{idx:03d}")

        # Verify the 12 non-expired accounts remain intact and unevicted
        surviving_indices = [j for j in range(16) if j not in expired_indices]
        for idx in surviving_indices:
            acct = colliding[idx]
            res = self.shm.read_slot(acct)
            self.assertIsNotNone(res, f"Non-expired account {acct} was erroneously evicted!")
            self.assertEqual(res["code"], f"{idx:06d}")

    def test_collision_probing_wrap_around_boundary(self) -> None:
        """Verify linear collision probing wraps around the end of the ring buffer (slot 1022 -> 0)."""
        wrap_slot = SLOT_COUNT - 2  # slot 1021
        colliding_wrap = []
        i = 0
        while len(colliding_wrap) < 16:
            acct = f"user_wrap_{i}"
            if _account_hash(acct) % SLOT_COUNT == wrap_slot:
                colliding_wrap.append(acct)
            i += 1

        now = time.time()
        for idx, acct in enumerate(colliding_wrap):
            wrote = self.shm.write_slot(acct, f"W{idx:05d}", now + 120, now + 120)
            self.assertTrue(wrote)

        # Verify probing wrapped past slot 1022 into slots 0, 1, 2...
        # Slots should be 1021, 1022, 0, 1, 2, ...
        for p in range(16):
            expected_idx = (wrap_slot + p) % SLOT_COUNT
            offset = HEADER_SIZE + expected_idx * SLOT_SIZE
            slot_h, _, _ = struct.unpack_from(">Qdd", self.shm.buf, offset)
            self.assertEqual(slot_h, _account_hash(colliding_wrap[p]))

        # Verify all accounts readable across boundary
        for idx, acct in enumerate(colliding_wrap):
            res = self.shm.read_slot(acct)
            self.assertIsNotNone(res)
            self.assertEqual(res["code"], f"W{idx:05d}")


class TestDaemonConcurrentBurstStress(unittest.TestCase):
    """Adversarial stress testing for resident daemon IPC concurrency and burst handling."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="test_adv_daemon_")
        self.sock_path = Path(self.tmp_dir) / "burst.sock"
        self.pid_path = Path(self.tmp_dir) / "burst.pid"
        self.shm_name = f"test-adv-burst-{os.getpid()}-{time.time_ns() % 1000000}"
        self.server = DaemonServer(
            sock_path=self.sock_path,
            shm_name=self.shm_name,
            pid_file=self.pid_path,
        )
        self.server_thread = threading.Thread(target=self.server.start, daemon=True)
        self.server_thread.start()

        for _ in range(50):
            if self.sock_path.exists():
                break
            time.sleep(0.05)

    def tearDown(self) -> None:
        self.server._running = False
        self.server_thread.join(timeout=2.0)
        self.server.cleanup()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_burst_concurrency_zero_head_of_line_blocking(self) -> None:
        """Verify 5 slow clients holding connections do not block 45 concurrent fast clients."""
        fast_latencies: list[float] = []
        slow_latencies: list[float] = []
        errors: list[str] = []

        def slow_client_worker(i: int):
            try:
                t0 = time.perf_counter()
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(str(self.sock_path))
                # Sleep to hold connection and worker thread
                time.sleep(0.20)
                send_framed_message(sock, {"action": "ping", "client": f"slow_{i}"})
                resp = recv_framed_message(sock)
                elapsed = time.perf_counter() - t0
                slow_latencies.append(elapsed)
                sock.close()
                if not resp or resp.get("status") != "ok":
                    errors.append(f"Slow client {i} failed: {resp}")
            except Exception as exc:
                errors.append(f"Slow client {i} exception: {exc}")

        def fast_client_worker(i: int):
            try:
                t0 = time.perf_counter()
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(str(self.sock_path))
                send_framed_message(sock, {"action": "ping", "client": f"fast_{i}"})
                resp = recv_framed_message(sock)
                elapsed = time.perf_counter() - t0
                fast_latencies.append(elapsed)
                sock.close()
                if not resp or resp.get("status") != "ok":
                    errors.append(f"Fast client {i} failed: {resp}")
            except Exception as exc:
                errors.append(f"Fast client {i} exception: {exc}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
            # Submit 5 slow clients first
            slow_futures = [ex.submit(slow_client_worker, i) for i in range(5)]
            # Concurrently submit 45 fast clients
            fast_futures = [ex.submit(fast_client_worker, i) for i in range(45)]

            for f in slow_futures + fast_futures:
                f.result()

        self.assertEqual(len(errors), 0, f"Encountered client errors: {errors}")
        self.assertEqual(len(fast_latencies), 45)
        self.assertEqual(len(slow_latencies), 5)

        avg_fast = sum(fast_latencies) / len(fast_latencies)
        is_tracing = (
            sys.gettrace() is not None
            or "coverage" in sys.modules
            or (
                hasattr(sys, "monitoring")
                and sys.monitoring.get_tool(getattr(sys.monitoring, "COVERAGE_ID", 1)) is not None
            )
        )
        latency_sla = 0.250 if is_tracing else 0.100
        # Fast clients should complete in SLA on average despite slow clients
        self.assertLess(
            avg_fast,
            latency_sla,
            f"Fast clients average latency {avg_fast * 1000:.2f}ms indicates head-of-line blocking!",
        )

    def test_burst_50_concurrent_mixed_operations(self) -> None:
        """Verify 50 concurrent requests across cache, get, verify, list, and ping execute cleanly."""
        secret = "JBSWY3DPEHPK3PXP"
        send_ipc_request(
            {"action": "cache_token", "account": "base_user", "secret": secret},
            sock_path=self.sock_path,
        )

        def worker(i: int):
            op = i % 5
            if op == 0:
                res = send_ipc_request(
                    {
                        "action": "cache_token",
                        "account": f"burst_user_{i}",
                        "secret": secret,
                    },
                    sock_path=self.sock_path,
                )
                return res and res.get("status") == "ok"
            elif op == 1:
                res = send_ipc_request(
                    {"action": "get_totp", "account": "base_user"},
                    sock_path=self.sock_path,
                )
                return res and res.get("status") == "ok" and len(res.get("code", "")) == 6
            elif op == 2:
                res = send_ipc_request(
                    {
                        "action": "verify_totp",
                        "account": "base_user",
                        "code": "000000",
                    },
                    sock_path=self.sock_path,
                )
                return res and res.get("status") == "ok"
            elif op == 3:
                res = send_ipc_request({"action": "list_tokens"}, sock_path=self.sock_path)
                return res and res.get("status") == "ok" and isinstance(res.get("accounts"), list)
            elif op == 4:
                res = send_ipc_request({"action": "ping"}, sock_path=self.sock_path)
                return res and res.get("status") == "ok"
            return False

        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
            futures = [ex.submit(worker, i) for i in range(50)]
            results = [f.result() for f in futures]
        elapsed = time.perf_counter() - t0

        self.assertEqual(len(results), 50)
        self.assertTrue(all(results), "One or more concurrent mixed requests failed")
        # 50 requests should complete in well under 1.0s
        self.assertLess(elapsed, 1.0, f"50 mixed burst requests took {elapsed:.3f}s")


class TestPamJsonEscapingAdversarial(unittest.TestCase):
    """Adversarial testing for PAM C module RFC 8259 JSON escaping and injection defense."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pam_so_path = Path(__file__).resolve().parents[1] / "pam" / "pam_otp_local.so"
        if not cls.pam_so_path.exists():
            raise unittest.SkipTest(f"pam_otp_local.so binary not found at {cls.pam_so_path}")

        libpam_name = ctypes.util.find_library("pam")
        if not libpam_name:
            raise unittest.SkipTest("libpam.so is not available")
        cls.libpam = ctypes.CDLL(libpam_name)

        libc_name = ctypes.util.find_library("c")
        if not libc_name:
            raise unittest.SkipTest("libc is not available")
        cls.libc = ctypes.CDLL(libc_name)
        cls.libc.strdup.restype = ctypes.c_void_p
        cls.libc.strdup.argtypes = [ctypes.c_char_p]
        cls.libc.malloc.restype = ctypes.c_void_p
        cls.libc.malloc.argtypes = [ctypes.c_size_t]

        cls.pam_mod = ctypes.CDLL(str(cls.pam_so_path))

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="test_adv_pam_")
        self.sock_path = Path(self.tmp_dir) / "pam.sock"
        self.pid_path = Path(self.tmp_dir) / "pam.pid"
        self.shm_name = f"test-adv-pam-{os.getpid()}-{time.time_ns() % 1000000}"
        self.server = DaemonServer(
            sock_path=self.sock_path,
            shm_name=self.shm_name,
            pid_file=self.pid_path,
        )
        self.server_thread = threading.Thread(target=self.server.start, daemon=True)
        self.server_thread.start()

        for _ in range(50):
            if self.sock_path.exists():
                break
            time.sleep(0.05)

    def tearDown(self) -> None:
        self.server._running = False
        self.server_thread.join(timeout=2.0)
        self.server.cleanup()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_pam_conv(self, c_code: str) -> PamConv:
        @PAM_CONV_FUNC
        def conv_fn(num_msg, msg, resp_out, appdata):
            resp_ptr = self.libc.malloc(ctypes.sizeof(PamResponse) * num_msg)
            p_resp = ctypes.cast(resp_ptr, ctypes.POINTER(PamResponse))
            for i in range(num_msg):
                p_resp[i].resp = self.libc.strdup(c_code.encode("utf-8"))
                p_resp[i].resp_retcode = 0
            resp_out[0] = p_resp
            return 0

        return PamConv(conv=conv_fn, appdata_ptr=None)

    def test_pam_adversarial_escaping_matrix(self) -> None:
        """Verify comprehensive matrix of quotes, backslashes, controls, Unicode, injections."""
        secret = "JBSWY3DPEHPK3PXP"

        cases = [
            # Quotes
            ('alice"admin', True, "VALID", PAM_SUCCESS, "Double quote within username"),
            ('"leading_quote', True, "VALID", PAM_SUCCESS, "Leading double quote"),
            ('trailing_quote"', True, "VALID", PAM_SUCCESS, "Trailing double quote"),
            ('multi"""quotes', True, "VALID", PAM_SUCCESS, "Multiple consecutive quotes"),
            # Backslashes
            (r"DOMAIN\user", True, "VALID", PAM_SUCCESS, "ActiveDirectory single backslash"),
            (r"DOMAIN\\user", True, "VALID", PAM_SUCCESS, "Double backslash"),
            (r"C:\dir\file.txt", True, "VALID", PAM_SUCCESS, "Windows path backslashes"),
            # Control characters
            ("user\nname", True, "VALID", PAM_SUCCESS, "Newline control character"),
            ("user\rname", True, "VALID", PAM_SUCCESS, "Carriage return control character"),
            ("user\tname", True, "VALID", PAM_SUCCESS, "Tab control character"),
            ("user\b\fname", True, "VALID", PAM_SUCCESS, "Backspace and formfeed"),
            ("user\x01\x1f", True, "VALID", PAM_SUCCESS, "Low ASCII control codes"),
            # Unicode / multi-byte UTF-8
            ("Müller", True, "VALID", PAM_SUCCESS, "German umlaut"),
            ("山田太郎", True, "VALID", PAM_SUCCESS, "Japanese kanji"),
            ("user_🛡️_shield", True, "VALID", PAM_SUCCESS, "Emoji multi-byte sequence"),
            # JSON Injection Attacks (uncached)
            (
                'admin","valid":true,"x":"',
                False,
                "123456",
                PAM_USER_UNKNOWN,
                "JSON injection field breakout",
            ),
            (
                'user"}\n{"injected":true',
                False,
                "123456",
                PAM_USER_UNKNOWN,
                "JSON injection bracket breakout",
            ),
            (
                'foo","status":"ok","valid":true,"bar":"',
                False,
                "123456",
                PAM_USER_UNKNOWN,
                "JSON status injection",
            ),
            # Wrong code for adversarial user
            ('alice"admin', False, "000000", PAM_AUTH_ERR, "Wrong code with special char user"),
            # Buffer overflow: 150 quotes (expands to 300 bytes in 256 byte esc_account buffer)
            ('"' * 150, False, "123456", PAM_AUTH_ERR, "150 quotes exceeding esc_account buffer"),
            # 300 characters
            (
                "A" * 300,
                False,
                "123456",
                PAM_AUTH_ERR,
                "300 char username exceeding esc_account buffer",
            ),
        ]

        for username, do_cache, code_choice, expected_rc, desc in cases:
            if do_cache:
                c_res = send_ipc_request(
                    {"action": "cache_token", "account": username, "secret": secret},
                    sock_path=self.sock_path,
                )
                self.assertIsNotNone(c_res)
                self.assertEqual(c_res.get("status"), "ok")

            if code_choice == "VALID":
                params = parse_secret_or_uri(secret, fallback_label=username)
                code_to_send, _ = generate_totp_code(params)
            else:
                code_to_send = code_choice

            pam_conv = self._create_pam_conv(code_to_send)
            pamh = ctypes.c_void_p()
            u_bytes = username.encode("utf-8", errors="replace")
            rc_start = self.libpam.pam_start(
                b"sudo", u_bytes, ctypes.byref(pam_conv), ctypes.byref(pamh)
            )
            self.assertEqual(rc_start, PAM_SUCCESS)

            args = (ctypes.c_char_p * 2)(
                f"socket_path={self.sock_path}".encode("utf-8"),
                b"debug",
            )
            rc_auth = self.pam_mod.pam_sm_authenticate(pamh, 0, 2, args)
            self.libpam.pam_end(pamh, rc_auth)

            self.assertEqual(
                rc_auth,
                expected_rc,
                f"Adversarial case '{desc}' failed: expected rc={expected_rc}, got {rc_auth}",
            )


if __name__ == "__main__":
    unittest.main()
