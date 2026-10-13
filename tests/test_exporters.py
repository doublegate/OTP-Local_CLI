"""Tests for offline backup exporter and CLI export command."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from authy_local.cli import main
from authy_local.enrollment import OtpParameters
from authy_local.errors import AppError
from authy_local.exporters import (
    export_tokens_to_string,
    format_aegis_json,
    format_csv,
    format_uri_list,
    write_export_file,
)


class TestExporters(unittest.TestCase):
    def setUp(self):
        self.tokens = [
            OtpParameters(
                secret="JBSWY3DPEHPK3PXP",
                account="alice",
                issuer="GitHub",
                algorithm="SHA1",
                digits=6,
                period=30,
            ),
            OtpParameters(
                secret="GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ",
                account="bob",
                issuer="Google",
                algorithm="SHA256",
                digits=8,
                period=60,
            ),
        ]

    def test_format_uri_list(self):
        self.assertEqual(format_uri_list([]), "")
        res = format_uri_list(self.tokens)
        lines = [line.strip() for line in res.splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("otpauth://totp/GitHub:alice"))
        self.assertTrue(lines[1].startswith("otpauth://totp/Google:bob"))

    def test_format_aegis_json(self):
        res = format_aegis_json(self.tokens)
        data = json.loads(res)
        self.assertEqual(data["version"], 1)
        self.assertEqual(len(data["db"]["entries"]), 2)
        entry1 = data["db"]["entries"][0]
        self.assertEqual(entry1["name"], "alice")
        self.assertEqual(entry1["issuer"], "GitHub")
        self.assertEqual(entry1["info"]["secret"], "JBSWY3DPEHPK3PXP")
        self.assertEqual(entry1["info"]["digits"], 6)

    def test_format_csv(self):
        res = format_csv(self.tokens)
        lines = res.splitlines()
        self.assertEqual(lines[0], "Account,Issuer,Secret,Digits,Period,Algorithm,Type,URI")
        self.assertEqual(len(lines), 3)
        self.assertIn("alice,GitHub,JBSWY3DPEHPK3PXP,6,30,SHA1,totp", lines[1])

    def test_export_tokens_to_string_dispatch(self):
        self.assertIn("otpauth://", export_tokens_to_string(self.tokens, "uri"))
        self.assertIn('"version": 1', export_tokens_to_string(self.tokens, "aegis"))
        self.assertIn("Account,Issuer", export_tokens_to_string(self.tokens, "csv"))
        with self.assertRaises(AppError) as ctx:
            export_tokens_to_string(self.tokens, "unknown")
        self.assertEqual(ctx.exception.exit_code, 2)

    def test_write_export_file_permissions(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir) / "backup.txt"
            write_export_file("secret-content", out_path)
            self.assertTrue(out_path.exists())
            self.assertEqual(out_path.read_text(), "secret-content")
            mode = out_path.stat().st_mode & 0o777
            self.assertEqual(mode, 0o600)

    def test_write_export_file_invalid_directory(self):
        out_path = Path("/nonexistent/directory/backup.txt")
        with self.assertRaises(AppError) as ctx:
            write_export_file("content", out_path)
        self.assertEqual(ctx.exception.exit_code, 2)

    @patch("authy_local.exporters.shutil.which")
    @patch("authy_local.exporters.run")
    def test_write_export_file_gpg_encryption(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/gpg"
        mock_run.return_value = MagicMock(returncode=0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir) / "backup.gpg"
            write_export_file(
                "secret-data", out_path, encrypt_gpg="user@example.com", env={"PATH": "/bin"}
            )
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            self.assertIn("--encrypt", args)
            self.assertIn("user@example.com", args)


class TestExportCLI(unittest.TestCase):
    def invoke(self, argv: list[str]) -> tuple[int, str, str]:
        import io

        out = io.StringIO()
        err = io.StringIO()
        try:
            status = main(argv, stdin=io.StringIO(), stdout=out, stderr=err)
        except AppError as error:
            status = error.exit_code
        return status, out.getvalue(), err.getvalue()

    def test_export_missing_destination_fails(self):
        status, _, _ = self.invoke(["export"])
        self.assertEqual(status, 2)

    def test_export_stdout_without_pipe_or_tty_fails(self):
        status, _, _ = self.invoke(["export", "--stdout"])
        self.assertEqual(status, 2)

    @patch("authy_local.exporters.collect_backend_tokens")
    def test_export_stdout_with_allow_pipe_succeeds(self, mock_collect):
        mock_collect.return_value = [
            OtpParameters(secret="JBSWY3DPEHPK3PXP", account="test", issuer="Corp")
        ]
        status, out, _ = self.invoke(["export", "--stdout", "--allow-pipe", "--format", "uri"])
        self.assertEqual(status, 0)
        self.assertIn("otpauth://totp/Corp:test?secret=JBSWY3DPEHPK3PXP", out)

    @patch("authy_local.exporters.collect_backend_tokens")
    def test_export_output_file_succeeds(self, mock_collect):
        mock_collect.return_value = [
            OtpParameters(secret="JBSWY3DPEHPK3PXP", account="test", issuer="Corp")
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "export.json"
            status, _, err = self.invoke(["export", "--output", str(out_file), "--format", "aegis"])
            self.assertEqual(status, 0)
            self.assertTrue(out_file.exists())
            self.assertIn("Successfully exported 1 token(s)", err)
