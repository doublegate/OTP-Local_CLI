"""Tests for KeePassXC KDBX4 database backend and session manager."""

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from authy_local import cli, doctor
from authy_local.backends import keepass
from authy_local.backends.keepass import KeePassSessionManager, child_environment
from authy_local.cache import clear_cache
from authy_local.errors import AppError
from authy_local.processes import Completed

SAMPLE_KEEPASS_XML = """<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<KeePassFile>
  <Root>
    <Group>
      <Name>Root</Name>
      <Entry>
        <String>
          <Key>Title</Key>
          <Value>GitHub</Value>
        </String>
        <String>
          <Key>UserName</Key>
          <Value>octocat</Value>
        </String>
        <String>
          <Key>otp</Key>
          <Value>JBSWY3DPEHPK3PXP</Value>
        </String>
      </Entry>
      <Entry>
        <String>
          <Key>Title</Key>
          <Value>AWS Console</Value>
        </String>
        <String>
          <Key>UserName</Key>
          <Value>admin</Value>
        </String>
        <String>
          <Key>otp</Key>
          <Value>otpauth://totp/AWS:admin?secret=JBSWY3DPEHPK3PXP</Value>
        </String>
      </Entry>
      <Entry>
        <String>
          <Key>Title</Key>
          <Value>NoOtpEntry</Value>
        </String>
      </Entry>
    </Group>
  </Root>
</KeePassFile>"""


class TestKeePassBackend(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.kdbx"
        self.env = {
            "PATH": "/usr/bin:/bin",
            "HOME": self.temp_dir.name,
            "KEEPASS_DB_PATH": str(self.db_path),
            "FAKE_KEEPASS_XML": SAMPLE_KEEPASS_XML,
        }
        keepass.session_manager.clear()
        clear_cache()

    def tearDown(self):
        keepass.session_manager.clear()
        clear_cache()
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. Probing & Capability Reporting
    # -------------------------------------------------------------------------

    @patch("shutil.which", return_value=None)
    def test_probe_missing_when_no_cli_and_no_db(self, mock_which):
        res = keepass.probe(self.env)
        self.assertEqual(res["state"], "missing")
        self.assertFalse(res["db_exists"])

    @patch("shutil.which", return_value="/usr/bin/keepassxc-cli")
    @patch("authy_local.backends.keepass.run")
    def test_probe_available_with_cli(self, mock_run, mock_which):
        mock_run.return_value = Completed(0, b"2.7.9\n")
        res = keepass.probe(self.env)
        self.assertEqual(res["state"], "available")
        self.assertEqual(res["version"], "2.7.9")

    def test_doctor_report_includes_keepass(self):
        with patch.object(
            keepass, "probe", return_value={"state": "available", "version": "2.7.9"}
        ):
            rep = doctor.report(self.env)
            self.assertIn("keepass", rep)
            self.assertEqual(rep["keepass"]["state"], "available")

    # -------------------------------------------------------------------------
    # 2. Session Manager & Volatile Memory Lifecycle
    # -------------------------------------------------------------------------

    def test_session_manager_set_get_and_clear(self):
        mgr = KeePassSessionManager()
        self.assertIsNone(mgr.get_password())
        self.assertFalse(mgr.is_unlocked())

        mgr.set_credentials("MyMasterPassword123!", keyfile="/path/to/keyfile.key", ttl=100.0)
        self.assertTrue(mgr.is_unlocked())
        self.assertEqual(mgr.get_password(), "MyMasterPassword123!")
        self.assertEqual(mgr.get_keyfile(), "/path/to/keyfile.key")

        # Zeroize and clear
        mgr.clear()
        self.assertIsNone(mgr.get_password())
        self.assertIsNone(mgr.get_keyfile())
        self.assertFalse(mgr.is_unlocked())

    def test_session_manager_expiration(self):
        mgr = KeePassSessionManager()
        mgr.set_credentials("ExpiringPassword", ttl=0.05)
        self.assertEqual(mgr.get_password(), "ExpiringPassword")
        time.sleep(0.06)
        self.assertIsNone(mgr.get_password())
        self.assertFalse(mgr.is_unlocked())

    def test_child_environment_sanitization(self):
        dirty_env = {
            "PATH": "/bin:/usr/bin",
            "BASH_FUNC_test%%": "() { :; }",
            "OP_SESSION": "secret",
            "HOME": "/home/user",
        }
        clean = child_environment(dirty_env)
        self.assertNotIn("BASH_FUNC_test%%", clean)
        self.assertNotIn("OP_SESSION", clean)
        self.assertEqual(clean["QT_QPA_PLATFORM"], "offscreen")

    # -------------------------------------------------------------------------
    # 3. Item Enumeration
    # -------------------------------------------------------------------------

    def test_keepass_records_from_xml(self):
        records = keepass.keepass_records(self.env)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0], ("AWS Console", "AWS Console (admin) [KeePassXC]"))
        self.assertEqual(records[1], ("GitHub", "GitHub (octocat) [KeePassXC]"))

    @patch("shutil.which", return_value="/usr/bin/keepassxc-cli")
    @patch("authy_local.backends.keepass.run")
    def test_keepass_records_from_cli(self, mock_run, mock_which):
        # Create dummy file so target_db.is_file() is True
        self.db_path.write_bytes(b"dummy kdbx")
        mock_run.return_value = Completed(0, b"Root/GitHub\nRoot/Google\n")

        records = keepass.keepass_records(self.env, db_path=self.db_path)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0], ("Root/GitHub", "Root/GitHub [KeePassXC]"))
        self.assertEqual(records[1], ("Root/Google", "Root/Google [KeePassXC]"))

    # -------------------------------------------------------------------------
    # 4. TOTP Retrieval & Step Caching
    # -------------------------------------------------------------------------

    def test_keepass_code_from_xml_fallback(self):
        # Timestamp 0.0 -> deterministic TOTP code for JBSWY3DPEHPK3PXP is 282760
        code = keepass.keepass_code("GitHub", self.env, timestamp=0.0)
        self.assertEqual(code, "282760")

        # Second call uses in-process step cache
        cached = keepass.keepass_code("GitHub", self.env, timestamp=0.0)
        self.assertEqual(cached, "282760")

    @patch("shutil.which", return_value="/usr/bin/keepassxc-cli")
    @patch("authy_local.backends.keepass.run")
    def test_keepass_code_from_cli(self, mock_run, mock_which):
        self.db_path.write_bytes(b"dummy kdbx")
        mock_run.return_value = Completed(0, b"918273\n")

        code = keepass.keepass_code("GitHub", self.env, db_path=self.db_path)
        self.assertEqual(code, "918273")

    def test_keepass_code_validation_errors(self):
        with self.assertRaises(AppError) as cm:
            keepass.keepass_code("", self.env)
        self.assertEqual(cm.exception.exit_code, 2)

        with self.assertRaises(AppError) as cm:
            keepass.keepass_code("NonExistentEntry", self.env)
        self.assertEqual(cm.exception.exit_code, 4)

    # -------------------------------------------------------------------------
    # 5. Enrollment & Deletion
    # -------------------------------------------------------------------------

    @patch("shutil.which", return_value="/usr/bin/keepassxc-cli")
    @patch("authy_local.backends.keepass.run")
    def test_keepass_enroll_via_cli(self, mock_run, mock_which):
        mock_run.return_value = Completed(0, b"Entry added successfully.\n")
        keepass.keepass_enroll("NewEntry", "JBSWY3DPEHPK3PXP", self.env, db_path=self.db_path)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertIn("add", cmd)
        self.assertIn("NewEntry", cmd)

    def test_keepass_enroll_validation_errors(self):
        with self.assertRaises(AppError) as cm:
            keepass.keepass_enroll("", "JBSWY3DPEHPK3PXP", self.env)
        self.assertEqual(cm.exception.exit_code, 2)

    @patch("shutil.which", return_value="/usr/bin/keepassxc-cli")
    @patch("authy_local.backends.keepass.run")
    @patch("authy_local.deletion_audit.record")
    def test_keepass_delete(self, mock_audit, mock_run, mock_which):
        self.db_path.write_bytes(b"dummy kdbx")
        mock_run.return_value = Completed(0, b"Entry removed.\n")

        keepass.keepass_delete("OldEntry", self.env, db_path=self.db_path)
        mock_audit.assert_called_once_with("keepass")
        mock_run.assert_called_once()
        self.assertIn("rm", mock_run.call_args[0][0])
        self.assertIn("OldEntry", mock_run.call_args[0][0])

    # -------------------------------------------------------------------------
    # 6. Exporter & Auditor Token Collection
    # -------------------------------------------------------------------------

    def test_collect_tokens(self):
        tokens = keepass.collect_tokens(self.env)
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0].issuer, "GitHub")
        self.assertEqual(tokens[0].account, "octocat")
        self.assertEqual(tokens[0].secret, "JBSWY3DPEHPK3PXP")

    # -------------------------------------------------------------------------
    # 7. CLI End-to-End Command Routing
    # -------------------------------------------------------------------------

    @patch("authy_local.cli.has_terminal", return_value=True)
    @patch("authy_local.backends.keepass.keepass_code", return_value="555666")
    def test_cli_show_keepass(self, mock_code, mock_term):
        import io

        out = io.StringIO()
        out.isatty = lambda: True
        err = io.StringIO()

        code = cli.main(["show", "--backend", "keepass", "GitHub"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().strip(), "555666")
        mock_code.assert_called_once()

    @patch("authy_local.cli.has_terminal", return_value=True)
    @patch("authy_local.backends.keepass.keepass_records")
    @patch("authy_local.backends.keepass.keepass_code", return_value="777888")
    @patch("authy_local.interaction.choose_records", return_value="GitHub")
    def test_cli_select_keepass(self, mock_choose, mock_code, mock_records, mock_term):
        import io

        mock_records.return_value = [("GitHub", "GitHub (octocat) [KeePassXC]")]
        out = io.StringIO()
        out.isatty = lambda: True
        err = io.StringIO()

        code = cli.main(["select", "--backend", "keepass"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().strip(), "777888")
        mock_code.assert_called_once_with("GitHub", unittest.mock.ANY)

    @patch("authy_local.cli.has_terminal", return_value=True)
    @patch("authy_local.backends.keepass.keepass_enroll")
    def test_cli_enroll_keepass(self, mock_enroll, mock_term):
        import io

        out = io.StringIO()
        out.isatty = lambda: True
        err = io.StringIO()

        with patch("getpass.getpass", side_effect=["JBSWY3DPEHPK3PXP", "JBSWY3DPEHPK3PXP"]):
            code = cli.main(
                ["enroll", "--backend", "keepass", "--title", "Discord", "--apply"],
                stdout=out,
                stderr=err,
            )
            self.assertEqual(code, 0)
            mock_enroll.assert_called_once_with("Discord", "JBSWY3DPEHPK3PXP", unittest.mock.ANY)


if __name__ == "__main__":
    unittest.main()
