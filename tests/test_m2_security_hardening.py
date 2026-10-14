"""Comprehensive automated test suite for Milestone M2 security hardening.

Covers:
1. OtpParameters secret repr and str shielding.
2. TOCTOU symlink race elimination and atomic file descriptor reading in importers.
3. YubiKey account name validation and command-line option injection prevention.
4. Runtime memory security initialization and core dump exclusion.
5. In-place memory zeroization behavior under ctypes and SecureBuffer.
6. Textual TUI modal unmount credential zeroization.
7. Top-level CLI exception shield preventing traceback leaks.
8. Daemon framing error handling with pre-bound req_format.
9. Plugin configuration file and directory permission enforcement.
"""

import io
import os
import resource
import socket
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from textual.app import App
from textual.widgets import Input, Static

from authy_local import cli
from authy_local.backends.hardware import LABEL as HARDWARE_LABEL
from authy_local.backends.hardware import yubikey_code
from authy_local.daemon import DaemonServer
from authy_local.enrollment import OtpParameters
from authy_local.errors import MESSAGES, AppError
from authy_local.importers import detect_and_parse_import
from authy_local.ipc import recv_framed_message
from authy_local.plugins.manager import PluginManager
from authy_local.security import (
    SecureBuffer,
    init_runtime_security,
    secure_zero,
)
from authy_local.tui import AddOtpModal, CodeDisplayModal, InteractiveQrModal


class TestM2SecurityHardening(unittest.TestCase):
    """Milestone M2 security hardening test cases."""

    def test_otp_parameters_repr_and_str_shielding(self) -> None:
        """Verify OtpParameters.secret is masked in repr and str to prevent traceback leaks."""
        secret = "JBSWY3DPEHPK3PXP"
        account = "alice@example.com"
        params = OtpParameters(secret=secret, account=account, issuer="AcmeCorp")

        rep = repr(params)
        st = str(params)

        self.assertNotIn(secret, rep, "Plaintext secret leaked in OtpParameters.__repr__")
        self.assertNotIn(secret, st, "Plaintext secret leaked in OtpParameters.__str__")
        self.assertIn(account, rep, "Account metadata missing from OtpParameters.__repr__")
        self.assertEqual(params.secret, secret, "Direct attribute access must remain intact")
        self.assertIn(secret, params.to_uri(), "Canonical URI serialization must remain functional")

    def test_importers_toctou_symlink_rejection_and_atomic_fd(self) -> None:
        """Verify detect_and_parse_import rejects symlinks atomically and reads via fd."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            target = tmppath / "valid_tokens.txt"
            target.write_text("otpauth://totp/Acme:alice?secret=JBSWY3DPEHPK3PXP\n")

            symlink = tmppath / "symlink_tokens.txt"
            symlink.symlink_to(target)

            # Assert symlink is strictly rejected with AppError(3)
            with self.assertRaises(AppError) as ctx:
                detect_and_parse_import(symlink)
            self.assertEqual(ctx.exception.exit_code, 3)

            # Assert regular file succeeds
            tokens = detect_and_parse_import(target)
            self.assertEqual(len(tokens), 1)
            self.assertEqual(tokens[0].account, "alice")

            # Assert non-existent file fails with AppError(2)
            with self.assertRaises(AppError) as ctx:
                detect_and_parse_import(tmppath / "nonexistent.txt")
            self.assertEqual(ctx.exception.exit_code, 2)

            # Assert directory path fails with AppError(2)
            with self.assertRaises(AppError) as ctx:
                detect_and_parse_import(tmppath)
            self.assertEqual(ctx.exception.exit_code, 2)

    def test_yubikey_account_name_character_validation_and_option_injection(self) -> None:
        """Verify yubikey_code validates account names against LABEL and rejects option injection."""
        env = {"PATH": "/usr/bin:/bin"}

        # Dangerous option-injection inputs must fail with AppError(2) before executing ykman
        malicious_inputs = [
            "-s",
            "--help",
            "-d",
            "--device",
            "; rm -rf /",
            "account;ls",
            "account $(whoami)",
            "account\nlist",
            " ",
            "",
            "-v",
            "../etc/passwd",
        ]

        for malicious in malicious_inputs:
            with self.assertRaises(AppError, msg=f"Failed to reject: {malicious!r}") as ctx:
                yubikey_code(malicious, env)
            self.assertEqual(ctx.exception.exit_code, 2)

        # Valid OATH formats (including colon and @-sign) must match LABEL regex
        valid_inputs = [
            "AWS:admin",
            "GitHub:octocat",
            "alice@example.com",
            "gitlab:user.name-01",
            "Google:my_account@gmail.com",
        ]
        for valid in valid_inputs:
            self.assertIsNotNone(
                HARDWARE_LABEL.fullmatch(valid),
                f"Valid OATH account {valid!r} rejected by regex",
            )

        # Mock run to verify valid account passes through to ykman
        with (
            patch("shutil.which", return_value="/usr/bin/ykman"),
            patch(
                "authy_local.backends.hardware.run",
                return_value=MagicMock(returncode=0, stdout=b"123456\n"),
            ) as mock_run,
        ):
            code = yubikey_code("AWS:admin", env)
            self.assertEqual(code, "123456")
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            self.assertEqual(args[-1], "AWS:admin")

    def test_init_runtime_security_execution_and_core_dump_disabling(self) -> None:
        """Verify init_runtime_security initializes core dump limits and signal hooks."""
        status = init_runtime_security(enable_mlock=False)
        self.assertIsInstance(status, dict)
        self.assertIn("core_dumps_disabled", status)
        self.assertIn("signal_handlers_installed", status)
        self.assertIn("memory_locked", status)
        self.assertTrue(status["signal_handlers_installed"])
        self.assertFalse(status["memory_locked"])

        # Check RLIMIT_CORE is set to 0
        soft, _hard = resource.getrlimit(resource.RLIMIT_CORE)
        self.assertEqual(soft, 0, "Core dump soft limit must be 0")

        # Test enable_mlock parameter
        status_locked = init_runtime_security(enable_mlock=True)
        self.assertIn("memory_locked", status_locked)

    def test_in_place_memory_zeroization_ctypes_and_secure_buffer(self) -> None:
        """Verify secure_zero and SecureBuffer perform real in-place memory wiping."""
        # 1. Test secure_zero with mutable bytearray
        secret_payload = b"TOP_SECRET_CREDENTIAL_DATA"
        buf = bytearray(secret_payload)
        self.assertEqual(bytes(buf), secret_payload)
        secure_zero(buf)
        self.assertEqual(bytes(buf), b"\x00" * len(secret_payload))

        # 2. Test secure_zero with memoryview
        target = bytearray(b"AAAAAAAAAAAAAAAA")
        view = memoryview(target)
        secure_zero(view)
        self.assertEqual(bytes(target), b"\x00" * 16)

        # 3. Test SecureBuffer lifecycle and zeroization
        sbuf = SecureBuffer(size=32)
        sbuf.write(b"HIGH_ENTROPY_KEY_BUFFER")
        self.assertIn(b"HIGH_ENTROPY_KEY", sbuf.read())
        sbuf.zeroize()
        # Underlying memory must be wiped with zeroes
        self.assertEqual(sbuf.read(), b"\x00" * 32)
        sbuf.close()
        self.assertTrue(sbuf._closed)
        with self.assertRaises(RuntimeError):
            sbuf.read()

    def test_plugin_configuration_permissions(self) -> None:
        """Verify PluginManager.save_config enforces 0o600 on config and 0o700 on parent dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"XDG_CONFIG_HOME": tmpdir}
            pm = PluginManager(env=env)
            pm.save_config(["trusted_plugin_1", "trusted_plugin_2"])

            cfg_path = Path(tmpdir) / "authy-local" / "plugins.json"
            self.assertTrue(cfg_path.is_file())
            self.assertEqual(cfg_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(cfg_path.parent.stat().st_mode & 0o777, 0o700)

    def test_cli_top_level_exception_shield(self) -> None:
        """Verify unhandled exceptions in main() return exit code 5 and do not print tracebacks."""
        out, err = io.StringIO(), io.StringIO()
        with patch(
            "authy_local.cli.parser",
            side_effect=RuntimeError("unexpected_internal_cryptographic_state"),
        ):
            code = cli.main(["show", "item"], stdout=out, stderr=err)

        self.assertEqual(code, 5)
        err_output = err.getvalue()
        self.assertNotIn("Traceback", err_output, "Traceback leaked to stderr!")
        self.assertNotIn("unexpected_internal_cryptographic_state", err_output)
        self.assertIn(MESSAGES[5], err_output)

    def test_daemon_error_handling_invalid_framing(self) -> None:
        """Verify framing errors in daemon return structured CBOR errors without UnboundLocalError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sock = Path(tmpdir) / "test_daemon.sock"
            pid = Path(tmpdir) / "test_daemon.pid"
            shm_name = f"test_shm_m2_{os.getpid()}"

            server = DaemonServer(
                sock_path=sock,
                shm_name=shm_name,
                pid_file=pid,
                env={},
                idle_timeout=30.0,
            )
            thread = threading.Thread(target=server.start, daemon=True)
            thread.start()

            # Wait for socket
            for _ in range(50):
                if sock.exists() and pid.exists():
                    break
                time.sleep(0.05)

            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.connect(str(sock))
                    # Send oversized frame length (70000 exceeds 65536)
                    client.sendall(struct.pack(">I", 70000))
                    client.settimeout(2.0)
                    resp = recv_framed_message(client)
                    self.assertIsNotNone(resp)
                    self.assertEqual(resp.get("status"), "error")
                    self.assertIn("Invalid message length", resp.get("message", ""))
            finally:
                server._running = False
                thread.join(timeout=2.0)
                server.cleanup()

    def test_daemon_flush_cache_real_zeroization(self) -> None:
        """Verify DaemonServer.flush_cache closes SecureBuffers and clears token secrets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sock = Path(tmpdir) / "test_flush.sock"
            pid = Path(tmpdir) / "test_flush.pid"
            shm_name = f"test_shm_flush_{os.getpid()}"

            server = DaemonServer(
                sock_path=sock,
                shm_name=shm_name,
                pid_file=pid,
                env={},
                idle_timeout=30.0,
            )
            server._shm = MagicMock()
            server._shm.buf = bytearray(1024)

            # Cache token
            req = {
                "account": "test_account",
                "secret": "JBSWY3DPEHPK3PXP",
                "digits": 6,
                "period": 30,
            }
            res = server._action_cache_token(req)
            self.assertEqual(res["status"], "ok")
            self.assertIn("test_account", server._cached_buffers)
            self.assertIn("test_account", server._cached_tokens)

            # Flush cache
            server.flush_cache()

            self.assertEqual(len(server._cached_buffers), 0)
            self.assertEqual(len(server._cached_tokens), 0)
            server.cleanup()


class TestTuiModalZeroization(unittest.IsolatedAsyncioTestCase):
    """Textual TUI modal screen memory zeroization tests."""

    async def test_tui_modal_unmount_credential_zeroization(self) -> None:
        """Verify CodeDisplayModal, AddOtpModal, and InteractiveQrModal wipe secrets on unmount."""
        app = App()
        async with app.run_test():
            # 1. AddOtpModal unmount
            add_modal = AddOtpModal()
            await app.push_screen(add_modal)
            inp = add_modal.query_one("#inp-otp-secret", Input)
            inp.value = "SUPER_SECRET_OATH_KEY"
            lbl = add_modal.query_one("#lbl-live-code", Static)
            lbl.update("999 888")

            add_modal.on_unmount()

            self.assertEqual(inp.value, "", "AddOtpModal failed to wipe #inp-otp-secret.value")
            self.assertEqual(add_modal._live_code, "")
            self.assertIsNone(add_modal._parsed_params)
            app.pop_screen()

            # 2. CodeDisplayModal unmount
            code_modal = CodeDisplayModal(code="654321", item_label="github_admin")
            await app.push_screen(code_modal)
            self.assertEqual(code_modal.code, "654321")
            self.assertEqual(code_modal.item_label, "github_admin")

            code_modal.on_unmount()

            self.assertEqual(code_modal.code, "")
            self.assertEqual(code_modal.item_label, "")
            app.pop_screen()

            # 3. InteractiveQrModal unmount
            qr_modal = InteractiveQrModal(
                qr_text="otpauth://totp/Test:user?secret=SECRETKEY",
                item_label="test_qr_label",
            )
            await app.push_screen(qr_modal)
            self.assertIn("SECRETKEY", qr_modal.qr_text)

            qr_modal.on_unmount()

            self.assertEqual(qr_modal.qr_text, "")
            self.assertEqual(qr_modal.item_label, "")
            app.pop_screen()


if __name__ == "__main__":
    unittest.main()
