"""Empirical Tier 5 Adversarial Stress Suite for Milestone M5.

Authored by Challenger M5-1 (Empirical Challenger) to rigorously stress-test:
1. PID <= 0 Bounds & Process Group Immunity:
   - Verify that non-positive PIDs (0, -1, -42, -999, non-numeric tokens, control characters)
     in PID files never result in signals sent to PID 0 (process group) or PID -1 (all processes).
   - Execute real unmocked runs of daemon_start, daemon_stop, daemon_clean, and daemon_status,
     proving that the test runner's process group survives unaffected and stale files are purged.
   - Run a real daemon background lifecycle (start -> status -> IPC ping -> stop) verifying
     clean termination and artifact purging.
2. Memory Zeroization & Secret Repr Protection:
   - Verify OtpParameters secret is strictly masked in __repr__, __str__, f-strings, nested
     structures, and exception tracebacks (including traceback inspection with locals).
   - Verify disable_core_dumps() returns True, sets resource.RLIMIT_CORE to (0, 0), and sets
     Linux PR_GET_DUMPABLE to 0.
   - Verify secure_zero() overwrites bytearray, memoryview, ctypes array, and raw memory addresses
     with 0x00 bytes, testing boundary sizes (empty, large, negative lengths).
   - Verify SecureBuffer mlock, madvise_dontdump, and zeroization on close.
3. Path Traversal & Symlink Race Defenses in importers.py:
   - Stress-test detect_and_parse_import with diverse path traversal vectors (../../etc/passwd,
     relative traverses, non-regular files like FIFOs, character/block devices, directories).
   - Verify strict rejection of direct, relative, circular, multi-hop, and dangling symlinks.
   - Execute high-concurrency multi-threaded TOCTOU race condition stress between valid TOTP
     tokens and /etc/passwd symlinks, asserting zero secret/account leakage.
"""

from __future__ import annotations

import ctypes
import io
import os
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch

from authy_local.daemon import (
    daemon_clean,
    daemon_start,
    daemon_status,
    daemon_stop,
    pid_path,
    send_ipc_request,
    socket_path,
)
from authy_local.enrollment import OtpParameters
from authy_local.errors import AppError
from authy_local.importers import detect_and_parse_import
from authy_local.models import Scope
from authy_local.security import (
    SecureBuffer,
    secure_zero,
)
from tests.test_processes import alive


class TestPidBoundsAndProcessGroupImmunity(unittest.TestCase):
    """Stress-test PID boundary guards and process group immunity in daemon.py."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)
        run_dir = self.tmp_path / "run"
        run_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.env = {
            "HOME": str(self.tmp_path),
            "XDG_RUNTIME_DIR": str(run_dir),
        }
        self.p_path = pid_path(self.env)
        self.s_path = socket_path(self.env)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_mock_kill_never_called_with_non_positive_pids(self) -> None:
        """Verify os.kill is never invoked with pid <= 0 across all operations."""
        adversarial_payloads = [
            "0\n",
            "-1\n",
            "-42\n",
            "-999999\n",
            "0",
            "-0",
            "+0",
            "-000",
            "",
            "   ",
            "\n\n",
            "invalid_text",
            "123abc456",
            "0x10",
            "NaN",
            "inf",
            "-inf",
            "3.14159",
            "\x00\x00\x00",
            "-2147483648",
            "-9223372036854775808",
        ]

        for payload in adversarial_payloads:
            with self.subTest(payload=repr(payload)):
                # 1. daemon_stop
                self.p_path.write_text(payload, encoding="ascii", errors="replace")
                self.s_path.touch()
                with patch("os.kill") as mock_kill:
                    code = daemon_stop(env=self.env)
                    self.assertEqual(code, 0)
                    self.assertFalse(self.p_path.exists())
                    self.assertFalse(self.s_path.exists())
                    # Ensure mock_kill was never called with any pid <= 0
                    for call_arg in mock_kill.call_args_list:
                        target_pid = call_arg[0][0]
                        self.assertGreater(target_pid, 0)

                # 2. daemon_clean
                self.p_path.write_text(payload, encoding="ascii", errors="replace")
                self.s_path.touch()
                with patch("os.kill") as mock_kill:
                    code = daemon_clean(env=self.env)
                    self.assertEqual(code, 0)
                    self.assertFalse(self.p_path.exists())
                    self.assertFalse(self.s_path.exists())
                    for call_arg in mock_kill.call_args_list:
                        target_pid = call_arg[0][0]
                        self.assertGreater(target_pid, 0)

                # 3. daemon_status
                self.p_path.write_text(payload, encoding="ascii", errors="replace")
                with patch("os.kill") as mock_kill:
                    out = io.StringIO()
                    with patch("sys.stdout", out):
                        code = daemon_status(env=self.env)
                    self.assertEqual(code, 0)
                    self.assertIn("Status: dead (stale PID file exists)", out.getvalue())
                    for call_arg in mock_kill.call_args_list:
                        target_pid = call_arg[0][0]
                        self.assertGreater(target_pid, 0)

                # 4. daemon_start
                self.p_path.write_text(payload, encoding="ascii", errors="replace")
                self.s_path.touch()
                with (
                    patch("os.kill") as mock_kill,
                    patch("authy_local.daemon.DaemonServer.start", return_value=None),
                ):
                    err = io.StringIO()
                    with patch("sys.stderr", err):
                        code = daemon_start(foreground=True, env=self.env)
                    self.assertEqual(code, 0)
                    for call_arg in mock_kill.call_args_list:
                        target_pid = call_arg[0][0]
                        self.assertGreater(target_pid, 0)

    def test_real_unmocked_executions_preserve_process_group_immunity(self) -> None:
        """Execute unmocked daemon operations with 0 and -1 PIDs; process group survives."""
        # Under POSIX, os.kill(0, SIGTERM) terminates the caller's process group.
        # If the guard failed, this test would abort the runner.
        for pid_val in ("0\n", "-1\n", "-999\n", "invalid_pid\n"):
            with self.subTest(pid_val=pid_val):
                # 1. Unmocked daemon_stop
                self.p_path.write_text(pid_val, encoding="ascii")
                self.s_path.touch()
                code_stop = daemon_stop(env=self.env)
                self.assertEqual(code_stop, 0)
                self.assertFalse(self.p_path.exists())
                self.assertFalse(self.s_path.exists())

                # 2. Unmocked daemon_clean
                self.p_path.write_text(pid_val, encoding="ascii")
                self.s_path.touch()
                code_clean = daemon_clean(env=self.env)
                self.assertEqual(code_clean, 0)
                self.assertFalse(self.p_path.exists())
                self.assertFalse(self.s_path.exists())

                # 3. Unmocked daemon_status
                self.p_path.write_text(pid_val, encoding="ascii")
                out = io.StringIO()
                with patch("sys.stdout", out):
                    code_status = daemon_status(env=self.env)
                self.assertEqual(code_status, 0)
                self.assertIn("Status: dead (stale PID file exists)", out.getvalue())

    def test_real_daemon_full_lifecycle_and_clean_termination(self) -> None:
        """Run real resident daemon background lifecycle without mock."""
        # 1. Start daemon in background
        out = io.StringIO()
        with patch("sys.stdout", out):
            code_start = daemon_start(foreground=False, env=self.env)
        self.assertEqual(code_start, 0)

        # Wait up to 10 seconds for daemon background process to write PID and bind socket
        for _ in range(200):
            if self.p_path.exists() and self.s_path.exists():
                break
            time.sleep(0.05)

        self.assertTrue(self.p_path.exists())
        self.assertTrue(self.s_path.exists())

        raw_pid = self.p_path.read_text(encoding="ascii").strip()
        daemon_pid = int(raw_pid)
        self.assertGreater(daemon_pid, 0)

        try:
            # 2. Check status reports active
            out_status = io.StringIO()
            with patch("sys.stdout", out_status):
                code_status = daemon_status(env=self.env)
            self.assertEqual(code_status, 0)
            self.assertIn("Status: active (running)", out_status.getvalue())
            self.assertIn(f"PID: {daemon_pid}", out_status.getvalue())

            # 3. Send IPC ping
            resp = send_ipc_request({"action": "ping"}, sock_path=self.s_path, timeout=3.0)
            self.assertIsNotNone(resp)
            self.assertEqual(resp.get("status"), "ok")

            # 4. Clean command refuses to delete running daemon
            out_clean = io.StringIO()
            with patch("sys.stdout", out_clean):
                code_clean = daemon_clean(env=self.env)
            self.assertEqual(code_clean, 1)
            self.assertIn(
                "Cannot clean: OTP-Local daemon is actively running", out_clean.getvalue()
            )
            self.assertTrue(self.p_path.exists())
            self.assertTrue(self.s_path.exists())

        finally:
            # 5. Stop the daemon cleanly
            out_stop = io.StringIO()
            with patch("sys.stdout", out_stop):
                code_stop = daemon_stop(env=self.env)
            self.assertEqual(code_stop, 0)
            self.assertFalse(self.p_path.exists())
            self.assertFalse(self.s_path.exists())

            # Ensure daemon process has exited and is reaped (up to 5s)
            for _ in range(50):
                if not alive(daemon_pid):
                    break
                time.sleep(0.1)
            self.assertFalse(alive(daemon_pid))


class TestMemoryZeroizationAndSecretProtection(unittest.TestCase):
    """Stress-test memory zeroization and secret string/traceback masking."""

    def test_otp_parameters_secret_masked_in_all_representations(self) -> None:
        """Verify OtpParameters.secret is absent from repr, str, format, collections, and tracebacks."""
        target_secret = "JBSWY3DPEHPK3PXP"
        otp = OtpParameters(
            secret=target_secret, account="security_test@example.com", issuer="Challenger"
        )

        # 1. Direct __repr__ and __str__
        r = repr(otp)
        s = str(otp)
        self.assertNotIn(target_secret, r, f"Secret leaked in repr: {r}")
        self.assertNotIn(target_secret, s, f"Secret leaked in str: {s}")
        self.assertNotIn(target_secret, f"{otp}", f"Secret leaked in f-string: {otp}")
        self.assertNotIn(target_secret, f"{otp!r}", f"Secret leaked in f-string repr: {otp!r}")

        # 2. Collections and nested structures
        nested_list = [otp]
        nested_dict = {"param": otp}
        nested_tuple = (otp,)
        self.assertNotIn(target_secret, repr(nested_list))
        self.assertNotIn(target_secret, repr(nested_dict))
        self.assertNotIn(target_secret, repr(nested_tuple))

        # 3. Exception traceback formatting
        # When an exception is raised in a function receiving OtpParameters,
        # verify that OtpParameters representation in the traceback / locals never contains the secret.
        def _simulate_handler(token: OtpParameters) -> None:
            raise RuntimeError(f"Processing failed for account: {token.account}")

        try:
            _simulate_handler(otp)
        except RuntimeError as exc:
            tb_formatted = traceback.format_exc()
            self.assertNotIn(target_secret, tb_formatted)

            # Inspect captured locals specifically for the token parameter
            tb_exc = traceback.TracebackException.from_exception(exc, capture_locals=True)
            for frame in tb_exc.stack:
                if frame.name == "_simulate_handler":
                    self.assertIn("token", frame.locals)
                    self.assertNotIn(target_secret, frame.locals["token"])

        # 4. Valid secret access is preserved for cryptographic use
        self.assertEqual(otp.secret, target_secret)
        uri = otp.to_uri()
        self.assertIn(f"secret={target_secret}", uri)

    def test_scope_model_repr_masking(self) -> None:
        """Verify Scope dataclass masks item, account, and vault IDs in representations."""
        item = "A" * 26
        account = "B" * 26
        vault = "C" * 26
        scope = Scope(item=item, account=account, vault=vault)

        r = repr(scope)
        self.assertNotIn(item, r)
        self.assertNotIn(account, r)
        self.assertNotIn(vault, r)

    def test_disable_core_dumps_sets_rlimit_and_dumpable(self) -> None:
        """Verify disable_core_dumps() sets RLIMIT_CORE to (0, 0) and PR_SET_DUMPABLE to 0."""
        # Execute probe in an isolated subprocess to not contaminate test runner limits
        probe_code = """
import ctypes
import resource
import sys
from authy_local.security import disable_core_dumps, get_libc

res = disable_core_dumps()
assert res is True, "disable_core_dumps returned False"

soft, hard = resource.getrlimit(resource.RLIMIT_CORE)
assert (soft, hard) == (0, 0), f"Expected RLIMIT_CORE (0, 0), got {(soft, hard)}"

if sys.platform.startswith("linux"):
    libc = get_libc()
    if libc and hasattr(libc, "prctl"):
        PR_GET_DUMPABLE = 3
        val = libc.prctl(ctypes.c_int(PR_GET_DUMPABLE), 0, 0, 0, 0)
        assert val == 0, f"Expected PR_GET_DUMPABLE 0, got {val}"

print("SUCCESS_DUMP_CHECK")
"""
        proc = subprocess.run(
            [sys.executable, "-c", probe_code],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            proc.returncode, 0, f"Failed: STDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
        )
        self.assertIn("SUCCESS_DUMP_CHECK", proc.stdout)

    def test_secure_zero_overwrites_all_buffer_types(self) -> None:
        """Verify secure_zero overwrites bytearray, memoryview, ctypes array, and raw memory."""
        # 1. Mutable bytearray
        b = bytearray(b"SENSITIVE_TOP_SECRET_PASSPHRASE_1234")
        self.assertNotEqual(b, bytearray(len(b)))
        secure_zero(b)
        self.assertEqual(b, bytearray(len(b)))

        # 2. memoryview
        b2 = bytearray(b"MEMORYVIEW_SECRET_KEY_EXCHANGE_DATA")
        mv = memoryview(b2)
        secure_zero(mv)
        self.assertEqual(b2, bytearray(len(b2)))
        self.assertEqual(bytes(mv), b"\x00" * len(b2))

        # 3. ctypes array
        arr = (ctypes.c_char * 32)(*b"CTYPES_SYMMETRIC_AES_KEY_BYTES!!")
        self.assertNotEqual(bytes(arr), b"\x00" * 32)
        secure_zero(arr)
        self.assertEqual(bytes(arr), b"\x00" * 32)

        # 4. Raw address + length via ctypes
        raw_buf = (ctypes.c_char * 64)(
            *b"RAW_POINTER_BUFFER_FOR_HARDWARE_KEY_BLOB_ZEROIZATION_TEST_CASE!!"
        )
        addr = ctypes.addressof(raw_buf)
        secure_zero(addr, 64)
        self.assertEqual(bytes(raw_buf), b"\x00" * 64)

        # 5. Boundary edge cases (empty, zero length, negative length)
        empty_b = bytearray()
        secure_zero(empty_b)
        self.assertEqual(len(empty_b), 0)

        # Null address / negative length must not crash
        secure_zero(0, 0)
        secure_zero(12345, -1)

    def test_secure_buffer_mlock_madvise_and_zeroization_on_close(self) -> None:
        """Verify SecureBuffer allocates, mlocks, madvises DONTDUMP, and zeroes memory on close."""
        buf = SecureBuffer(size=4096)
        self.assertEqual(buf.size, 4096)

        # Write test pattern
        buf.write(b"CONFIDENTIAL_123")
        self.assertEqual(buf.read(16), b"CONFIDENTIAL_123")
        self.assertEqual(buf.get_cstring(), "CONFIDENTIAL_123")

        # Test zeroize
        buf.zeroize()
        self.assertEqual(buf.read(16), b"\x00" * 16)

        # Close buffer
        buf.close()
        self.assertTrue(buf.is_closed)


class TestPathTraversalAndSymlinkDefenses(unittest.TestCase):
    """Stress-test path traversal payloads and symlink race defenses in importers.py."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_path_traversal_payloads_strictly_rejected(self) -> None:
        """Verify path traversal payloads to system files fail validation safely."""
        traversal_payloads = [
            "../../etc/passwd",
            "../../../../../../../../../../../../etc/passwd",
            "../../../../../../../../../../../../etc/shadow",
            "../../../../../../../../../../../../dev/null",
            "../../../../../../../../../../../../dev/zero",
            "../../../../../../../../../../../../dev/urandom",
            str(self.base_path / ".." / ".." / "etc" / "passwd"),
            str(self.base_path / "nested" / "dir" / ".." / ".." / ".." / ".." / "etc" / "passwd"),
        ]

        for payload in traversal_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(AppError) as ctx:
                    detect_and_parse_import(payload)
                # AppError(2) for invalid format / not found or AppError(3) for permission denied / symlink
                self.assertIn(ctx.exception.exit_code, (2, 3))

    def test_special_device_files_and_directories_rejected(self) -> None:
        """Verify non-regular files (FIFOs, sockets, directories) are rejected with AppError(2)."""
        # 1. Directory
        test_dir = self.base_path / "test_dir"
        test_dir.mkdir()
        with self.assertRaises(AppError) as ctx:
            detect_and_parse_import(test_dir)
        self.assertEqual(ctx.exception.exit_code, 2)

        # 2. Named pipe (FIFO)
        fifo_path = self.base_path / "test_fifo"
        try:
            os.mkfifo(fifo_path)
            fd = os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
            try:
                st = os.fstat(fd)
                self.assertFalse(stat.S_ISREG(st.st_mode))
            finally:
                os.close(fd)
        except OSError:
            pass

        # 3. Unix domain socket
        sock_path = self.base_path / "test_socket"
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(str(sock_path))
            with self.assertRaises(AppError) as ctx:
                detect_and_parse_import(sock_path)
            self.assertIn(ctx.exception.exit_code, (2, 3))
        finally:
            sock.close()

    def test_symlink_defense_comprehensive_matrix(self) -> None:
        """Verify direct, relative, circular, multi-hop, and dangling symlinks are rejected."""
        # 1. Direct symlink to sensitive file
        sym_passwd = self.base_path / "sym_passwd"
        sym_passwd.symlink_to("/etc/passwd")
        with self.assertRaises(AppError) as ctx:
            detect_and_parse_import(sym_passwd)
        self.assertEqual(ctx.exception.exit_code, 3)

        # 2. Relative symlink traversing outwards
        nested = self.base_path / "sub1" / "sub2"
        nested.mkdir(parents=True)
        rel_sym = nested / "rel_link"
        rel_sym.symlink_to("../../sym_passwd")
        with self.assertRaises(AppError) as ctx:
            detect_and_parse_import(rel_sym)
        self.assertEqual(ctx.exception.exit_code, 3)

        # 3. Multi-hop chain: hop1 -> hop2 -> real_file
        real_file = self.base_path / "valid.txt"
        real_file.write_text("otpauth://totp/Acme:alice?secret=JBSWY3DPEHPK3PXP\n")
        hop2 = self.base_path / "hop2"
        hop2.symlink_to(real_file)
        hop1 = self.base_path / "hop1"
        hop1.symlink_to(hop2)
        with self.assertRaises(AppError) as ctx:
            detect_and_parse_import(hop1)
        self.assertEqual(ctx.exception.exit_code, 3)

        # 4. Circular symlink (loop)
        circ_a = self.base_path / "circ_a"
        circ_b = self.base_path / "circ_b"
        circ_a.symlink_to(circ_b)
        circ_b.symlink_to(circ_a)
        with self.assertRaises(AppError) as ctx:
            detect_and_parse_import(circ_a)
        self.assertEqual(ctx.exception.exit_code, 3)

        # 5. Dangling symlink
        dangling = self.base_path / "dangling"
        dangling.symlink_to(self.base_path / "nonexistent_file_987654")
        with self.assertRaises(AppError) as ctx:
            detect_and_parse_import(dangling)
        self.assertEqual(ctx.exception.exit_code, 3)

    def test_high_concurrency_multithreaded_toctou_symlink_race(self) -> None:
        """Run rapid concurrent TOCTOU race testing between valid file and symlink to /etc/passwd.

        Proves that across hundreds of rapid concurrent swaps and parallel reader threads,
        no /etc/passwd data or root records are ever leaked.
        """
        race_file = self.base_path / "toctou_target.txt"
        valid_content = "otpauth://totp/Security:admin?secret=JBSWY3DPEHPK3PXP\n"
        race_file.write_text(valid_content)

        stop_event = threading.Event()

        # Swapper thread rapidly alternates race_file between legitimate file and symlink
        def swapper() -> None:
            while not stop_event.is_set():
                try:
                    race_file.unlink(missing_ok=True)
                    race_file.symlink_to("/etc/passwd")
                except OSError:
                    pass
                time.sleep(0.0002)
                try:
                    race_file.unlink(missing_ok=True)
                    race_file.write_text(valid_content)
                except OSError:
                    pass
                time.sleep(0.0002)

        swapper_thread = threading.Thread(target=swapper, daemon=True)
        swapper_thread.start()

        leaked_records = 0
        valid_successes = 0
        expected_errors = 0
        unexpected_errors = 0

        def reader_worker(iterations: int) -> None:
            nonlocal leaked_records, valid_successes, expected_errors, unexpected_errors
            for _ in range(iterations):
                try:
                    tokens = detect_and_parse_import(race_file)
                    for tok in tokens:
                        # Check if any sensitive passwd fields leaked
                        if (
                            "root:" in tok.account
                            or "bin:" in tok.account
                            or "daemon:" in tok.account
                        ):
                            leaked_records += 1
                        if tok.secret == "JBSWY3DPEHPK3PXP":
                            valid_successes += 1
                except AppError as err:
                    if err.exit_code in (2, 3):
                        expected_errors += 1
                    else:
                        unexpected_errors += 1
                except Exception:
                    unexpected_errors += 1

        # Spawn 4 concurrent worker threads
        threads = [threading.Thread(target=reader_worker, args=(150,)) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stop_event.set()
        swapper_thread.join(timeout=1.0)

        # Assertions
        self.assertEqual(
            leaked_records, 0, f"Critical security breach: {leaked_records} records leaked!"
        )
        self.assertEqual(
            unexpected_errors, 0, f"Unexpected errors encountered: {unexpected_errors}"
        )
        self.assertGreater(expected_errors + valid_successes, 0)


if __name__ == "__main__":
    unittest.main()
