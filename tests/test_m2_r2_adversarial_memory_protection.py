"""Milestone M2 Adversarial Memory Protection & Zeroization Test Suite.

Authored by Challenger M2-2 (Empirical Challenger) to rigorously stress-test:
1. Linux kernel runtime security (init_runtime_security):
   Empirically verifies via ctypes prctl(PR_GET_DUMPABLE) that process dumpability
   is disabled (0) and resource.RLIMIT_CORE is enforced at (0, 0).
2. Daemon in-place memory zeroization (DaemonServer.flush_cache):
   Inspects memory via ctypes raw pointers to verify that SecureBuffer and
   POSIX shared memory slots are overwritten with \x00 bytes upon cache flush,
   and stress-tests resilience against released memoryview objects.
3. Vault backend in-place memory zeroization:
   Inspects memory via ctypes raw pointers in fido2, dpapi, and keychain backends
   to verify decrypted secret buffers are overwritten with \x00 bytes in finally blocks.
4. Textual TUI modal unmount credential zeroization under real lifecycle conditions:
   Verifies whether #inp-otp-secret.value, live code labels, #code-digits, and
   #qr-content are wiped upon natural modal dismissal / unmounting.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from textual.app import App
from textual.widgets import Input, Static

from authy_local.backends import dpapi as dpapi_mod
from authy_local.backends.dpapi import dpapi_code
from authy_local.backends.fido2 import fido2_code
from authy_local.backends.keychain import keychain_code
from authy_local.daemon import DaemonServer
from authy_local.security import secure_zero
from authy_local.shm import ShmRingBuffer
from authy_local.tui import AddOtpModal, CodeDisplayModal, InteractiveQrModal


class TestRuntimeSecurityAdversarial(unittest.TestCase):
    """Stress-test init_runtime_security at the Linux kernel boundary."""

    def test_prctl_dumpable_and_rlimit_in_isolated_process(self) -> None:
        """Verify PR_GET_DUMPABLE returns 0 and RLIMIT_CORE is (0, 0) after init."""
        probe_code = """
import ctypes
import resource
from authy_local.security import init_runtime_security

libc = ctypes.CDLL(None)
PR_GET_DUMPABLE = 3

# Verify default Linux state is dumpable (1)
before_dump = libc.prctl(PR_GET_DUMPABLE, 0, 0, 0, 0)
assert before_dump == 1, f"Expected initial dumpable 1, got {before_dump}"

# Initialize runtime security
status = init_runtime_security(enable_mlock=False)
assert status["core_dumps_disabled"] is True

# Empirically query Linux kernel state
after_dump = libc.prctl(PR_GET_DUMPABLE, 0, 0, 0, 0)
assert after_dump == 0, f"PR_GET_DUMPABLE expected 0, got {after_dump}"

soft, hard = resource.getrlimit(resource.RLIMIT_CORE)
assert (soft, hard) == (0, 0), f"RLIMIT_CORE expected (0, 0), got {(soft, hard)}"
print("SUCCESS")
"""
        proc = subprocess.run(
            [sys.executable, "-c", probe_code],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"Subprocess kernel probe failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}",
        )
        self.assertIn("SUCCESS", proc.stdout)


class TestDaemonFlushCacheInPlaceZeroization(unittest.TestCase):
    """Empirically inspect raw memory buffers in daemon.flush_cache via ctypes."""

    def test_daemon_flush_cache_ctypes_zeroization(self) -> None:
        """Verify SecureBuffer and ShmRingBuffer memory pages are overwritten with \\x00."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sock = Path(tmpdir) / "test_flush.sock"
            pid = Path(tmpdir) / "test_flush.pid"
            shm_name = f"test_shm_challenger_{os.getpid()}"

            server = DaemonServer(
                sock_path=sock,
                shm_name=shm_name,
                pid_file=pid,
                env={},
                idle_timeout=30.0,
            )
            shm = ShmRingBuffer(name=shm_name, create=True)
            server._shm = shm

            # Cache token
            account = "adversarial:bob"
            secret = "JBSWY3DPEHPK3PXP"
            req = {"account": account, "secret": secret, "digits": 6, "period": 30}
            res = server._action_cache_token(req)
            self.assertEqual(res["status"], "ok")

            sbuf = server._cached_buffers[account]
            sbuf_addr = sbuf.address
            self.assertIsNotNone(sbuf_addr)
            self.assertEqual(ctypes.string_at(sbuf_addr, len(secret)), secret.encode("utf-8"))

            shm_addr = ctypes.addressof((ctypes.c_char * len(shm.buf)).from_buffer(shm.buf))
            self.assertIn(account.encode("utf-8"), ctypes.string_at(shm_addr, len(shm.buf)))

            # Spy on secure_zero calls during flush_cache
            zeroed_allocations: list[tuple[int, int, bytes, bytes]] = []
            orig_secure_zero = secure_zero

            def spy_zero(
                target: bytearray | memoryview | ctypes.Array | int, length: int | None = None
            ) -> None:
                if isinstance(target, int):
                    addr = target
                    n = length or 0
                elif isinstance(target, (bytearray, memoryview)):
                    addr = ctypes.addressof((ctypes.c_char * len(target)).from_buffer(target))
                    n = len(target)
                else:
                    addr = None
                    n = 0

                if addr is not None and n > 0:
                    before = ctypes.string_at(addr, n)
                    orig_secure_zero(target, length)
                    after = ctypes.string_at(addr, n)
                    zeroed_allocations.append((addr, n, before, after))
                else:
                    orig_secure_zero(target, length)

            with (
                patch("authy_local.daemon.secure_zero", side_effect=spy_zero),
                patch("authy_local.security.secure_zero", side_effect=spy_zero),
            ):
                server.flush_cache()

            # Confirm SecureBuffer was wiped with \x00
            sbuf_wipes = [rec for rec in zeroed_allocations if rec[0] == sbuf_addr]
            self.assertTrue(
                len(sbuf_wipes) > 0, "SecureBuffer address was not passed to secure_zero"
            )
            self.assertEqual(sbuf_wipes[0][3], b"\x00" * sbuf.size)

            # Confirm SHM buffer was wiped with \x00
            shm_wipes = [rec for rec in zeroed_allocations if rec[0] == shm_addr]
            self.assertTrue(len(shm_wipes) > 0, "SHM buffer address was not passed to secure_zero")
            self.assertEqual(shm_wipes[0][3], b"\x00" * len(shm.buf))

            # Confirm state clean
            self.assertEqual(len(server._cached_buffers), 0)
            self.assertEqual(len(server._cached_tokens), 0)

            server.cleanup()

    def test_daemon_flush_cache_handles_released_shm_without_crash(self) -> None:
        """Verify flush_cache does not crash when ShmRingBuffer buffer was previously closed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sock = Path(tmpdir) / "test_released.sock"
            pid = Path(tmpdir) / "test_released.pid"
            shm_name = f"test_shm_rel_{os.getpid()}"

            server = DaemonServer(
                sock_path=sock,
                shm_name=shm_name,
                pid_file=pid,
                env={},
                idle_timeout=30.0,
            )
            shm = ShmRingBuffer(name=shm_name, create=True)
            server._shm = shm

            # Simulate SHM segment being closed prior to flush_cache
            shm.close()

            # flush_cache must safely handle closed/released memoryview without raising ValueError
            try:
                server.flush_cache()
            except ValueError as e:
                self.fail(
                    f"FLUSH_CACHE RE-ENTRY BUG: flush_cache() crashed on released SHM memoryview: {e}"
                )


class TestBackendVaultInPlaceZeroization(unittest.TestCase):
    """Empirically inspect raw memory buffers in vault backends via ctypes."""

    def test_backend_raw_secret_buffer_ctypes_zeroization(self) -> None:
        """Verify decrypted bytearrays in fido2, dpapi, and keychain are wiped with \\x00."""
        captured: dict[str, dict[str, Any]] = {}

        def make_spy(backend_name: str):
            def spy(buf: Any, length: int | None = None) -> None:
                if isinstance(buf, (bytearray, memoryview)):
                    n = len(buf)
                    c_buf = (ctypes.c_char * n).from_buffer(buf)
                    addr = ctypes.addressof(c_buf)
                    before = ctypes.string_at(addr, n)
                    secure_zero(buf, length)
                    after = ctypes.string_at(addr, n)
                    captured[backend_name] = {
                        "addr": addr,
                        "len": n,
                        "before": before,
                        "after": after,
                        "buf_bytes": bytes(buf),
                    }
                else:
                    secure_zero(buf, length)

            return spy

        # 1. FIDO2 Backend
        secret_fido = b"JBSWY3DPEHPK3PXP"
        with patch("authy_local.backends.fido2.secure_zero", side_effect=make_spy("fido2")):
            vault_data = {
                "accounts": {
                    "alice": {
                        "salt": "aa" * 32,
                        "credential_id": "bb" * 16,
                        "nonce": "cc" * 12,
                        "ciphertext": "dd" * 32,
                    }
                }
            }
            mock_dev = MagicMock()
            mock_dev.mock_assertion.return_value = b"hmac_mock_secret_32bytes_out_!"
            with (
                patch("authy_local.backends.fido2._read_vault", return_value=vault_data),
                patch(
                    "authy_local.backends.fido2.get_ctap2_device",
                    return_value=(mock_dev, MagicMock()),
                ),
                patch("authy_local.backends.fido2.AESGCM") as mock_aes,
            ):
                mock_aes_inst = MagicMock()
                mock_aes_inst.decrypt.return_value = secret_fido
                mock_aes.return_value = mock_aes_inst
                code_fido = fido2_code("alice", env={"FIDO2_PIN": "1234"}, timestamp=1000)
                self.assertTrue(code_fido.isdigit())

        f_res = captured.get("fido2")
        self.assertIsNotNone(f_res)
        self.assertEqual(f_res["before"], secret_fido)
        self.assertEqual(f_res["after"], b"\x00" * len(secret_fido))
        self.assertEqual(f_res["buf_bytes"], b"\x00" * len(secret_fido))

        # 2. DPAPI Backend
        secret_dpapi = b"HXDMVJECJJWSRB3HWIZR4IFUGFTMXBOZ"
        with patch("authy_local.backends.dpapi.secure_zero", side_effect=make_spy("dpapi")):
            with (
                patch.object(dpapi_mod, "_crypt32_override", MagicMock()),
                patch("authy_local.backends.dpapi.credman_read", return_value=b"cipher"),
                patch("authy_local.backends.dpapi.dpapi_decrypt", return_value=secret_dpapi),
            ):
                code_dpapi = dpapi_code("bob", env={}, timestamp=1000)
                self.assertTrue(code_dpapi.isdigit())

        d_res = captured.get("dpapi")
        self.assertIsNotNone(d_res)
        self.assertEqual(d_res["before"], secret_dpapi)
        self.assertEqual(d_res["after"], b"\x00" * len(secret_dpapi))
        self.assertEqual(d_res["buf_bytes"], b"\x00" * len(secret_dpapi))

        # 3. Keychain Backend
        secret_keychain = b"JBSWY3DPEHPK3PXP"
        with patch("authy_local.backends.keychain.secure_zero", side_effect=make_spy("keychain")):
            with (
                patch("shutil.which", return_value="/usr/bin/security"),
                patch(
                    "authy_local.backends.keychain.run",
                    return_value=MagicMock(returncode=0, stdout=secret_keychain + b"\n"),
                ),
            ):
                code_keychain = keychain_code("charlie", env={}, timestamp=1000)
                self.assertTrue(code_keychain.isdigit())

        k_res = captured.get("keychain")
        self.assertIsNotNone(k_res)
        self.assertEqual(k_res["before"], secret_keychain)
        self.assertEqual(k_res["after"], b"\x00" * len(secret_keychain))
        self.assertEqual(k_res["buf_bytes"], b"\x00" * len(secret_keychain))


class TestTuiModalLifecycleCredentialZeroization(unittest.IsolatedAsyncioTestCase):
    """Stress-test credential zeroization upon natural modal dismissal in Textual."""

    async def test_add_otp_modal_natural_dismiss_wipes_secret(self) -> None:
        """Adversarial check: verify #inp-otp-secret.value is wiped when dismissed naturally."""
        app = App()
        async with app.run_test() as pilot:
            add_modal = AddOtpModal()
            await app.push_screen(add_modal)
            await pilot.pause()

            inp = add_modal.query_one("#inp-otp-secret", Input)
            inp.value = "SUPER_SECRET_TOKEN_VALUE"
            lbl = add_modal.query_one("#lbl-live-code", Static)
            lbl.update("999 888")
            add_modal._live_code = "999 888"

            self.assertEqual(inp.value, "SUPER_SECRET_TOKEN_VALUE")

            # Dismiss modal through natural action / event
            add_modal.dismiss(None)
            await pilot.pause()

            # Empirical check: does the secret remain in inp.value?
            self.assertEqual(
                inp.value,
                "",
                f"CREDENTIAL LEAK BUG CONFIRMED: #inp-otp-secret.value retained {inp.value!r} after dismiss!",
            )

    async def test_code_display_modal_natural_dismiss_wipes_digits(self) -> None:
        """Adversarial check: verify #code-digits is wiped when dismissed naturally."""
        app = App()
        async with app.run_test() as pilot:
            code_modal = CodeDisplayModal(code="123456", item_label="github_token")
            await app.push_screen(code_modal)
            await pilot.pause()

            digits_widget = code_modal.query_one("#code-digits", Static)
            self.assertIn("123", digits_widget.content)

            code_modal.dismiss(None)
            await pilot.pause()

            self.assertEqual(
                digits_widget.content,
                "",
                f"CREDENTIAL LEAK BUG CONFIRMED: #code-digits retained {digits_widget.content!r} after dismiss!",
            )

    async def test_interactive_qr_modal_natural_dismiss_wipes_qr(self) -> None:
        """Adversarial check: verify #qr-content is wiped when dismissed naturally."""
        app = App()
        async with app.run_test() as pilot:
            qr_text = "otpauth://totp/Test?secret=SECRETKEY99"
            qr_modal = InteractiveQrModal(qr_text=qr_text, item_label="qr_test")
            await app.push_screen(qr_modal)
            await pilot.pause()

            qr_widget = qr_modal.query_one("#qr-content", Static)
            self.assertIn("SECRETKEY99", qr_widget.content)

            qr_modal.dismiss(None)
            await pilot.pause()

            self.assertEqual(
                qr_widget.content,
                "",
                f"CREDENTIAL LEAK BUG CONFIRMED: #qr-content retained {qr_widget.content!r} after dismiss!",
            )


if __name__ == "__main__":
    unittest.main()
