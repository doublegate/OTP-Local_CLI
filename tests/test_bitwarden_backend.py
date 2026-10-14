"""Comprehensive synthetic test suite for Bitwarden / Vaultwarden CLI backend."""

import json
import time
import unittest
from unittest.mock import patch

from authy_local import cli, doctor
from authy_local.backends import bitwarden
from authy_local.backends.bitwarden import BitwardenSessionManager, child_environment
from authy_local.errors import AppError
from authy_local.processes import Completed


class TestBitwardenBackend(unittest.TestCase):
    def setUp(self):
        self.env = {
            "PATH": "/usr/bin:/bin",
            "HOME": "/home/user",
        }
        bitwarden.session_manager.clear_session()

    def tearDown(self):
        bitwarden.session_manager.clear_session()

    # -------------------------------------------------------------------------
    # 1. Probing & Capability Reporting
    # -------------------------------------------------------------------------

    @patch("shutil.which", return_value=None)
    def test_probe_missing_bw(self, mock_which):
        res = bitwarden.probe(self.env)
        self.assertEqual(res["state"], "missing")

    @patch("shutil.which", return_value="/usr/bin/bw")
    @patch("authy_local.backends.bitwarden.run")
    def test_probe_available_locked(self, mock_run, mock_which):
        def fake_run(cmd, **kwargs):
            if "--version" in cmd:
                return Completed(0, b"2024.1.0\n")
            if "status" in cmd:
                return Completed(
                    0,
                    json.dumps({"status": "locked", "userEmail": "test@example.com"}).encode(
                        "utf-8"
                    ),
                )
            return Completed(1, b"")

        mock_run.side_effect = fake_run
        res = bitwarden.probe(self.env)
        self.assertEqual(res["state"], "available")
        self.assertEqual(res["version"], "2024.1.0")
        self.assertEqual(res["vault_status"], "locked")
        self.assertFalse(res["unlocked"])

    @patch("shutil.which", return_value="/usr/bin/bw")
    @patch("authy_local.backends.bitwarden.run")
    def test_probe_available_unlocked(self, mock_run, mock_which):
        def fake_run(cmd, **kwargs):
            if "--version" in cmd:
                return Completed(0, b"2024.1.0\n")
            if "status" in cmd:
                return Completed(
                    0,
                    json.dumps({"status": "unlocked", "userEmail": "test@example.com"}).encode(
                        "utf-8"
                    ),
                )
            return Completed(1, b"")

        mock_run.side_effect = fake_run
        res = bitwarden.probe(self.env)
        self.assertEqual(res["state"], "available")
        self.assertEqual(res["vault_status"], "unlocked")
        self.assertTrue(res["unlocked"])

    def test_doctor_report_includes_bitwarden(self):
        with patch.object(
            bitwarden, "probe", return_value={"state": "available", "version": "2024.1.0"}
        ):
            rep = doctor.report(self.env)
            self.assertIn("bitwarden", rep)
            self.assertEqual(rep["bitwarden"]["state"], "available")

    # -------------------------------------------------------------------------
    # 2. Session Manager & Volatile Memory Security
    # -------------------------------------------------------------------------

    def test_session_manager_set_get_and_clear(self):
        mgr = BitwardenSessionManager()
        self.assertIsNone(mgr.get_session())
        self.assertFalse(mgr.is_unlocked())

        with self.assertRaises(AppError):
            mgr.set_session("")

        raw_session = "BW_SESSION_TEST_SECRET_KEY_1234567890"
        mgr.set_session(raw_session, ttl=100.0)
        self.assertTrue(mgr.is_unlocked())
        self.assertEqual(mgr.get_session(), raw_session)

        # Clear session and verify memory zeroing
        mgr.clear_session()
        self.assertIsNone(mgr.get_session())
        self.assertFalse(mgr.is_unlocked())

    def test_session_manager_expiration(self):
        mgr = BitwardenSessionManager()
        mgr.set_session("BW_SESSION_EXPIRING_KEY_12345", ttl=0.05)
        self.assertEqual(mgr.get_session(), "BW_SESSION_EXPIRING_KEY_12345")
        time.sleep(0.06)
        self.assertIsNone(mgr.get_session())

    def test_session_manager_env_fallback(self):
        mgr = BitwardenSessionManager()
        env_with_session = {"BW_SESSION": "ENV_SESSION_KEY_ABCDEFGHIJ"}
        self.assertEqual(mgr.get_session(env_with_session), "ENV_SESSION_KEY_ABCDEFGHIJ")

    @patch("shutil.which", return_value="/usr/bin/bw")
    @patch("authy_local.backends.bitwarden.run")
    def test_session_manager_unlock_success(self, mock_run, mock_which):
        mgr = BitwardenSessionManager()
        session_token = "GENERATED_SESSION_TOKEN_1234567890"

        def fake_run(cmd, input_data=None, stdin=None, **kwargs):
            self.assertIn("unlock", cmd)
            self.assertIn("--raw", cmd)
            # Master password must be passed on stdin/input_data, never on commandline
            data = input_data if input_data is not None else stdin
            self.assertEqual(data, b"MyMasterPassword123!")
            return Completed(0, session_token.encode("utf-8"))

        mock_run.side_effect = fake_run
        unlocked_token = mgr.unlock("MyMasterPassword123!", self.env)
        self.assertEqual(unlocked_token, session_token)
        self.assertEqual(mgr.get_session(), session_token)

    @patch("shutil.which", return_value="/usr/bin/bw")
    @patch("authy_local.backends.bitwarden.run")
    def test_session_manager_unlock_failure(self, mock_run, mock_which):
        mgr = BitwardenSessionManager()
        mock_run.return_value = Completed(1, b"")
        with self.assertRaises(AppError) as cm:
            mgr.unlock("WrongPassword", self.env)
        self.assertEqual(cm.exception.exit_code, 4)
        self.assertFalse(mgr.is_unlocked())

    @patch("shutil.which", return_value="/usr/bin/bw")
    @patch("authy_local.backends.bitwarden.run")
    def test_session_manager_lock(self, mock_run, mock_which):
        mgr = BitwardenSessionManager()
        mgr.set_session("ACTIVE_SESSION_KEY_12345")
        mock_run.return_value = Completed(0, b"Vault locked.\n")

        mgr.lock(self.env)
        self.assertFalse(mgr.is_unlocked())
        self.assertIsNone(mgr.get_session())
        mock_run.assert_called_once()
        self.assertIn("lock", mock_run.call_args[0][0])

    def test_child_environment_sanitization_and_injection(self):
        dirty_env = {
            "PATH": "/bin:/usr/bin",
            "BASH_FUNC_foo%%": "() { :; }",
            "OP_SESSION_my": "unwanted_op_token",
            "BW_SESSION": "old_session_to_replace",
            "USER": "operator",
        }
        bitwarden.session_manager.set_session("NEW_BW_SESSION_12345")
        clean = child_environment(dirty_env)
        self.assertNotIn("BASH_FUNC_foo%%", clean)
        self.assertNotIn("OP_SESSION_my", clean)
        self.assertEqual(clean["BW_SESSION"], "NEW_BW_SESSION_12345")
        self.assertEqual(clean["BW_NO_TELEMETRY"], "true")
        self.assertEqual(clean["USER"], "operator")

    # -------------------------------------------------------------------------
    # 3. Item Enumeration & Search
    # -------------------------------------------------------------------------

    @patch("shutil.which", return_value="/usr/bin/bw")
    @patch("authy_local.backends.bitwarden.run")
    def test_list_items_and_records(self, mock_run, mock_which):
        sample_vault = [
            {
                "id": "item-111",
                "name": "GitHub",
                "login": {"username": "octocat", "totp": "JBSWY3DPEHPK3PXP"},
            },
            {
                "id": "item-222",
                "name": "AWS Console",
                "login": {
                    "username": "admin",
                    "totp": "otpauth://totp/AWS:admin?secret=JBSWY3DPEHPK3PXP",
                },
            },
            {
                "id": "item-333",
                "name": "Note Only",
                "login": {"username": "nouser"},  # No TOTP, must be filtered
            },
        ]
        mock_run.return_value = Completed(0, json.dumps(sample_vault).encode("utf-8"))

        items = bitwarden.list_items(self.env)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["id"], "item-111")
        self.assertEqual(items[1]["id"], "item-222")

        records = bitwarden.bitwarden_records(self.env)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0], ("item-222", "AWS Console (admin) [Bitwarden]"))
        self.assertEqual(records[1], ("item-111", "GitHub (octocat) [Bitwarden]"))

    @patch("shutil.which", return_value="/usr/bin/bw")
    @patch("authy_local.backends.bitwarden.run")
    def test_list_items_search_flag(self, mock_run, mock_which):
        mock_run.return_value = Completed(0, b"[]")
        bitwarden.list_items(self.env, search="GitHub")
        cmd = mock_run.call_args[0][0]
        self.assertIn("--search", cmd)
        self.assertIn("GitHub", cmd)

    # -------------------------------------------------------------------------
    # 4. TOTP Code Retrieval & Step Caching
    # -------------------------------------------------------------------------

    @patch("shutil.which", return_value="/usr/bin/bw")
    @patch("authy_local.backends.bitwarden.run")
    def test_bitwarden_code_native_get_totp(self, mock_run, mock_which):
        mock_run.return_value = Completed(0, b"842109\n")
        code = bitwarden.bitwarden_code("item-111", self.env)
        self.assertEqual(code, "842109")

        # Second call within same step should use in-process cache without running subprocess
        mock_run.reset_mock()
        cached_code = bitwarden.bitwarden_code("item-111", self.env)
        self.assertEqual(cached_code, "842109")
        mock_run.assert_not_called()

    @patch("shutil.which", return_value="/usr/bin/bw")
    @patch("authy_local.backends.bitwarden.run")
    def test_bitwarden_code_fallback_to_get_item(self, mock_run, mock_which):
        def fake_run(cmd, **kwargs):
            if "get" in cmd and "totp" in cmd:
                return Completed(1, b"")
            if "get" in cmd and "item" in cmd:
                item_obj = {
                    "id": "item-999",
                    "name": "LocalCalc",
                    "login": {"totp": "JBSWY3DPEHPK3PXP"},
                }
                return Completed(0, json.dumps(item_obj).encode("utf-8"))
            return Completed(1, b"")

        mock_run.side_effect = fake_run
        # Timestamp 0 -> deterministic code for base32 secret JBSWY3DPEHPK3PXP is 282760
        code = bitwarden.bitwarden_code("item-999", self.env, timestamp=0.0)
        self.assertEqual(code, "282760")

    def test_bitwarden_code_validation_errors(self):
        with self.assertRaises(AppError) as cm:
            bitwarden.bitwarden_code("", self.env)
        self.assertEqual(cm.exception.exit_code, 2)

        with patch("shutil.which", return_value=None):
            with self.assertRaises(AppError) as cm:
                bitwarden.bitwarden_code("valid-id", self.env)
            self.assertEqual(cm.exception.exit_code, 3)

    # -------------------------------------------------------------------------
    # 5. Enrollment & Deletion
    # -------------------------------------------------------------------------

    @patch("shutil.which", return_value="/usr/bin/bw")
    @patch("authy_local.backends.bitwarden.run")
    def test_bitwarden_enroll_success(self, mock_run, mock_which):
        def fake_run(cmd, input_data=None, stdin=None, **kwargs):
            self.assertIn("create", cmd)
            self.assertIn("item", cmd)
            data = input_data if input_data is not None else stdin
            assert data is not None
            payload = json.loads(data.decode("utf-8"))
            self.assertEqual(payload["name"], "GitLab")
            self.assertEqual(payload["login"]["totp"], "JBSWY3DPEHPK3PXP")
            return Completed(0, json.dumps({"id": "created-id-456"}).encode("utf-8"))

        mock_run.side_effect = fake_run
        item_id = bitwarden.bitwarden_enroll("GitLab", "JBSWY3DPEHPK3PXP", self.env)
        self.assertEqual(item_id, "created-id-456")

    @patch("shutil.which", return_value="/usr/bin/bw")
    @patch("authy_local.backends.bitwarden.run")
    @patch("authy_local.deletion_audit.record")
    def test_bitwarden_delete(self, mock_audit, mock_run, mock_which):
        mock_run.return_value = Completed(0, b"Deleted item.\n")
        bitwarden.bitwarden_delete("item-111", self.env)
        mock_audit.assert_called_once_with("bitwarden")
        mock_run.assert_called_once()
        self.assertIn("delete", mock_run.call_args[0][0])
        self.assertIn("item-111", mock_run.call_args[0][0])

    # -------------------------------------------------------------------------
    # 6. Exporter & Auditor Token Collection
    # -------------------------------------------------------------------------

    @patch("authy_local.backends.bitwarden.list_items")
    def test_collect_tokens(self, mock_list):
        mock_list.return_value = [
            {
                "id": "1",
                "name": "ServiceA",
                "login": {
                    "username": "alice",
                    "totp": "otpauth://totp/ServiceA:alice?secret=JBSWY3DPEHPK3PXP",
                },
            }
        ]
        tokens = bitwarden.collect_tokens(self.env)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].issuer, "ServiceA")
        self.assertEqual(tokens[0].account, "alice")
        self.assertEqual(tokens[0].secret, "JBSWY3DPEHPK3PXP")

    # -------------------------------------------------------------------------
    # 7. CLI End-to-End Command Routing
    # -------------------------------------------------------------------------

    @patch("authy_local.cli.has_terminal", return_value=True)
    @patch("authy_local.backends.bitwarden.bitwarden_code", return_value="123456")
    def test_cli_show_bitwarden(self, mock_code, mock_term):
        import io

        out = io.StringIO()
        out.isatty = lambda: True
        err = io.StringIO()

        code = cli.main(["show", "--backend", "bitwarden", "my-account"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().strip(), "123456")
        mock_code.assert_called_once()

    @patch("authy_local.cli.has_terminal", return_value=True)
    @patch("authy_local.backends.bitwarden.bitwarden_records")
    @patch("authy_local.backends.bitwarden.bitwarden_code", return_value="654321")
    @patch("authy_local.interaction.choose_records", return_value="item-123")
    def test_cli_select_bitwarden(self, mock_choose, mock_code, mock_records, mock_term):
        import io

        mock_records.return_value = [("item-123", "Account 123 [Bitwarden]")]
        out = io.StringIO()
        out.isatty = lambda: True
        err = io.StringIO()

        code = cli.main(["select", "--backend", "bitwarden"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().strip(), "654321")
        mock_code.assert_called_once_with("item-123", unittest.mock.ANY)

    @patch("authy_local.cli.has_terminal", return_value=True)
    @patch("authy_local.backends.bitwarden.bitwarden_enroll", return_value="new-id-999")
    def test_cli_enroll_bitwarden(self, mock_enroll, mock_term):
        import io

        out = io.StringIO()
        out.isatty = lambda: True
        err = io.StringIO()

        with patch("getpass.getpass", side_effect=["JBSWY3DPEHPK3PXP", "JBSWY3DPEHPK3PXP"]):
            code = cli.main(
                ["enroll", "--backend", "bitwarden", "--title", "NewService", "--apply"],
                stdout=out,
                stderr=err,
            )
            self.assertEqual(code, 0)
            mock_enroll.assert_called_once_with("NewService", "JBSWY3DPEHPK3PXP", unittest.mock.ANY)

    @patch("shutil.which", return_value="/usr/bin/bw")
    @patch("authy_local.backends.bitwarden.run")
    def test_bitwarden_large_vault_buffer_overflow_prevention(self, mock_run, mock_which):
        large_items = [
            {
                "id": f"item-{i}",
                "name": f"Enterprise Account {i}",
                "login": {"username": f"user{i}@example.com", "totp": "JBSWY3DPEHPK3PXP"},
                "notes": "x" * 800,
            }
            for i in range(1500)
        ]
        raw_json = json.dumps(large_items).encode("utf-8")
        self.assertGreater(len(raw_json), 1024 * 1024)

        def check_run(cmd, stdout_cap=0, **kwargs):
            self.assertGreaterEqual(stdout_cap, 2 * 1024 * 1024)
            return Completed(0, raw_json)

        mock_run.side_effect = check_run
        items = bitwarden.list_items(self.env)
        self.assertEqual(len(items), 1500)

    def test_bitwarden_alias_bw_list_items(self):
        self.assertIs(bitwarden._bw_list_items, bitwarden.list_items)

    @patch("shutil.which", return_value="/usr/bin/bw")
    @patch("authy_local.backends.bitwarden.run")
    def test_bitwarden_unlock_uses_input_data_keyword(self, mock_run, mock_which):
        mock_run.return_value = Completed(0, b"session-token-xyz")
        mgr = BitwardenSessionManager()
        mgr.unlock("MasterPass!", self.env)
        self.assertIn("input_data", mock_run.call_args[1])
        self.assertNotIn("stdin", mock_run.call_args[1])
        self.assertEqual(mock_run.call_args[1]["input_data"], b"MasterPass!")

    @patch("shutil.which", return_value="/usr/bin/bw")
    @patch("authy_local.backends.bitwarden.run")
    def test_bitwarden_enroll_uses_input_data_keyword(self, mock_run, mock_which):
        mock_run.return_value = Completed(0, json.dumps({"id": "item-999"}).encode("utf-8"))
        bitwarden.bitwarden_enroll("ServiceX", "JBSWY3DPEHPK3PXP", self.env)
        self.assertIn("input_data", mock_run.call_args[1])
        self.assertNotIn("stdin", mock_run.call_args[1])


if __name__ == "__main__":
    unittest.main()
