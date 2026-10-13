"""Unit tests for credential security and hygiene auditor."""

import io
import json
import unittest

from authy_local.auditor import audit_tokens, format_audit_report
from authy_local.cli import main
from authy_local.enrollment import OtpParameters


class TestAuditor(unittest.TestCase):
    def test_clean_tokens_get_perfect_score(self):
        tokens = [
            OtpParameters(
                secret="JBSWY3DPEHPK3PXY",  # 16-char random-looking
                account="alice@example.com",
                issuer="GitHub",
                algorithm="SHA1",
                digits=6,
                period=30,
            ),
            OtpParameters(
                secret="KRSXG5CTMVRXEZLU",
                account="bob@example.com",
                issuer="GitLab",
                algorithm="SHA256",
                digits=8,
                period=30,
            ),
        ]
        report = audit_tokens(tokens, backend="pass-otp")
        self.assertEqual(report.total_tokens, 2)
        self.assertEqual(report.score, 100)
        self.assertEqual(report.grade, "A+")
        self.assertEqual(len(report.findings), 0)

        text = format_audit_report(report)
        self.assertIn("All inspected tokens conform", text)
        self.assertIn("100 / 100", text)

    def test_detect_duplicate_secret_reuse(self):
        shared_secret = "JBSWY3DPEHPK3PXY"
        tokens = [
            OtpParameters(
                secret=shared_secret,
                account="alice@work.com",
                issuer="AWS",
            ),
            OtpParameters(
                secret=shared_secret,
                account="alice@home.com",
                issuer="GitHub",
            ),
        ]
        report = audit_tokens(tokens, backend="pass-otp")
        self.assertEqual(report.total_tokens, 2)
        self.assertTrue(report.score < 90)
        crit_findings = [f for f in report.findings if f.severity == "CRITICAL"]
        self.assertEqual(len(crit_findings), 1)
        self.assertEqual(crit_findings[0].rule_id, "SEC-001")
        self.assertIn("AWS (alice@work.com)", crit_findings[0].accounts)
        self.assertIn("GitHub (alice@home.com)", crit_findings[0].accounts)

    def test_detect_known_test_vector_seed(self):
        tokens = [
            OtpParameters(
                secret="JBSWY3DPEHPK3PXP",  # RFC sample "Hello!"
                account="alice@test.com",
                issuer="TestApp",
            )
        ]
        report = audit_tokens(tokens, backend="onepassword")
        self.assertEqual(report.total_tokens, 1)
        high_findings = [f for f in report.findings if f.rule_id == "SEC-002"]
        self.assertEqual(len(high_findings), 1)
        self.assertIn("TestApp (alice@test.com)", high_findings[0].accounts)

    def test_detect_weak_length_secret(self):
        tokens = [
            OtpParameters(
                secret="JBSWY3DP",  # Only 8 chars / 40 bits
                account="charlie",
                issuer="VPN",
            )
        ]
        report = audit_tokens(tokens, backend="totpm")
        weak_findings = [f for f in report.findings if f.rule_id == "SEC-003"]
        self.assertEqual(len(weak_findings), 1)

    def test_detect_hygiene_and_non_standard_params(self):
        tokens = [
            OtpParameters(
                secret="KRSXG5CTMVRXEZLU",
                account="account",  # generic
                issuer="",  # missing
                period=15,  # non-standard
                digits=7,  # non-standard
            )
        ]
        report = audit_tokens(tokens, backend="local")
        rule_ids = {f.rule_id for f in report.findings}
        self.assertIn("HYG-001", rule_ids)
        self.assertIn("HYG-002", rule_ids)

    def test_empty_token_list(self):
        report = audit_tokens([], backend="empty")
        self.assertEqual(report.total_tokens, 0)
        self.assertEqual(report.score, 100)
        self.assertEqual(report.grade, "A+")


class TestAuditCLI(unittest.TestCase):
    def test_audit_json_output(self):
        from unittest.mock import patch

        out = io.StringIO()
        err = io.StringIO()
        with patch("authy_local.exporters.collect_backend_tokens", return_value=[]):
            status = main(
                [
                    "audit",
                    "--backend",
                    "pass-otp",
                    "--store",
                    "/tmp/store",
                    "--key-home",
                    "/tmp/keys",
                    "--json",
                ],
                stdout=out,
                stderr=err,
            )
        self.assertEqual(status, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data["backend"], "pass-otp")
        self.assertIn("score", data)
        self.assertIn("grade", data)


if __name__ == "__main__":
    unittest.main()
