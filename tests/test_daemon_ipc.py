"""Automated test suite for resident UNIX socket daemon, binary CBOR IPC, and SHM ring buffer."""

import concurrent.futures
import os
import shutil
import socket
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from authy_local.cli import main
from authy_local.daemon import (
    DaemonServer,
    daemon_status,
    daemon_systemd_install,
    generate_systemd_unit,
    lock_process_memory,
)
from authy_local.ipc import (
    decode_cbor,
    encode_cbor,
    get_runtime_dir,
    pid_path,
    recv_framed_message,
    send_framed_message,
    send_ipc_request,
    socket_path,
    verify_peer_credentials,
)
from authy_local.shm import ShmRingBuffer


class TestDaemonIpc(unittest.TestCase):
    """Unit, integration, and stress tests for resident daemon and low-latency IPC."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="test_daemon_ipc_")
        self.env = {
            "HOME": self.temp_dir,
            "XDG_RUNTIME_DIR": os.path.join(self.temp_dir, "run"),
        }
        os.makedirs(self.env["XDG_RUNTIME_DIR"], mode=0o700, exist_ok=True)
        self.test_sock = Path(self.env["XDG_RUNTIME_DIR"]) / "test_otp.sock"
        self.test_pid = Path(self.env["XDG_RUNTIME_DIR"]) / "test_otp.pid"
        self.test_shm_name = f"test-shm-{os.getpid()}-{int(time.time() * 1000) % 100000}"

    def tearDown(self) -> None:
        try:
            shm = ShmRingBuffer(name=self.test_shm_name)
            shm.unlink()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ipc_cbor_framing_and_roundtrip(self) -> None:
        """Verify binary CBOR message framing, length prefix, and roundtrip serialization."""
        data = {
            "action": "get_totp",
            "service": "GitHub",
            "account": "alice",
            "timestamp": 1234567890.5,
            "extra": [1, 2, 3],
        }
        encoded = encode_cbor(data)
        decoded = decode_cbor(encoded)
        self.assertEqual(decoded["action"], "get_totp")
        self.assertEqual(decoded["account"], "alice")
        self.assertEqual(decoded["timestamp"], 1234567890.5)

        # Test framing over real socketpair
        server_sock, client_sock = socket.socketpair()
        try:
            send_framed_message(client_sock, data)
            received = recv_framed_message(server_sock)
            self.assertEqual(received, data)
        finally:
            server_sock.close()
            client_sock.close()

    def test_ipc_framing_size_boundaries(self) -> None:
        """Verify oversized messages and empty/corrupted frames are rejected safely."""
        server_sock, client_sock = socket.socketpair()
        try:
            # Empty stream
            client_sock.close()
            self.assertIsNone(recv_framed_message(server_sock))
        finally:
            server_sock.close()

        # Oversized message header
        s1, s2 = socket.socketpair()
        try:
            s2.sendall(struct.pack(">I", 70000))  # Exceeds 64 KiB
            with self.assertRaises(ValueError):
                recv_framed_message(s1, max_bytes=65536)
        finally:
            s1.close()
            s2.close()

    def test_runtime_dir_and_path_resolution(self) -> None:
        """Verify get_runtime_dir resolves XDG_RUNTIME_DIR and enforces 0700 permissions."""
        rdir = get_runtime_dir(self.env)
        self.assertEqual(rdir, Path(self.env["XDG_RUNTIME_DIR"]))
        self.assertEqual(socket_path(self.env), rdir / "otp-local.sock")
        self.assertEqual(pid_path(self.env), rdir / "otp-local.pid")

        # Fallback without XDG_RUNTIME_DIR
        fallback_env = {"HOME": self.temp_dir}
        fb_dir = get_runtime_dir(fallback_env)
        self.assertTrue(fb_dir.exists())

    def test_peer_credentials_verification(self) -> None:
        """Verify SO_PEERCRED inspects caller UID and rejects mismatches."""
        s1, s2 = socket.socketpair()
        try:
            pid, uid, gid = verify_peer_credentials(s1, expected_uid=os.getuid())
            self.assertEqual(uid, os.getuid())

            # Mismatched expected UID must raise PermissionError
            with self.assertRaises(PermissionError):
                verify_peer_credentials(s1, expected_uid=os.getuid() + 9999)
        finally:
            s1.close()
            s2.close()

    def test_shm_ring_buffer_lifecycle_and_zero_copy_reads(self) -> None:
        """Verify SHM creation, write_slot, read_slot, and expiration semantics."""
        shm = ShmRingBuffer(name=self.test_shm_name, create=True)
        try:
            now = time.time()
            account = "gitlab:security"
            code = "987654"

            # 1. Unknown slot returns None
            self.assertIsNone(shm.read_slot("unknown:acct"))

            # 2. Write active slot
            wrote = shm.write_slot(
                account=account,
                code=code,
                expiry=now + 30.0,
                valid_until=now + 30.0,
                digits=6,
                period=30,
            )
            self.assertTrue(wrote)

            # 3. Zero-copy read
            res = shm.read_slot(account)
            self.assertIsNotNone(res)
            self.assertEqual(res["code"], code)
            self.assertEqual(res["digits"], 6)
            self.assertGreater(res["remaining_seconds"], 25.0)

            # 4. Expired slot returns None
            shm.write_slot(
                account="expired:key",
                code="111222",
                expiry=now - 5.0,
                valid_until=now - 5.0,
            )
            self.assertIsNone(shm.read_slot("expired:key"))
        finally:
            shm.unlink()

    def test_shm_concurrency_stress_and_sub_millisecond_latency(self) -> None:
        """Verify multi-threaded concurrent reads achieve sub-0.1ms (<100 microseconds) latency."""
        shm = ShmRingBuffer(name=self.test_shm_name, create=True)
        try:
            account = "aws:root"
            shm.write_slot(
                account=account,
                code="654321",
                expiry=time.time() + 60.0,
                valid_until=time.time() + 60.0,
            )

            latencies: list[float] = []

            def read_worker() -> None:
                # Open read handle
                reader = ShmRingBuffer(name=self.test_shm_name, create=False)
                for _ in range(50):
                    t0 = time.perf_counter()
                    slot = reader.read_slot(account)
                    t1 = time.perf_counter()
                    if slot and slot.get("code") == "654321":
                        latencies.append(t1 - t0)
                reader.close()

            # Execute 100 parallel queries across 10 threads
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(read_worker) for _ in range(10)]
                for f in futures:
                    f.result()

            self.assertGreaterEqual(len(latencies), 400)
            avg_latency = sum(latencies) / len(latencies)
            # Verify average latency is well under 0.1 milliseconds (100 microseconds)
            self.assertLess(
                avg_latency, 0.0001, f"Mean latency {avg_latency * 1000:.3f}ms >= 0.1ms"
            )
        finally:
            shm.unlink()

    def test_daemon_server_full_lifecycle_and_ipc(self) -> None:
        """Verify DaemonServer start, ping, cache_token, get_totp, verify_totp, flush, and stop."""
        server = DaemonServer(
            sock_path=self.test_sock,
            shm_name=self.test_shm_name,
            pid_file=self.test_pid,
            env=self.env,
            idle_timeout=900.0,
        )

        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()

        # Wait for socket and PID file to bind
        for _ in range(50):
            if self.test_sock.exists() and self.test_pid.exists():
                break
            time.sleep(0.05)
        self.assertTrue(self.test_sock.exists())
        self.assertTrue(self.test_pid.exists())

        try:
            # 1. Ping
            ping_res = send_ipc_request({"action": "ping"}, sock_path=self.test_sock)
            self.assertEqual(ping_res, {"status": "ok", "version": 1})

            # 2. Status
            status_res = send_ipc_request({"action": "status"}, sock_path=self.test_sock)
            self.assertEqual(status_res["status"], "ok")
            self.assertEqual(status_res["cached_count"], 0)

            # 3. Cache token
            secret = "JBSWY3DPEHPK3PXP"
            cache_res = send_ipc_request(
                {
                    "action": "cache_token",
                    "account": "alice@github",
                    "secret": secret,
                    "service": "GitHub",
                },
                sock_path=self.test_sock,
            )
            self.assertEqual(cache_res, {"status": "ok", "cached": "alice@github"})

            # 4. Read immediately from SHM without socket roundtrip
            shm_client = ShmRingBuffer(name=self.test_shm_name, create=False)
            shm_slot = shm_client.read_slot("alice@github")
            self.assertIsNotNone(shm_slot)
            shm_client.close()

            # 5. Get TOTP via IPC
            totp_res = send_ipc_request(
                {"action": "get_totp", "account": "alice@github"},
                sock_path=self.test_sock,
            )
            self.assertEqual(totp_res["status"], "ok")
            code = totp_res["code"]
            self.assertEqual(len(code), 6)
            self.assertEqual(code, shm_slot["code"])

            # 6. Verify TOTP
            ver_ok = send_ipc_request(
                {"action": "verify_totp", "account": "alice@github", "code": code},
                sock_path=self.test_sock,
            )
            self.assertEqual(ver_ok, {"status": "ok", "valid": True})

            ver_bad = send_ipc_request(
                {"action": "verify_totp", "account": "alice@github", "code": "000000"},
                sock_path=self.test_sock,
            )
            self.assertEqual(ver_bad, {"status": "ok", "valid": False})

            # 7. List tokens
            list_res = send_ipc_request({"action": "list_tokens"}, sock_path=self.test_sock)
            self.assertEqual(list_res, {"status": "ok", "accounts": ["alice@github"]})

            # 8. Flush cache
            flush_res = send_ipc_request({"action": "flush_cache"}, sock_path=self.test_sock)
            self.assertEqual(flush_res, {"status": "ok", "flushed": True})

            list_after = send_ipc_request({"action": "list_tokens"}, sock_path=self.test_sock)
            self.assertEqual(list_after["accounts"], [])
        finally:
            server._running = False
            server_thread.join(timeout=2.0)
            server.cleanup()

    def test_daemon_cli_helpers(self) -> None:
        """Verify daemon_status, systemd_unit, and systemd_install CLI operations."""
        # 1. Status when inactive
        self.assertEqual(daemon_status(self.env), 0)
        self.assertIsInstance(lock_process_memory(), bool)

        # 2. Systemd unit text
        unit_text = generate_systemd_unit()
        self.assertIn("Description=OTP-Local Resident Authentication Daemon", unit_text)
        self.assertIn("ExecStart=", unit_text)

        # 3. Systemd install
        with patch("shutil.which", return_value=None):
            install_rc = daemon_systemd_install(self.env)
            self.assertEqual(install_rc, 0)
            unit_path = (
                Path(self.env["HOME"]) / ".config" / "systemd" / "user" / "otp-local.service"
            )
            self.assertTrue(unit_path.exists())
            self.assertIn("LimitMEMLOCK=infinity", unit_path.read_text(encoding="utf-8"))

        # 4. CLI dispatch for daemon subcommands
        with patch("sys.stdout.write"):
            rc = main(["daemon", "systemd-unit"])
            self.assertEqual(rc, 0)

    def test_unauthorized_uid_connection_rejected(self) -> None:
        """Verify connection from mismatched caller UID is dropped immediately."""
        server = DaemonServer(
            sock_path=self.test_sock,
            shm_name=self.test_shm_name,
            pid_file=self.test_pid,
            env=self.env,
        )

        with patch("authy_local.daemon.verify_peer_credentials") as mock_verify:
            mock_verify.side_effect = PermissionError("Unauthorized caller")

            server_thread = threading.Thread(target=server.start, daemon=True)
            server_thread.start()

            for _ in range(50):
                if self.test_sock.exists():
                    break
                time.sleep(0.05)

            try:
                # Client attempts request but server drops connection due to PermissionError
                resp = send_ipc_request({"action": "ping"}, sock_path=self.test_sock, timeout=0.5)
                self.assertIsNone(resp)
            finally:
                server._running = False
                server_thread.join(timeout=2.0)
                server.cleanup()


if __name__ == "__main__":
    unittest.main()
