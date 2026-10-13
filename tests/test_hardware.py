"""Tests for hardware token backends (YubiKey OATH and TPM 2.0)."""

import unittest
from unittest.mock import patch

from authy_local import doctor
from authy_local.backends.hardware import (
    probe_hardware,
    yubikey_code,
    yubikey_records,
)
from authy_local.errors import AppError
from authy_local.processes import Completed


class TestHardwareBackends(unittest.TestCase):
    def setUp(self):

        self.env = {"PATH": "/usr/bin:/bin"}

    @patch("shutil.which")
    def test_probe_hardware_detects_tools(self, mock_which):
        def _which(name, path=None):
            if name == "ykman":
                return "/usr/bin/ykman"
            return None

        mock_which.side_effect = _which
        result = probe_hardware(self.env)
        self.assertEqual(result["yubikey"]["state"], "available")
        self.assertEqual(result["yubikey"]["path"], "/usr/bin/ykman")
        self.assertEqual(result["tpm2-totp"]["state"], "missing")

    @patch("shutil.which")
    @patch("authy_local.backends.hardware.run")
    def test_yubikey_records_parsing(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/ykman"
        mock_run.return_value = Completed(
            returncode=0,
            stdout=b"AWS:admin\nGitHub:octocat\n",
        )
        records = yubikey_records(self.env)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0], ("AWS:admin", "AWS:admin [YubiKey]"))
        self.assertEqual(records[1], ("GitHub:octocat", "GitHub:octocat [YubiKey]"))

    @patch("shutil.which")
    @patch("authy_local.backends.hardware.run")
    def test_yubikey_code_retrieval(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/ykman"
        mock_run.return_value = Completed(
            returncode=0,
            stdout=b"123456\n",
        )
        code = yubikey_code("AWS:admin", self.env)
        self.assertEqual(code, "123456")

    @patch("shutil.which")
    def test_yubikey_missing_tool_raises_app_error(self, mock_which):
        mock_which.return_value = None
        with self.assertRaises(AppError) as ctx:
            yubikey_records(self.env)
        self.assertEqual(ctx.exception.exit_code, 3)

    def test_doctor_report_includes_hardware(self):
        rep = doctor.report(self.env)
        self.assertIn("yubikey", rep)
        self.assertIn("tpm2-totp", rep)
        self.assertIn(rep["yubikey"]["state"], ("available", "missing"))

    @patch("shutil.which")
    @patch("authy_local.backends.hardware.run")
    def test_tpm2_totp_code_retrieval(self, mock_run, mock_which):
        from authy_local.backends.hardware import tpm2_totp_code, tpm2_totp_records

        mock_which.return_value = "/usr/bin/tpm2-totp"
        mock_run.return_value = Completed(returncode=0, stdout=b"654321\n")
        recs = tpm2_totp_records(self.env)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0][0], "default")
        code = tpm2_totp_code("default", self.env)
        self.assertEqual(code, "654321")

    @patch("shutil.which")
    def test_tpm2_totp_missing_raises_error(self, mock_which):
        from authy_local.backends.hardware import tpm2_totp_code, tpm2_totp_records

        mock_which.return_value = None
        with self.assertRaises(AppError) as ctx:
            tpm2_totp_records(self.env)
        self.assertEqual(ctx.exception.exit_code, 3)

        with self.assertRaises(AppError) as ctx:
            tpm2_totp_code("default", self.env)
        self.assertEqual(ctx.exception.exit_code, 3)
