"""Tests for Apple macOS Keychain and Secure Enclave token backend."""

import tempfile
import unittest
from unittest.mock import patch

from authy_local import doctor
from authy_local.backends import keychain
from authy_local.errors import AppError
from authy_local.processes import Completed


class TestKeychainBackend(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        import os

        os.chmod(self.temp_dir.name, 0o700)
        self.env = {
            "PATH": "/usr/bin:/bin",
            "HOME": self.temp_dir.name,
            "XDG_STATE_HOME": self.temp_dir.name,
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_probe_non_darwin(self):
        with patch("sys.platform", "linux"):
            res = keychain.probe(self.env)
            self.assertEqual(res["state"], "not-applicable")

    @patch("sys.platform", "darwin")
    @patch("shutil.which")
    def test_probe_darwin_missing_security(self, mock_which):
        mock_which.return_value = None
        res = keychain.probe(self.env)
        self.assertEqual(res["state"], "missing")

    @patch("sys.platform", "darwin")
    @patch("shutil.which")
    @patch("authy_local.backends.keychain.has_secure_enclave")
    def test_probe_darwin_available(self, mock_enclave, mock_which):
        mock_which.return_value = "/usr/bin/security"
        mock_enclave.return_value = True
        res = keychain.probe(self.env)
        self.assertEqual(res["state"], "available")
        self.assertEqual(res["path"], "/usr/bin/security")
        self.assertTrue(res["enclave"])

    def test_has_secure_enclave_non_darwin(self):
        with patch("sys.platform", "linux"):
            self.assertFalse(keychain.has_secure_enclave())

    @patch("sys.platform", "darwin")
    @patch("platform.machine")
    def test_has_secure_enclave_arm64(self, mock_machine):
        mock_machine.return_value = "arm64"
        self.assertTrue(keychain.has_secure_enclave())

    @patch("sys.platform", "darwin")
    @patch("platform.machine")
    @patch("authy_local.backends.keychain.run")
    def test_has_secure_enclave_intel_t2(self, mock_run, mock_machine):
        mock_machine.return_value = "x86_64"
        mock_run.return_value = Completed(
            returncode=0, stdout=b"Model Name: Apple T2 Security Chip\n"
        )
        self.assertTrue(keychain.has_secure_enclave())

    @patch("sys.platform", "darwin")
    @patch("platform.machine")
    @patch("authy_local.backends.keychain.run")
    def test_has_secure_enclave_intel_no_t2(self, mock_run, mock_machine):
        mock_machine.return_value = "x86_64"
        mock_run.return_value = Completed(returncode=0, stdout=b"No controller information.\n")
        self.assertFalse(keychain.has_secure_enclave())

    @patch("shutil.which")
    def test_keychain_records_missing_security_raises(self, mock_which):
        mock_which.return_value = None
        with self.assertRaises(AppError) as ctx:
            keychain.keychain_records(self.env)
        self.assertEqual(ctx.exception.exit_code, 3)

    @patch("shutil.which")
    @patch("authy_local.backends.keychain.has_secure_enclave")
    def test_keychain_enroll_and_records_roundtrip(self, mock_enclave, mock_which):
        mock_which.return_value = "/usr/bin/security"
        mock_enclave.return_value = True

        with patch("authy_local.backends.keychain.run") as mock_run:
            mock_run.return_value = Completed(returncode=0, stdout=b"")
            keychain.keychain_enroll("github_work", "JBSWY3DPEHPK3PXP", self.env)

            # Assert correct security command was invoked
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            self.assertEqual(args[0], "/usr/bin/security")
            self.assertEqual(args[1], "add-generic-password")
            self.assertIn("-s", args)
            self.assertIn("otp-local", args)
            self.assertIn("-a", args)
            self.assertIn("github_work", args)
            self.assertIn("-w", args)
            self.assertIn("JBSWY3DPEHPK3PXP", args)
            self.assertIn("-U", args)

        records = keychain.keychain_records(self.env)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0], ("github_work", "github_work [Keychain/SecureEnclave]"))

    @patch("shutil.which")
    def test_keychain_enroll_validation(self, mock_which):
        mock_which.return_value = "/usr/bin/security"

        # Invalid account label
        with self.assertRaises(AppError) as ctx:
            keychain.keychain_enroll("bad account!", "JBSWY3DPEHPK3PXP", self.env)
        self.assertEqual(ctx.exception.exit_code, 2)

        # Empty secret
        with self.assertRaises(AppError) as ctx:
            keychain.keychain_enroll("valid_account", "", self.env)
        self.assertEqual(ctx.exception.exit_code, 2)

    @patch("shutil.which")
    @patch("authy_local.backends.keychain.run")
    def test_keychain_code_golden_vector(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/security"
        # Golden secret JBSWY3DPEHPK3PXP at timestamp 1111111110 produces 358462
        mock_run.return_value = Completed(returncode=0, stdout=b"JBSWY3DPEHPK3PXP\n")

        code = keychain.keychain_code("github_work", self.env, timestamp=1111111110)
        self.assertEqual(code, "358462")

    @patch("shutil.which")
    @patch("authy_local.backends.keychain.run")
    def test_keychain_code_not_found_raises(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/security"
        mock_run.return_value = Completed(returncode=44, stdout=b"")

        with self.assertRaises(AppError) as ctx:
            keychain.keychain_code("nonexistent", self.env)
        self.assertEqual(ctx.exception.exit_code, 4)

    @patch("shutil.which")
    @patch("authy_local.backends.keychain.run")
    def test_keychain_delete_removes_from_index(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/security"
        mock_run.return_value = Completed(returncode=0, stdout=b"")

        # Enroll first
        keychain.keychain_enroll("target_account", "JBSWY3DPEHPK3PXP", self.env)
        self.assertEqual(len(keychain.keychain_records(self.env)), 1)

        # Delete
        keychain.keychain_delete("target_account", self.env)
        self.assertEqual(len(keychain.keychain_records(self.env)), 0)

    @patch("sys.platform", "darwin")
    @patch("shutil.which")
    @patch("authy_local.backends.keychain.has_secure_enclave")
    def test_doctor_report_darwin_keychain_and_tpm_na(self, mock_enclave, mock_which):
        def _which(name, path=None):
            if name in ("security", "pbcopy"):
                return f"/usr/bin/{name}"
            return None

        mock_which.side_effect = _which
        mock_enclave.return_value = True

        rep = doctor.report(self.env)
        self.assertEqual(rep["keychain"]["state"], "available")
        self.assertEqual(rep["secure-enclave"]["state"], "available")
        self.assertEqual(rep["totpm"]["state"], "not-applicable")
        self.assertEqual(rep["tpm2-totp"]["state"], "not-applicable")
        self.assertEqual(rep["tpm-device"]["state"], "not-applicable")
        self.assertEqual(rep["pbcopy"]["state"], "available")

    @patch("shutil.which")
    def test_tui_items_keychain_integration(self, mock_which):
        from authy_local import tui_items

        mock_which.return_value = "/usr/bin/security"

        with patch("authy_local.backends.keychain.run") as mock_run:
            mock_run.return_value = Completed(returncode=0, stdout=b"")
            keychain.keychain_enroll("acct_tui", "JBSWY3DPEHPK3PXP", self.env)

        recs = tui_items.records("keychain", {}, self.env)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0][0], "acct_tui")

        args = tui_items.arguments("keychain", {}, "acct_tui")
        self.assertEqual(args, ["--backend", "keychain", "--account", "acct_tui"])

        with patch("authy_local.backends.keychain.run") as mock_run:
            mock_run.return_value = Completed(returncode=0, stdout=b"")
            tui_items.remove("keychain", {}, "acct_tui", self.env)

        recs_after = tui_items.records("keychain", {}, self.env)
        self.assertEqual(len(recs_after), 0)

    @patch("authy_local.cli.has_terminal", return_value=True)
    @patch("shutil.which")
    def test_cli_keychain_show_and_enroll(self, mock_which, mock_term):
        import io

        from authy_local import cli

        mock_which.return_value = "/usr/bin/security"

        # 1. Enroll via CLI
        with patch("getpass.getpass", side_effect=["JBSWY3DPEHPK3PXP", "JBSWY3DPEHPK3PXP"]):
            with patch("authy_local.backends.keychain.run") as mock_run:
                mock_run.return_value = Completed(returncode=0, stdout=b"")
                stdout = io.StringIO()
                stdout.isatty = lambda: True
                code = cli.main(
                    ["enroll", "--backend", "keychain", "--account", "cli_test", "--apply"],
                    stdin=io.StringIO(),
                    stdout=stdout,
                    stderr=io.StringIO(),
                )
                self.assertEqual(code, 0)

        # 2. Show via CLI
        stdout = io.StringIO()
        stdout.isatty = lambda: True
        with patch("authy_local.backends.keychain.run") as mock_run:
            mock_run.return_value = Completed(returncode=0, stdout=b"JBSWY3DPEHPK3PXP\n")
            code = cli.main(
                ["show", "--backend", "keychain", "--account", "cli_test"],
                stdin=io.StringIO(),
                stdout=stdout,
                stderr=io.StringIO(),
            )
            self.assertEqual(code, 0)
            self.assertEqual(len(stdout.getvalue().strip()), 6)
            self.assertTrue(stdout.getvalue().strip().isdigit())
