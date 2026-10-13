"""Tests for 1Password backend enrollment method."""

import json
import unittest
from unittest.mock import MagicMock, patch

from authy_local.backends import onepassword
from authy_local.errors import AppError


class TestOnePasswordEnrollment(unittest.TestCase):
    """Unit tests for onepassword.enroll function."""

    def setUp(self) -> None:
        self.account = "2w4j6k8m0n2p4r6t8v0x2z4a6a"
        self.vault = "2w4j6k8m0n2p4r6t8v0x2z4a6v"
        self.title = "GitHub Personal"
        self.uri = "otpauth://totp/GitHub:alice?secret=JBSWY3DPEHPK3PXP&issuer=GitHub"
        self.env = {"PATH": "/usr/bin"}

    def test_enroll_new_item_command_construction(self) -> None:
        """Verify op item create is called with --category Login, --tags OTP, and otp field."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"id": "item123", "title": self.title}).encode()

        with (
            patch(
                "authy_local.backends.onepassword.probe",
                return_value={"state": "available", "path": "/usr/bin/op"},
            ),
            patch("authy_local.backends.onepassword.run", return_value=mock_result) as mock_run,
        ):
            item_id = onepassword.enroll(
                account=self.account,
                vault=self.vault,
                title=self.title,
                otp_uri=self.uri,
                env=self.env,
            )
            self.assertEqual(item_id, "item123")
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            self.assertEqual(cmd[0], "/usr/bin/op")
            self.assertEqual(cmd[1:3], ["item", "create"])
            self.assertIn("--category", cmd)
            self.assertIn("Login", cmd)
            self.assertIn("--tags", cmd)
            self.assertIn("OTP", cmd)
            self.assertIn(f"one-time password[otp]={self.uri}", cmd)

    def test_enroll_existing_item_edit(self) -> None:
        """Verify op item edit is called when item_id is provided."""
        existing_id = "2w4j6k8m0n2p4r6t8v0x2z4a6i"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"id": existing_id}).encode()

        with (
            patch(
                "authy_local.backends.onepassword.probe",
                return_value={"state": "available", "path": "/usr/bin/op"},
            ),
            patch("authy_local.backends.onepassword.run", return_value=mock_result) as mock_run,
        ):
            item_id = onepassword.enroll(
                account=self.account,
                vault=self.vault,
                title=self.title,
                otp_uri=self.uri,
                env=self.env,
                item_id=existing_id,
                tags="Dev,Cloud",
            )
            self.assertEqual(item_id, existing_id)
            cmd = mock_run.call_args[0][0]
            self.assertEqual(cmd[1:4], ["item", "edit", existing_id])
            self.assertIn("--tags", cmd)
            self.assertIn("Dev,Cloud,OTP", cmd)

    def test_enroll_foreign_auth_and_missing_tool_refusal(self) -> None:
        """Verify foreign auth tokens and missing op tool are refused safely."""
        with self.assertRaises(AppError) as ctx:
            onepassword.enroll(
                account=self.account,
                vault=self.vault,
                title=self.title,
                otp_uri=self.uri,
                env={"PATH": "/usr/bin", "OP_SERVICE_ACCOUNT_TOKEN": "forbidden"},
            )
        self.assertEqual(ctx.exception.exit_code, 3)

        with patch("authy_local.backends.onepassword.probe", return_value={"state": "missing"}):
            with self.assertRaises(AppError) as ctx:
                onepassword.enroll(
                    account=self.account,
                    vault=self.vault,
                    title=self.title,
                    otp_uri=self.uri,
                    env=self.env,
                )
            self.assertEqual(ctx.exception.exit_code, 3)

    def test_enroll_parameter_validation_and_command_failure(self) -> None:
        """Verify parameter bounds and non-zero exit codes fail closed."""
        with patch(
            "authy_local.backends.onepassword.probe",
            return_value={"state": "available", "path": "/usr/bin/op"},
        ):
            # Empty title
            with self.assertRaises(AppError) as ctx:
                onepassword.enroll(
                    account=self.account,
                    vault=self.vault,
                    title="   ",
                    otp_uri=self.uri,
                    env=self.env,
                )
            self.assertEqual(ctx.exception.exit_code, 2)

            # Non-otpauth URI
            with self.assertRaises(AppError) as ctx:
                onepassword.enroll(
                    account=self.account,
                    vault=self.vault,
                    title=self.title,
                    otp_uri="http://invalid.uri",
                    env=self.env,
                )
            self.assertEqual(ctx.exception.exit_code, 2)

            # Process failure returncode = 1
            mock_fail = MagicMock()
            mock_fail.returncode = 1
            with patch("authy_local.backends.onepassword.run", return_value=mock_fail):
                with self.assertRaises(AppError) as ctx:
                    onepassword.enroll(
                        account=self.account,
                        vault=self.vault,
                        title=self.title,
                        otp_uri=self.uri,
                        env=self.env,
                    )
                self.assertEqual(ctx.exception.exit_code, 4)


if __name__ == "__main__":
    unittest.main()
