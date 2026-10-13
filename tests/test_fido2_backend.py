"""Tests for FIDO2 CTAP 2.1 hardware security key backend."""

import hashlib
import hmac
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from authy_local import deletion_audit, doctor
from authy_local.backends import fido2
from authy_local.enrollment import OtpParameters, generate_totp_code
from authy_local.errors import AppError


class MockCtapHidDevice:
    """Synthetic CTAP 2.1 HID device emulator."""

    def __init__(
        self,
        has_hmac_secret: bool = True,
        required_pin: str | None = None,
        simulate_timeout: bool = False,
    ):
        self.has_hmac_secret = has_hmac_secret
        self.required_pin = required_pin
        self.simulate_timeout = simulate_timeout
        self.hardware_master_secret = os.urandom(32)
        self.enrolled_creds: dict[bytes, bytes] = {}

        self.info = MagicMock()
        self.info.extensions = ["hmac-secret"] if has_hmac_secret else []
        self.info.options = {"clientPin": required_pin is not None}
        self.ctap = MagicMock()
        self.ctap.info = self.info

    def mock_enroll(
        self, account: str, salt: bytes, pin: str | None = None
    ) -> tuple[bytes, bytes, str]:
        if self.simulate_timeout:
            raise TimeoutError("Touch timeout")
        if self.required_pin and pin != self.required_pin:
            raise AppError(4)

        cred_id = hashlib.sha256(f"CRED:{account}".encode()).digest()[:16]
        # Authenticator binds a secret to the cred_id
        cred_secret = hmac.new(self.hardware_master_secret, cred_id, hashlib.sha256).digest()
        self.enrolled_creds[cred_id] = cred_secret

        # Compute HMAC-SHA-256(cred_secret, salt)
        hmac_output = hmac.new(cred_secret, salt, hashlib.sha256).digest()
        aaguid = "000102030405060708090a0b0c0d0e0f"
        return cred_id, hmac_output, aaguid

    def mock_assertion(self, cred_id: bytes, salt: bytes, pin: str | None = None) -> bytes:
        if self.simulate_timeout:
            raise TimeoutError("Touch timeout")
        if self.required_pin and pin != self.required_pin:
            raise AppError(5)

        cred_secret = self.enrolled_creds.get(cred_id)
        if not cred_secret:
            raise AppError(5)

        return hmac.new(cred_secret, salt, hashlib.sha256).digest()


class TestFido2Backend(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.env = {
            "XDG_STATE_HOME": self.tmpdir.name,
            "HOME": self.tmpdir.name,
        }
        self.mock_dev = MockCtapHidDevice(has_hmac_secret=True)
        fido2._set_device_override([self.mock_dev])

    def tearDown(self) -> None:
        fido2._set_device_override(None)
        self.tmpdir.cleanup()

    def test_probe_available_with_device(self) -> None:
        res = fido2.probe(self.env)
        self.assertEqual(res["state"], "available")
        self.assertEqual(res["device_count"], 1)
        self.assertTrue(res["hmac_secret"])

    def test_probe_missing_when_no_devices(self) -> None:
        fido2._set_device_override([])
        res = fido2.probe(self.env)
        self.assertEqual(res["state"], "missing")
        self.assertEqual(res["device_count"], 0)

    def test_probe_missing_when_device_lacks_hmac_secret(self) -> None:
        dev = MockCtapHidDevice(has_hmac_secret=False)
        fido2._set_device_override([dev])
        res = fido2.probe(self.env)
        self.assertEqual(res["state"], "missing")
        self.assertFalse(res["hmac_secret"])

    def test_fido2_enroll_and_code_golden_vector(self) -> None:
        sample_secret = "JBSWY3DPEHPK3PXP"
        account = "github"

        # Golden vector reference
        params = OtpParameters(secret=sample_secret, account=account)
        expected_code, _ = generate_totp_code(params, timestamp=1234567.0)

        # 1. Enroll
        fido2.fido2_enroll(account, sample_secret, self.env)

        # 2. Check vault file on disk (assert plaintext seed is NEVER persisted)
        vault_path = Path(self.tmpdir.name) / "authy-local" / "fido2_vault.json"
        self.assertTrue(vault_path.is_file())
        raw_vault = vault_path.read_text(encoding="utf-8")
        self.assertNotIn(sample_secret, raw_vault)

        # 3. Check records listing
        records = fido2.fido2_records(self.env)
        self.assertEqual(records, [("github", "github [FIDO2]")])

        # 4. Generate code and compare against golden vector
        code = fido2.fido2_code(account, self.env, timestamp=1234567.0)
        self.assertEqual(code, expected_code)

    def test_fido2_touch_callback(self) -> None:
        account = "aws"
        secret = "MFRGGZDFMZTWQ2LK"
        touch_called = []

        def on_touch():
            touch_called.append(True)

        fido2.fido2_enroll(account, secret, self.env, touch_callback=on_touch)
        self.assertEqual(len(touch_called), 1)

        touch_called.clear()
        fido2.fido2_code(account, self.env, touch_callback=on_touch)
        self.assertEqual(len(touch_called), 1)

    def test_fido2_pin_protection(self) -> None:
        pin_dev = MockCtapHidDevice(has_hmac_secret=True, required_pin="123456")
        fido2._set_device_override([pin_dev])

        account = "banking"
        secret = "JBSWY3DPEHPK3PXP"

        # Enrollment with right PIN succeeds
        fido2.fido2_enroll(account, secret, self.env, pin="123456")

        # Retrieval with right PIN succeeds
        code = fido2.fido2_code(account, self.env, pin="123456")
        self.assertTrue(code.isdigit() and len(code) == 6)

        # Retrieval with wrong PIN fails
        with self.assertRaises(AppError) as cm:
            fido2.fido2_code(account, self.env, pin="wrongpin")
        self.assertEqual(cm.exception.exit_code, 5)

    def test_fido2_touch_timeout(self) -> None:
        timeout_dev = MockCtapHidDevice(has_hmac_secret=True, simulate_timeout=True)
        fido2._set_device_override([timeout_dev])

        with self.assertRaises(AppError) as cm:
            fido2.fido2_enroll("server", "JBSWY3DPEHPK3PXP", self.env)
        self.assertEqual(cm.exception.exit_code, 4)

    def test_fido2_delete_removes_from_vault(self) -> None:
        account = "gitlab"
        secret = "JBSWY3DPEHPK3PXP"
        fido2.fido2_enroll(account, secret, self.env)
        self.assertEqual(len(fido2.fido2_records(self.env)), 1)

        fido2.fido2_delete(account, self.env)
        self.assertEqual(len(fido2.fido2_records(self.env)), 0)

        # Accessing deleted account raises AppError(4)
        with self.assertRaises(AppError) as cm:
            fido2.fido2_code(account, self.env)
        self.assertEqual(cm.exception.exit_code, 4)

    def test_fido2_tampered_ciphertext_fails_decryption(self) -> None:
        account = "vpn"
        secret = "JBSWY3DPEHPK3PXP"
        fido2.fido2_enroll(account, secret, self.env)

        # Tamper with the ciphertext in the vault
        vault_path = Path(self.tmpdir.name) / "authy-local" / "fido2_vault.json"
        import json

        data = json.loads(vault_path.read_text(encoding="utf-8"))
        # Flip bytes in ciphertext
        ct = bytearray.fromhex(data["accounts"][account]["ciphertext"])
        ct[0] ^= 0xFF
        data["accounts"][account]["ciphertext"] = ct.hex()
        vault_path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaises(AppError) as cm:
            fido2.fido2_code(account, self.env)
        self.assertEqual(cm.exception.exit_code, 5)

    def test_fido2_validation(self) -> None:
        # Invalid account names
        with self.assertRaises(AppError) as cm:
            fido2.fido2_enroll("", "JBSWY3DPEHPK3PXP", self.env)
        self.assertEqual(cm.exception.exit_code, 2)

        with self.assertRaises(AppError) as cm:
            fido2.fido2_enroll("invalid account with spaces!", "JBSWY3DPEHPK3PXP", self.env)
        self.assertEqual(cm.exception.exit_code, 2)

        # Empty secret
        with self.assertRaises(AppError) as cm:
            fido2.fido2_enroll("valid_acct", "", self.env)
        self.assertEqual(cm.exception.exit_code, 2)

    def test_fido2_missing_hardware_raises_error_3(self) -> None:
        fido2._set_device_override([])
        with self.assertRaises(AppError) as cm:
            fido2.fido2_enroll("test", "JBSWY3DPEHPK3PXP", self.env)
        self.assertEqual(cm.exception.exit_code, 3)

    def test_doctor_report_includes_fido2(self) -> None:
        rep = doctor.report(self.env)
        self.assertIn("fido2", rep)
        self.assertEqual(rep["fido2"]["state"], "available")

    def test_deletion_audit_fido2(self) -> None:
        # deletion_audit.record should accept fido2 without raising
        deletion_audit.record("fido2", home=Path(self.tmpdir.name))
        log_file = Path(self.tmpdir.name) / ".local" / "state" / "authy-local" / "deletions.jsonl"
        self.assertTrue(log_file.is_file())
        data = json.loads(log_file.read_text(encoding="utf-8").strip())
        self.assertEqual(data.get("backend"), "fido2")

    @patch("authy_local.cli.has_terminal", return_value=True)
    def test_cli_fido2_enroll_and_show(self, mock_term) -> None:
        import io

        from authy_local import cli

        # 1. Enroll via CLI
        with patch.dict(os.environ, self.env):
            with patch("getpass.getpass", side_effect=["JBSWY3DPEHPK3PXP", "JBSWY3DPEHPK3PXP"]):
                stdout = io.StringIO()
                stdout.isatty = lambda: True
                code = cli.main(
                    ["enroll", "--backend", "fido2", "--account", "cli_fido2_test", "--apply"],
                    stdin=io.StringIO(),
                    stdout=stdout,
                    stderr=io.StringIO(),
                )
                self.assertEqual(code, 0)

        # 2. Show via CLI
        with patch.dict(os.environ, self.env):
            stdout = io.StringIO()
            stdout.isatty = lambda: True
            code = cli.main(
                ["show", "--backend", "fido2", "--account", "cli_fido2_test"],
                stdin=io.StringIO(),
                stdout=stdout,
                stderr=io.StringIO(),
            )
            self.assertEqual(code, 0)
            output_code = stdout.getvalue().strip()
            self.assertEqual(len(output_code), 6)
            self.assertTrue(output_code.isdigit())

    def test_tui_items_fido2_integration(self) -> None:
        from authy_local import tui_items

        fido2.fido2_enroll("acct_fido2_tui", "JBSWY3DPEHPK3PXP", self.env)

        recs = tui_items.records("fido2", {}, self.env)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0][0], "acct_fido2_tui")

        args = tui_items.arguments("fido2", {}, "acct_fido2_tui")
        self.assertEqual(args, ["--backend", "fido2", "--account", "acct_fido2_tui"])

        tui_items.remove("fido2", {}, "acct_fido2_tui", self.env)
        recs_after = tui_items.records("fido2", {}, self.env)
        self.assertEqual(len(recs_after), 0)

    def test_fido2_multi_token_redundancy(self) -> None:
        account = "multi_key_acct"
        secret = "JBSWY3DPEHPK3PXP"
        params = OtpParameters(secret=secret, account=account)
        expected_code, _ = generate_totp_code(params, timestamp=1234567.0)

        # 1. Enroll primary token
        primary_dev = MockCtapHidDevice(has_hmac_secret=True)
        fido2._set_device_override([primary_dev])
        fido2.fido2_enroll(account, secret, self.env)

        # 2. Enroll secondary backup token
        backup_dev = MockCtapHidDevice(has_hmac_secret=True)
        fido2._set_device_override([backup_dev])
        fido2.fido2_add_backup_token(account, secret, self.env)

        # 3. Disconnect primary, test generation using backup token
        fido2._set_device_override([backup_dev])
        code_backup = fido2.fido2_code(account, self.env, timestamp=1234567.0)
        self.assertEqual(code_backup, expected_code)

        # 4. Disconnect backup, test generation using primary token
        fido2._set_device_override([primary_dev])
        code_primary = fido2.fido2_code(account, self.env, timestamp=1234567.0)
        self.assertEqual(code_primary, expected_code)
