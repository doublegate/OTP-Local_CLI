"""Tests for Microsoft Windows DPAPI and Credential Manager token backend."""

import ctypes
import io
import os
import struct
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from authy_local import doctor
from authy_local.backends import dpapi
from authy_local.errors import AppError
from authy_local.processes import Completed


class SyntheticWin32Mock:
    """Synthetic Win32 C runtime emulator for Crypt32, Advapi32, and Kernel32."""

    def __init__(self):
        self.cred_store = {}
        self.freed_buffers = []
        self._keepalive = []

        self.crypt32 = MagicMock()
        self.advapi32 = MagicMock()
        self.kernel32 = MagicMock()

        self.crypt32.CryptProtectData.side_effect = self._crypt_protect
        self.crypt32.CryptUnprotectData.side_effect = self._crypt_unprotect
        self.advapi32.CredWriteW.side_effect = self._cred_write
        self.advapi32.CredReadW.side_effect = self._cred_read
        self.advapi32.CredDeleteW.side_effect = self._cred_delete
        self.advapi32.CredEnumerateW.side_effect = self._cred_enumerate
        self.advapi32.CredFree.side_effect = self._cred_free
        self.kernel32.LocalFree.side_effect = self._local_free

    def _crypt_protect(
        self, pDataIn, szDataDescr, pOptionalEntropy, pvReserved, pPromptStruct, dwFlags, pDataOut
    ):
        in_blob = pDataIn.contents
        raw = ctypes.string_at(in_blob.pbData, in_blob.cbData)
        entropy = b""
        if pOptionalEntropy:
            ent_blob = pOptionalEntropy.contents
            entropy = ctypes.string_at(ent_blob.pbData, ent_blob.cbData)
        header = struct.pack("<II", len(entropy), len(raw))
        ciphertext = b"DPAPI_CIPHER:" + header + entropy + raw
        buf = ctypes.create_string_buffer(ciphertext)
        self._keepalive.append(buf)
        pDataOut.contents.cbData = len(ciphertext)
        pDataOut.contents.pbData = ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))
        return 1

    def _crypt_unprotect(
        self, pDataIn, ppszDataDescr, pOptionalEntropy, pvReserved, pPromptStruct, dwFlags, pDataOut
    ):
        in_blob = pDataIn.contents
        raw = ctypes.string_at(in_blob.pbData, in_blob.cbData)
        if not raw.startswith(b"DPAPI_CIPHER:"):
            return 0
        payload = raw[len(b"DPAPI_CIPHER:") :]
        if len(payload) < 8:
            return 0
        ent_len, raw_len = struct.unpack("<II", payload[:8])
        stored_entropy = payload[8 : 8 + ent_len]
        plaintext = payload[8 + ent_len : 8 + ent_len + raw_len]
        if pOptionalEntropy:
            ent_blob = pOptionalEntropy.contents
            provided_entropy = ctypes.string_at(ent_blob.pbData, ent_blob.cbData)
            if stored_entropy != provided_entropy:
                return 0
        buf = ctypes.create_string_buffer(plaintext)
        self._keepalive.append(buf)
        pDataOut.contents.cbData = len(plaintext)
        pDataOut.contents.pbData = ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))
        return 1

    def _cred_write(self, pCred, dwFlags):
        cred = pCred.contents
        blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        self.cred_store[cred.TargetName] = blob
        return 1

    def _cred_read(self, target_name, cred_type, dwFlags, p_p_cred):
        if target_name not in self.cred_store:
            return 0
        blob = self.cred_store[target_name]
        buf = ctypes.create_string_buffer(blob)
        self._keepalive.append(buf)

        cred = dpapi.CREDENTIALW()
        cred.TargetName = target_name
        cred.CredentialBlobSize = len(blob)
        cred.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))
        cred.Type = cred_type
        self._keepalive.append(cred)

        p_cred = ctypes.pointer(cred)
        self._keepalive.append(p_cred)
        p_p_cred.contents = p_cred
        return 1

    def _cred_delete(self, target_name, cred_type, dwFlags):
        self.cred_store.pop(target_name, None)
        return 1

    def _cred_enumerate(self, filter_str, dwFlags, pCount, p_p_creds):
        prefix = filter_str.rstrip("*")
        matches = [k for k in self.cred_store if k.startswith(prefix)]
        pCount.contents.value = len(matches)
        if not matches:
            return 1
        cred_ptrs = (dpapi.PCREDENTIALW * len(matches))()
        for idx, target in enumerate(matches):
            blob = self.cred_store[target]
            buf = ctypes.create_string_buffer(blob)
            self._keepalive.append(buf)
            c = dpapi.CREDENTIALW()
            c.TargetName = target
            c.CredentialBlobSize = len(blob)
            c.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))
            self._keepalive.append(c)
            cred_ptrs[idx] = ctypes.pointer(c)
        self._keepalive.append(cred_ptrs)
        p_p_creds.contents = ctypes.cast(cred_ptrs, ctypes.POINTER(dpapi.PCREDENTIALW))
        return 1

    def _cred_free(self, pBuffer):
        self.freed_buffers.append(pBuffer)

    def _local_free(self, hMem):
        self.freed_buffers.append(hMem)


class TestDpapiBackend(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.chmod(self.temp_dir.name, 0o700)
        self.env = {
            "PATH": "/usr/bin:/bin",
            "HOME": self.temp_dir.name,
            "LOCALAPPDATA": self.temp_dir.name,
            "XDG_STATE_HOME": self.temp_dir.name,
            "USERNAME": "testuser",
            "USERDOMAIN": "TESTDOMAIN",
        }
        self.win32_mock = SyntheticWin32Mock()
        dpapi._crypt32_override = self.win32_mock.crypt32
        dpapi._advapi32_override = self.win32_mock.advapi32
        dpapi._kernel32_override = self.win32_mock.kernel32

    def tearDown(self):
        dpapi._crypt32_override = None
        dpapi._advapi32_override = None
        dpapi._kernel32_override = None
        self.temp_dir.cleanup()

    def test_probe_non_win32(self):
        dpapi._crypt32_override = None
        dpapi._advapi32_override = None
        with patch("sys.platform", "linux"):
            res = dpapi.probe(self.env)
            self.assertEqual(res["state"], "not-applicable")
            res_cred = dpapi.probe_credman(self.env)
            self.assertEqual(res_cred["state"], "not-applicable")

    def test_probe_win32_available(self):
        with patch("sys.platform", "win32"):
            res = dpapi.probe(self.env)
            self.assertEqual(res["state"], "available")
            self.assertFalse(res["hello"])
            res_cred = dpapi.probe_credman(self.env)
            self.assertEqual(res_cred["state"], "available")

    def test_probe_win32_missing_when_dll_fails(self):
        dpapi._crypt32_override = None
        dpapi._advapi32_override = None
        with (
            patch("sys.platform", "win32"),
            patch.object(dpapi, "_get_crypt32", side_effect=Exception("dll error")),
            patch.object(dpapi, "_get_advapi32", side_effect=Exception("dll error")),
        ):
            self.assertEqual(dpapi.probe(self.env)["state"], "missing")
            self.assertEqual(dpapi.probe_credman(self.env)["state"], "missing")

    def test_has_windows_hello(self):
        with patch("sys.platform", "linux"):
            self.assertFalse(dpapi.has_windows_hello())

        with (
            patch("sys.platform", "win32"),
            patch.dict(os.environ, {"OTP_LOCAL_WINDOWS_HELLO": "1"}),
        ):
            self.assertTrue(dpapi.has_windows_hello())

    def test_dpapi_encrypt_decrypt_roundtrip(self):
        secret = b"SUPER_SECRET_OTP_SEED"
        entropy = dpapi._get_entropy(self.env)
        ciphertext = dpapi.dpapi_encrypt(secret, entropy=entropy)
        self.assertNotEqual(ciphertext, secret)
        self.assertTrue(ciphertext.startswith(b"DPAPI_CIPHER:"))

        decrypted = dpapi.dpapi_decrypt(ciphertext, entropy=entropy)
        self.assertEqual(decrypted, secret)

    def test_dpapi_decrypt_wrong_entropy_fails(self):
        secret = b"SUPER_SECRET_OTP_SEED"
        ciphertext = dpapi.dpapi_encrypt(secret, entropy=b"entropy_1" * 4)
        with self.assertRaises(AppError) as ctx:
            dpapi.dpapi_decrypt(ciphertext, entropy=b"entropy_2" * 4)
        self.assertEqual(ctx.exception.exit_code, 4)

    def test_dpapi_encrypt_failure_raises(self):
        self.win32_mock.crypt32.CryptProtectData.side_effect = None
        self.win32_mock.crypt32.CryptProtectData.return_value = 0
        with self.assertRaises(AppError) as ctx:
            dpapi.dpapi_encrypt(b"data", entropy=b"salt")
        self.assertEqual(ctx.exception.exit_code, 4)

    def test_dpapi_decrypt_failure_raises(self):
        self.win32_mock.crypt32.CryptUnprotectData.side_effect = None
        self.win32_mock.crypt32.CryptUnprotectData.return_value = 0
        with self.assertRaises(AppError) as ctx:
            dpapi.dpapi_decrypt(b"bad_cipher", entropy=b"salt")
        self.assertEqual(ctx.exception.exit_code, 4)

    def test_credman_read_write_delete_list(self):
        target = "OTP-Local:test_account"
        blob = b"ENCRYPTED_BLOB_BYTES"
        dpapi.credman_write(target, blob)
        self.assertEqual(dpapi.credman_read(target), blob)

        targets = dpapi.credman_list("OTP-Local:")
        self.assertIn(target, targets)

        dpapi.credman_delete(target)
        with self.assertRaises(AppError) as ctx:
            dpapi.credman_read(target)
        self.assertEqual(ctx.exception.exit_code, 4)

    def test_dpapi_enroll_and_records_roundtrip(self):
        dpapi.dpapi_enroll("github_work", "JBSWY3DPEHPK3PXP", self.env)

        records = dpapi.dpapi_records(self.env)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0], ("github_work", "github_work [DPAPI]"))

        # Verify enrolled token generates expected RFC 6238 TOTP code
        code = dpapi.dpapi_code("github_work", self.env, timestamp=1111111110)
        self.assertEqual(code, "358462")

    def test_dpapi_enroll_validation(self):
        with self.assertRaises(AppError) as ctx:
            dpapi.dpapi_enroll("bad account!", "JBSWY3DPEHPK3PXP", self.env)
        self.assertEqual(ctx.exception.exit_code, 2)

        with self.assertRaises(AppError) as ctx:
            dpapi.dpapi_enroll("valid_account", "", self.env)
        self.assertEqual(ctx.exception.exit_code, 2)

    def test_dpapi_code_validation_and_not_found(self):
        with self.assertRaises(AppError) as ctx:
            dpapi.dpapi_code("bad label!", self.env)
        self.assertEqual(ctx.exception.exit_code, 2)

        with self.assertRaises(AppError) as ctx:
            dpapi.dpapi_code("nonexistent", self.env)
        self.assertEqual(ctx.exception.exit_code, 4)

    def test_dpapi_delete_removes_from_credman_and_index(self):
        dpapi.dpapi_enroll("target_account", "JBSWY3DPEHPK3PXP", self.env)
        self.assertEqual(len(dpapi.dpapi_records(self.env)), 1)

        dpapi.dpapi_delete("target_account", self.env)
        self.assertEqual(len(dpapi.dpapi_records(self.env)), 0)

    def test_doctor_report_win32(self):
        def _which(name, path=None):
            if name == "clip":
                return "C:\\Windows\\System32\\clip.exe"
            if name == "w32tm":
                return "C:\\Windows\\System32\\w32tm.exe"
            return None

        with (
            patch("sys.platform", "win32"),
            patch("shutil.which", side_effect=_which),
            patch("authy_local.doctor.run", return_value=Completed(0, b"")),
            patch.dict(os.environ, {"OTP_LOCAL_WINDOWS_HELLO": "1"}),
        ):
            rep = doctor.report(self.env)
            self.assertEqual(rep["platform"]["state"], "available")
            self.assertEqual(rep["dpapi"]["state"], "available")
            self.assertEqual(rep["credman"]["state"], "available")
            self.assertEqual(rep["windows-hello"]["state"], "available")
            self.assertEqual(rep["keychain"]["state"], "not-applicable")
            self.assertEqual(rep["secure-enclave"]["state"], "not-applicable")
            self.assertEqual(rep["totpm"]["state"], "not-applicable")
            self.assertEqual(rep["tpm2-totp"]["state"], "not-applicable")
            self.assertEqual(rep["tpm-device"]["state"], "not-applicable")
            self.assertEqual(rep["wl-copy"]["state"], "available")
            self.assertEqual(rep["clock"]["state"], "available")

    def test_doctor_install_win32_winget(self):
        def _which(name, path=None):
            if name == "winget":
                return "C:\\Program Files\\WindowsApps\\winget.exe"
            return None

        out = io.StringIO()
        err = io.StringIO()
        with (
            patch("sys.platform", "win32"),
            patch("shutil.which", side_effect=_which),
            patch(
                "authy_local.doctor.report",
                return_value={"fzf": {"state": "missing"}, "platform": {"state": "available"}},
            ),
            patch(
                "authy_local.doctor.run",
                return_value=Completed(0, b"Successfully installed junegunn.fzf\n"),
            ) as mock_run,
        ):
            res = doctor.install_missing(self.env, stdout=out, stderr=err)
            self.assertTrue(res)
            self.assertIn("Installing missing capabilities via winget", out.getvalue())
            self.assertIn("Successfully installed missing winget packages", out.getvalue())
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            self.assertIn("winget.exe", args[0])
            self.assertIn("junegunn.fzf", args)

    def test_doctor_install_win32_scoop(self):
        def _which(name, path=None):
            if name == "scoop":
                return "C:\\Users\\testuser\\scoop\\shims\\scoop.cmd"
            return None

        out = io.StringIO()
        err = io.StringIO()
        with (
            patch("sys.platform", "win32"),
            patch("shutil.which", side_effect=_which),
            patch(
                "authy_local.doctor.report",
                return_value={"yubikey": {"state": "missing"}, "platform": {"state": "available"}},
            ),
            patch(
                "authy_local.doctor.run",
                return_value=Completed(0, b"Successfully installed ykman\n"),
            ) as mock_run,
        ):
            res = doctor.install_missing(self.env, stdout=out, stderr=err)
            self.assertTrue(res)
            self.assertIn("Installing missing capabilities via Scoop", out.getvalue())
            self.assertIn("Successfully installed missing Scoop packages", out.getvalue())
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            self.assertIn("scoop.cmd", args[0])
            self.assertIn("ykman", args)

    def test_doctor_install_win32_no_package_manager(self):
        out = io.StringIO()
        err = io.StringIO()
        with (
            patch("sys.platform", "win32"),
            patch("shutil.which", return_value=None),
            patch(
                "authy_local.doctor.report",
                return_value={"fzf": {"state": "missing"}},
            ),
        ):
            res = doctor.install_missing(self.env, stdout=out, stderr=err)
            self.assertFalse(res)
            self.assertIn("requires winget or Scoop", err.getvalue())

    def test_tui_items_dpapi_integration(self):
        from authy_local import tui_items

        dpapi.dpapi_enroll("acct_dpapi_tui", "JBSWY3DPEHPK3PXP", self.env)

        recs = tui_items.records("dpapi", {}, self.env)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0][0], "acct_dpapi_tui")

        args = tui_items.arguments("dpapi", {}, "acct_dpapi_tui")
        self.assertEqual(args, ["--backend", "dpapi", "--account", "acct_dpapi_tui"])

        tui_items.remove("dpapi", {}, "acct_dpapi_tui", self.env)
        recs_after = tui_items.records("dpapi", {}, self.env)
        self.assertEqual(len(recs_after), 0)

    @patch("authy_local.cli.has_terminal", return_value=True)
    def test_cli_dpapi_show_and_enroll(self, mock_term):
        from authy_local import cli

        # 1. Enroll via CLI
        with patch("getpass.getpass", side_effect=["JBSWY3DPEHPK3PXP", "JBSWY3DPEHPK3PXP"]):
            stdout = io.StringIO()
            stdout.isatty = lambda: True
            code = cli.main(
                ["enroll", "--backend", "dpapi", "--account", "cli_dpapi_test", "--apply"],
                stdin=io.StringIO(),
                stdout=stdout,
                stderr=io.StringIO(),
            )
            self.assertEqual(code, 0)

        # 2. Show via CLI
        stdout = io.StringIO()
        stdout.isatty = lambda: True
        code = cli.main(
            ["show", "--backend", "dpapi", "--account", "cli_dpapi_test"],
            stdin=io.StringIO(),
            stdout=stdout,
            stderr=io.StringIO(),
        )
        self.assertEqual(code, 0)
        output_code = stdout.getvalue().strip()
        self.assertEqual(len(output_code), 6)
        self.assertTrue(output_code.isdigit())


if __name__ == "__main__":
    unittest.main()
