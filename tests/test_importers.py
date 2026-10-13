"""Tests for bulk migration importers (Google Authenticator, Aegis, Bitwarden, URIs)."""

import base64
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from authy_local import cli
from authy_local.importers import (
    detect_and_parse_import,
    parse_aegis_json,
    parse_bitwarden_json,
    parse_google_authenticator_migration,
)


def _make_google_migration_uri(items):

    payload = b""
    for secret_bytes, name, issuer, algo, digits in items:
        f1 = bytes([0x0A, len(secret_bytes)]) + secret_bytes
        f2 = bytes([0x12, len(name.encode())]) + name.encode()
        f3 = bytes([0x1A, len(issuer.encode())]) + issuer.encode()
        f4 = bytes([0x20, algo])
        f5 = bytes([0x28, 2 if digits == 8 else 1])
        f6 = bytes([0x30, 2])  # TOTP
        param = f1 + f2 + f3 + f4 + f5 + f6
        payload += bytes([0x0A, len(param)]) + param
    b64 = base64.b64encode(payload).decode()
    return f"otpauth-migration://offline?data={b64}"


class TestImporters(unittest.TestCase):
    def test_google_authenticator_migration_parsing(self):
        items = [
            (b"12345678901234567890", "alice@example.com", "Example", 1, 6),
            (b"12345678901234567890", "bob@work.org", "Work", 2, 8),
        ]
        uri = _make_google_migration_uri(items)
        tokens = parse_google_authenticator_migration(uri)
        self.assertEqual(len(tokens), 2)

        self.assertEqual(tokens[0].account, "alice@example.com")
        self.assertEqual(tokens[0].issuer, "Example")
        self.assertEqual(tokens[0].algorithm, "SHA1")
        self.assertEqual(tokens[0].digits, 6)
        self.assertEqual(tokens[0].secret, "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ")

        self.assertEqual(tokens[1].account, "bob@work.org")
        self.assertEqual(tokens[1].issuer, "Work")
        self.assertEqual(tokens[1].algorithm, "SHA256")
        self.assertEqual(tokens[1].digits, 8)

    def test_aegis_json_parsing(self):
        aegis_data = {
            "version": 1,
            "header": {"slots": None},
            "db": {
                "version": 2,
                "entries": [
                    {
                        "type": "totp",
                        "name": "john.doe@gmail.com",
                        "issuer": "Google",
                        "info": {
                            "secret": "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ",
                            "algo": "SHA1",
                            "digits": 6,
                            "period": 30,
                        },
                    },
                    {
                        "type": "hotp",  # HOTP should be ignored
                        "name": "hotp_test",
                        "info": {"secret": "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"},
                    },
                ],
            },
        }
        tokens = parse_aegis_json(aegis_data)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].issuer, "Google")
        self.assertEqual(tokens[0].account, "john.doe@gmail.com")
        self.assertEqual(tokens[0].secret, "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ")

    def test_bitwarden_json_parsing(self):
        bw_data = {
            "items": [
                {
                    "name": "GitHub",
                    "login": {
                        "username": "octocat",
                        "totp": "otpauth://totp/GitHub:octocat?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&issuer=GitHub",
                    },
                },
                {
                    "name": "Note Only",
                    "notes": "no totp",
                },
            ]
        }
        tokens = parse_bitwarden_json(bw_data)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].issuer, "GitHub")
        self.assertEqual(tokens[0].account, "octocat")
        self.assertEqual(tokens[0].secret, "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ")

    def test_detect_and_parse_import_file_types(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Test URI list file
            uri_file = tmppath / "tokens.txt"
            uri_file.write_text(
                "otpauth://totp/AWS:admin?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&issuer=AWS\n"
                "otpauth://totp/GitHub:user?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ\n"
            )
            tokens = detect_and_parse_import(uri_file)
            self.assertEqual(len(tokens), 2)
            self.assertEqual(tokens[0].issuer, "AWS")

            # Test Bitwarden JSON file
            bw_file = tmppath / "bw.json"
            bw_file.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "name": "Cloudflare",
                                "login": {
                                    "username": "admin",
                                    "totp": "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ",
                                },
                            }
                        ]
                    }
                )
            )
            tokens = detect_and_parse_import(bw_file)
            self.assertEqual(len(tokens), 1)
            self.assertEqual(tokens[0].issuer, "Cloudflare")


class TestImportCLI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmppath = Path(self.temp_dir.name)
        self.export_file = self.tmppath / "export.txt"
        self.export_file.write_text(
            "otpauth://totp/AWS:root?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&issuer=AWS\n"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def invoke(self, args, **env):
        out, err = io.StringIO(), io.StringIO()
        out.isatty = lambda: True
        full_env = {
            "PATH": "/usr/bin:/bin",
            "HOME": "/tmp",
        } | env
        with patch.dict(os.environ, full_env, clear=True):
            status = cli.main(args, stdout=out, stderr=err)
        return status, out.getvalue(), err.getvalue()

    def test_import_dry_run_previews_without_secrets(self):
        status, out, err = self.invoke(["import", str(self.export_file), "--dry-run"])
        self.assertEqual(status, 0)
        self.assertIn("Migration preview:", out)
        self.assertIn("AWS: root", out)
        self.assertNotIn("GEZDGNBVGY3TQOJQ", out)  # Secrets must NEVER leak!

    @patch("authy_local.backends.onepassword.enroll")
    def test_import_apply_onepassword(self, mock_enroll):
        status, out, err = self.invoke(
            [
                "import",
                str(self.export_file),
                "--apply",
                "--account",
                "a" * 26,
                "--vault",
                "b" * 26,
            ]
        )
        self.assertEqual(status, 0)
        self.assertIn("Successfully imported 1 token(s)", err)
        mock_enroll.assert_called_once()
        args = mock_enroll.call_args[1]
        self.assertEqual(args["title"], "AWS: root")
        self.assertIn("otpauth://totp/AWS:root", args["otp_uri"])

    def test_import_uri_list_with_comments_and_dedup(self):
        from authy_local.importers import parse_uri_list

        content = (
            "# This is a comment\n"
            "\n"
            "otpauth://totp/GitHub:user1?secret=JBSWY3DPEHPK3PXP\n"
            "# Another comment\n"
            "otpauth://totp/GitHub:user1?secret=JBSWY3DPEHPK3PXP\n"  # Duplicate secret
            "steam://totp/Steam:valve?secret=GEZDGNBVGY3TQOJQ\n"
        )
        tokens = parse_uri_list(content)
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0].account, "user1")
        self.assertEqual(tokens[0].issuer, "GitHub")
        self.assertEqual(tokens[1].algorithm, "STEAM")
        self.assertEqual(tokens[1].digits, 5)

    def test_import_cli_format_uri_list(self):
        uri_file = self.tmppath / "uris.txt"
        uri_file.write_text(
            "# Comment line\notpauth://totp/TestService:user@domain.com?secret=JBSWY3DPEHPK3PXP\n"
        )
        status, out, err = self.invoke(["import", str(uri_file), "--format", "uri-list"])
        self.assertEqual(status, 0)
        self.assertIn("Migration preview: found 1 TOTP token(s)", out)
        self.assertIn("TestService: user@domain.com", out)
