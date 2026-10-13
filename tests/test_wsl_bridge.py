"""Tests for WSL2 named pipe and UNIX socket interop bridge."""

import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from authy_local import doctor
from authy_local.backends import dpapi
from authy_local.enrollment import OtpParameters, generate_totp_code
from authy_local.errors import AppError
from authy_local.wsl_bridge import (
    WslBridgeClient,
    WslBridgeServer,
    get_bridge_socket_path,
    is_wsl,
)


class TestWslBridge(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.socket_path = str(Path(self.tmpdir.name) / "test_bridge.sock")
        self.env = {
            "OTP_LOCAL_BRIDGE_SOCKET": self.socket_path,
            "USER": "testuser",
            "HOME": self.tmpdir.name,
        }

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_is_wsl_detection(self) -> None:
        # Non-linux platforms return False
        with patch("sys.platform", "win32"):
            self.assertFalse(is_wsl())
        with patch("sys.platform", "darwin"):
            self.assertFalse(is_wsl())

        # Linux platform with WSL environment variables
        with patch("sys.platform", "linux"):
            with patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}, clear=True):
                self.assertTrue(is_wsl())
            with patch.dict(os.environ, {"WSL_INTEROP": "/run/WSL/1_interop"}, clear=True):
                self.assertTrue(is_wsl())

            # Linux without WSL vars but with /proc/version matching microsoft
            with patch.dict(os.environ, {}, clear=True):
                with patch("pathlib.Path.is_file", return_value=True):
                    with patch(
                        "pathlib.Path.read_text",
                        return_value="Linux version 5.15.133.1-microsoft-standard-WSL2",
                    ):
                        self.assertTrue(is_wsl())

                # Pure Linux without WSL indicators
                with patch("pathlib.Path.is_file", return_value=True):
                    with patch(
                        "pathlib.Path.read_text",
                        return_value="Linux version 6.6.10-arch1-1 (linux@archlinux)",
                    ):
                        with patch("pathlib.Path.exists", return_value=False):
                            self.assertFalse(is_wsl())

    def test_get_bridge_socket_path(self) -> None:
        # Custom override
        custom_env = {"OTP_LOCAL_BRIDGE_SOCKET": "/var/run/custom.sock"}
        self.assertEqual(get_bridge_socket_path(custom_env), "/var/run/custom.sock")

        # Windows default named pipe
        with patch("sys.platform", "win32"):
            win_env = {"USERNAME": "alice"}
            self.assertEqual(
                get_bridge_socket_path(win_env),
                r"\\.\pipe\otp-local-bridge-alice",
            )

        # Linux default UNIX socket
        with patch("sys.platform", "linux"):
            lin_env = {"USER": "bob"}
            self.assertEqual(
                get_bridge_socket_path(lin_env),
                "/tmp/otp-local-bridge-bob.sock",
            )

    def test_server_lifecycle_and_permissions(self) -> None:
        server = WslBridgeServer(socket_path=self.socket_path, env=self.env)
        server.start()
        self.assertTrue(os.path.exists(self.socket_path))
        # Ensure mode 0600 on UNIX
        if sys.platform != "win32":
            mode = os.stat(self.socket_path).st_mode & 0o777
            self.assertEqual(mode, 0o600)
        server.stop()
        self.assertFalse(os.path.exists(self.socket_path))

    def test_client_server_ping_roundtrip(self) -> None:
        server = WslBridgeServer(socket_path=self.socket_path, env=self.env)
        server.start()

        def serve():
            server.serve_one()

        t = threading.Thread(target=serve, daemon=True)
        t.start()

        client = WslBridgeClient(socket_path=self.socket_path, env=self.env)
        self.assertTrue(client.ping())
        t.join(timeout=2.0)
        server.stop()

    def test_client_ping_when_server_offline(self) -> None:
        client = WslBridgeClient(socket_path=self.socket_path, env=self.env)
        self.assertFalse(client.ping())

    def test_client_server_records_and_code_roundtrip(self) -> None:
        server = WslBridgeServer(socket_path=self.socket_path, env=self.env)
        server.start()

        records_data = [("github", "github [DPAPI]"), ("aws", "aws [DPAPI]")]
        expected_code = "123456"

        def mock_handle_request(request):
            action = request.get("action")
            if action == "ping":
                return {"status": "ok", "message": "pong"}
            if action == "records":
                return {"status": "ok", "records": records_data}
            if action == "code":
                self.assertEqual(request.get("account"), "github")
                self.assertEqual(request.get("timestamp"), 1000.0)
                return {"status": "ok", "code": expected_code}
            return {"status": "error", "error": "unknown"}

        server.handle_request = mock_handle_request

        running = True

        def loop():
            while running:
                server.serve_one()

        t = threading.Thread(target=loop, daemon=True)
        t.start()

        try:
            client = WslBridgeClient(socket_path=self.socket_path, env=self.env)
            records = client.get_records()
            self.assertEqual(records, records_data)

            code = client.get_code("github", timestamp=1000.0)
            self.assertEqual(code, expected_code)
        finally:
            running = False
            client_dummy = WslBridgeClient(socket_path=self.socket_path, env=self.env)
            try:
                client_dummy.ping()
            except Exception:
                pass
            server.stop()
            t.join(timeout=2.0)

    def test_client_server_enroll_and_delete_roundtrip(self) -> None:
        server = WslBridgeServer(socket_path=self.socket_path, env=self.env)
        server.start()

        enrolled = {}

        def mock_handle_request(request):
            action = request.get("action")
            if action == "enroll":
                enrolled[request["account"]] = request["secret"]
                return {"status": "ok"}
            if action == "delete":
                enrolled.pop(request["account"], None)
                return {"status": "ok"}
            if action == "ping":
                return {"status": "ok"}
            return {"status": "error"}

        server.handle_request = mock_handle_request

        running = True

        def loop():
            while running:
                server.serve_one()

        t = threading.Thread(target=loop, daemon=True)
        t.start()

        try:
            client = WslBridgeClient(socket_path=self.socket_path, env=self.env)
            client.enroll("github", "JBSWY3DPEHPK3PXP")
            self.assertEqual(enrolled.get("github"), "JBSWY3DPEHPK3PXP")

            client.delete("github")
            self.assertNotIn("github", enrolled)
        finally:
            running = False
            client_dummy = WslBridgeClient(socket_path=self.socket_path, env=self.env)
            try:
                client_dummy.ping()
            except Exception:
                pass
            server.stop()
            t.join(timeout=2.0)

    def test_error_propagation_and_exit_codes(self) -> None:
        server = WslBridgeServer(socket_path=self.socket_path, env=self.env)
        server.start()

        def mock_handle_request(request):
            action = request.get("action")
            if action == "code":
                acct = request.get("account")
                if acct == "missing_account":
                    return {"status": "error", "error": "Not found", "exit_code": 4}
                if acct == "corrupt":
                    return {"status": "error", "error": "Decrypt failed", "exit_code": 5}
            if action == "invalid":
                return {"status": "error", "error": "Bad request", "exit_code": 2}
            return {"status": "ok"}

        server.handle_request = mock_handle_request
        running = True

        def loop():
            while running:
                server.serve_one()

        t = threading.Thread(target=loop, daemon=True)
        t.start()

        try:
            client = WslBridgeClient(socket_path=self.socket_path, env=self.env)

            # Not found -> exit code 4
            with self.assertRaises(AppError) as cm:
                client.get_code("missing_account")
            self.assertEqual(cm.exception.exit_code, 4)

            # Decrypt failed -> exit code 5
            with self.assertRaises(AppError) as cm:
                client.get_code("corrupt")
            self.assertEqual(cm.exception.exit_code, 5)

            # Bad request / validation error -> exit code 2
            with self.assertRaises(AppError) as cm:
                client._send_request({"action": "invalid"})
            self.assertEqual(cm.exception.exit_code, 2)
        finally:
            running = False
            try:
                WslBridgeClient(socket_path=self.socket_path, env=self.env).ping()
            except Exception:
                pass
            server.stop()
            t.join(timeout=2.0)

    def test_server_malformed_json_resilience(self) -> None:
        server = WslBridgeServer(socket_path=self.socket_path, env=self.env)
        server.start()

        def serve():
            server.serve_one()

        t = threading.Thread(target=serve, daemon=True)
        t.start()

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self.socket_path)
        sock.sendall(b"NOT_VALID_JSON\n")
        data = sock.recv(4096)
        sock.close()
        t.join(timeout=2.0)
        server.stop()

        resp = json.loads(data.decode("utf-8"))
        self.assertEqual(resp.get("status"), "error")
        self.assertEqual(resp.get("exit_code"), 2)

    def test_dpapi_backend_wsl_bridge_integration(self) -> None:
        # When running on non-win32 with bridge socket configured
        server = WslBridgeServer(socket_path=self.socket_path, env=self.env)
        server.start()

        sample_secret = "JBSWY3DPEHPK3PXP"
        params = OtpParameters(secret=sample_secret, account="github")
        expected_code, _ = generate_totp_code(params, timestamp=1234567.0)

        mock_store = {"github": sample_secret}

        def mock_handle_request(req):
            act = req.get("action")
            if act == "ping":
                return {"status": "ok"}
            if act == "records":
                return {"status": "ok", "records": [("github", "github [DPAPI]")]}
            if act == "code":
                return {"status": "ok", "code": expected_code}
            if act == "enroll":
                mock_store[req["account"]] = req["secret"]
                return {"status": "ok"}
            if act == "delete":
                mock_store.pop(req["account"], None)
                return {"status": "ok"}
            return {"status": "error"}

        server.handle_request = mock_handle_request
        running = True

        def loop():
            while running:
                server.serve_one()

        t = threading.Thread(target=loop, daemon=True)
        t.start()

        try:
            # dpapi_records uses bridge
            records = dpapi.dpapi_records(self.env)
            self.assertEqual(records, [("github", "github [DPAPI]")])

            # dpapi_code uses bridge
            code = dpapi.dpapi_code("github", self.env, timestamp=1234567.0)
            self.assertEqual(code, expected_code)

            # dpapi_enroll uses bridge
            dpapi.dpapi_enroll("newaccount", "MFRGGZDFMZTWQ2LK", self.env)
            self.assertEqual(mock_store.get("newaccount"), "MFRGGZDFMZTWQ2LK")

            # dpapi_delete uses bridge
            dpapi.dpapi_delete("newaccount", self.env)
            self.assertNotIn("newaccount", mock_store)

            # probe and probe_credman
            probe_dpapi = dpapi.probe(self.env)
            self.assertEqual(probe_dpapi.get("state"), "available")

            probe_cm = dpapi.probe_credman(self.env)
            self.assertEqual(probe_cm.get("state"), "available")
        finally:
            running = False
            try:
                WslBridgeClient(socket_path=self.socket_path, env=self.env).ping()
            except Exception:
                pass
            server.stop()
            t.join(timeout=2.0)

    def test_doctor_report_with_wsl_bridge(self) -> None:
        server = WslBridgeServer(socket_path=self.socket_path, env=self.env)
        server.start()

        def loop():
            while server._running:
                server.serve_one()

        t = threading.Thread(target=loop, daemon=True)
        t.start()

        try:
            report = doctor.report(self.env)
            self.assertEqual(report.get("dpapi", {}).get("state"), "available")
            self.assertEqual(report.get("credman", {}).get("state"), "available")
        finally:
            server.stop()
            t.join(timeout=2.0)

        # When bridge is stopped, report should show missing
        report_offline = doctor.report(self.env)
        self.assertEqual(report_offline.get("dpapi", {}).get("state"), "missing")
        self.assertEqual(report_offline.get("credman", {}).get("state"), "missing")

    def test_bridge_server_recursion_guard(self) -> None:
        # In a process marked as bridge server, is_wsl_bridge_active must return False
        server_env = dict(self.env)
        server_env["OTP_LOCAL_BRIDGE_SERVER"] = "1"
        self.assertFalse(dpapi.is_wsl_bridge_active(server_env))
