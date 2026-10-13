"""Unit and integration tests for Autonomous Security Auditor v2 (Phase 11 / Sprint 11.2)."""

import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from authy_local.auditor import (
    AuditFinding,
    AuditReport,
    audit_tokens,
    calculate_shannon_entropy,
    check_time_drift,
    format_audit_report,
    generate_rotation_advice,
    scan_environment_leaks,
)
from authy_local.cli import main
from authy_local.enrollment import OtpParameters


class TestShannonEntropy(unittest.TestCase):
    def test_entropy_empty_string(self):
        self.assertEqual(calculate_shannon_entropy(""), 0.0)

    def test_entropy_single_repeated_char(self):
        # A string of all same character has 0 entropy
        self.assertEqual(calculate_shannon_entropy("AAAAAAAAAAAAAAAA"), 0.0)

    def test_entropy_low_pattern(self):
        # Two alternating characters: log2(2) = 1.0 bit/char
        entropy = calculate_shannon_entropy("ABABABABABABABAB")
        self.assertAlmostEqual(entropy, 1.0, places=3)
        self.assertLess(entropy, 2.5)

    def test_entropy_high_random(self):
        # 32 distinct characters in Base32: log2(32) = 5.0 bits/char
        b32_alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
        entropy = calculate_shannon_entropy(b32_alphabet)
        self.assertAlmostEqual(entropy, 5.0, places=3)
        self.assertGreater(entropy, 4.5)

    def test_flag_low_entropy_secret_rule_sec005(self):
        token = OtpParameters(
            secret="ABABABABABABABAB",  # 16 chars, 2 alternating characters, entropy 1.0
            account="bob@example.com",
            issuer="LowEntropyService",
        )
        report = audit_tokens([token], backend="local")
        sec005_findings = [f for f in report.findings if f.rule_id == "SEC-005"]
        self.assertEqual(len(sec005_findings), 1)
        self.assertEqual(sec005_findings[0].severity, "HIGH")
        self.assertIn("LowEntropyService (bob@example.com)", sec005_findings[0].accounts[0])
        self.assertIn("Shannon entropy", sec005_findings[0].accounts[0])


class TestTimeDrift(unittest.TestCase):
    def test_time_drift_normal(self):
        env = {"FAKE_TIME_SKEW_SECONDS": "0.15"}
        res = check_time_drift(env)
        self.assertTrue(res["synchronized"])
        self.assertAlmostEqual(res["offset_seconds"], 0.15)
        self.assertEqual(res["skew_severity"], "LOW")

    def test_time_drift_moderate_skew(self):
        env = {"FAKE_TIME_SKEW_SECONDS": "2.5"}
        res = check_time_drift(env)
        self.assertFalse(res["synchronized"])
        self.assertAlmostEqual(res["offset_seconds"], 2.5)
        self.assertEqual(res["skew_severity"], "HIGH")

        token = OtpParameters(
            secret="JBSWY3DPEHPK3PXY",
            account="user@example.com",
            issuer="SyncCheck",
        )
        report = audit_tokens([token], backend="local", env=env)
        sec006 = [f for f in report.findings if f.rule_id == "SEC-006"]
        self.assertEqual(len(sec006), 1)
        self.assertEqual(sec006[0].severity, "HIGH")
        self.assertIn("System Clock", sec006[0].accounts)

    def test_time_drift_critical_skew(self):
        env = {"FAKE_TIME_SKEW_SECONDS": "-6.2"}
        res = check_time_drift(env)
        self.assertFalse(res["synchronized"])
        self.assertEqual(res["skew_severity"], "CRITICAL")

        token = OtpParameters(
            secret="JBSWY3DPEHPK3PXY",
            account="user@example.com",
            issuer="SyncCheck",
        )
        report = audit_tokens([token], backend="local", env=env)
        sec006 = [f for f in report.findings if f.rule_id == "SEC-006"]
        self.assertEqual(len(sec006), 1)
        self.assertEqual(sec006[0].severity, "CRITICAL")


class TestEnvironmentLeakScanner(unittest.TestCase):
    def test_no_leaks_clean_environment(self):
        tokens = [
            OtpParameters(
                secret="MZXW6YTBOI=======",
                account="clean@example.com",
                issuer="CleanService",
            )
        ]
        env = {"PATH": "/usr/bin:/bin", "USER": "tester"}
        findings = scan_environment_leaks(tokens, env)
        self.assertEqual(len(findings), 0)

    def test_leak_in_environment_variable(self):
        secret = "MZXW6YTBOI2XEZLU"
        tokens = [
            OtpParameters(
                secret=secret,
                account="leak@example.com",
                issuer="LeakyService",
            )
        ]
        env = {"PATH": "/usr/bin", "LEAKED_OTP_SEED": f"export SECRET={secret}"}
        findings = scan_environment_leaks(tokens, env)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "SEC-007")
        self.assertEqual(findings[0].severity, "HIGH")
        self.assertIn(
            "LeakyService (leak@example.com) (in env var $LEAKED_OTP_SEED)", findings[0].accounts
        )

    def test_leak_in_fake_shell_history(self):
        secret = "KRSXG5CTMVRXEZLU"
        tokens = [
            OtpParameters(
                secret=secret,
                account="shell@example.com",
                issuer="ShellService",
            )
        ]
        with tempfile.NamedTemporaryFile("w", delete=False) as tf:
            tf.write(
                f"git commit -m 'initial'\notp-local enroll --secret {secret} myaccount\nls -la\n"
            )
            hist_path = tf.name

        try:
            env = {"FAKE_SHELL_HISTORY": hist_path}
            findings = scan_environment_leaks(tokens, env)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].rule_id, "SEC-007")
            self.assertTrue(
                any("ShellService (shell@example.com)" in acc for acc in findings[0].accounts)
            )
        finally:
            if os.path.exists(hist_path):
                os.unlink(hist_path)

    def test_leak_in_proc_environ_or_cmdline(self):
        secret = "NBSWY3DPEHPK3PXY"
        tokens = [
            OtpParameters(
                secret=secret,
                account="proc@example.com",
                issuer="ProcService",
            )
        ]
        with (
            tempfile.NamedTemporaryFile("wb", delete=False) as tf_env,
            tempfile.NamedTemporaryFile("wb", delete=False) as tf_cmd,
        ):
            tf_env.write(b"USER=tester\x00PATH=/bin\x00")
            tf_cmd.write(f"python3\x00--token={secret}\x00".encode("utf-8"))
            p_env = tf_env.name
            p_cmd = tf_cmd.name

        try:
            env = {
                "FAKE_PROC_ENVIRON": p_env,
                "FAKE_PROC_CMDLINE": p_cmd,
            }
            findings = scan_environment_leaks(tokens, env)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].rule_id, "SEC-007")
            self.assertTrue(
                any("ProcService (proc@example.com)" in acc for acc in findings[0].accounts)
            )
        finally:
            for p in (p_env, p_cmd):
                if os.path.exists(p):
                    os.unlink(p)


class TestRotationAdvisor(unittest.TestCase):
    def test_generate_rotation_advice_for_vulnerable_tokens(self):
        tokens = [
            OtpParameters(
                secret="JBSWY3DPEHPK3PXP",  # Known RFC sample seed (HIGH)
                account="alice@sample.com",
                issuer="VulnerableApp",
                algorithm="SHA1",
                digits=6,
            ),
            OtpParameters(
                secret="KRSXG5CTMVRXEZLU",  # Clean token
                account="bob@clean.com",
                issuer="CleanApp",
                algorithm="SHA256",
                digits=6,
            ),
        ]
        report = audit_tokens(tokens, backend="local", rotate=True)
        self.assertEqual(len(report.rotations), 1)
        rot = report.rotations[0]
        self.assertEqual(rot["account"], "alice@sample.com")
        self.assertEqual(rot["issuer"], "VulnerableApp")
        self.assertEqual(rot["old_algorithm"], "SHA1")
        self.assertEqual(rot["recommended_algorithm"], "SHA256")
        # Ensure new secret is 32 Base32 characters (160 bits)
        self.assertEqual(len(rot["new_secret"]), 32)
        self.assertIn("otpauth://totp/", rot["new_uri"])
        self.assertIn(rot["new_secret"], rot["new_uri"])

        formatted = format_audit_report(report)
        self.assertIn("Guided Secret Rotation Recommendations:", formatted)
        self.assertIn("VulnerableApp (alice@sample.com)", formatted)
        self.assertIn(rot["new_secret"], formatted)

    def test_direct_generate_rotation_advice(self):
        finding = AuditFinding(
            rule_id="SEC-002",
            severity="HIGH",
            title="Sample seed",
            accounts=["SampleApp (user@example.com)"],
            description="desc",
            recommendation="rec",
        )
        report = AuditReport(
            backend="local",
            total_tokens=1,
            findings=[finding],
            score=70,
            grade="C",
        )
        tokens = [
            OtpParameters(
                secret="JBSWY3DPEHPK3PXP",
                account="user@example.com",
                issuer="SampleApp",
            )
        ]
        rotations = generate_rotation_advice(report, tokens)
        self.assertEqual(len(rotations), 1)
        self.assertEqual(rotations[0]["account"], "user@example.com")
        self.assertEqual(rotations[0]["issuer"], "SampleApp")


class TestCliAuditCommandV2(unittest.TestCase):
    @patch("authy_local.exporters.collect_backend_tokens")
    def test_cli_audit_with_rotate_flag(self, mock_collect):
        mock_collect.return_value = [
            OtpParameters(
                secret="JBSWY3DPEHPK3PXP",  # Known RFC test seed
                account="alice@test.com",
                issuer="VulnerableApp",
                algorithm="SHA1",
            )
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        rc = main(["audit", "--backend", "onepassword", "--rotate"], stdout=stdout, stderr=stderr)
        out = stdout.getvalue()
        self.assertIn("Guided Secret Rotation Recommendations:", out)
        self.assertIn("VulnerableApp (alice@test.com)", out)
        self.assertIn("otpauth://totp/", out)
        # rc is 0 because there are no CRITICAL findings (SEC-002 is HIGH)
        self.assertEqual(rc, 0)

    @patch("authy_local.exporters.collect_backend_tokens")
    def test_cli_audit_json_with_rotations(self, mock_collect):
        mock_collect.return_value = [
            OtpParameters(
                secret="JBSWY3DPEHPK3PXP",  # Known RFC test seed
                account="alice@test.com",
                issuer="VulnerableApp",
                algorithm="SHA1",
            )
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        rc = main(
            ["audit", "--backend", "onepassword", "--rotate", "--json"],
            stdout=stdout,
            stderr=stderr,
        )
        data = json.loads(stdout.getvalue())
        self.assertIn("rotations", data)
        self.assertEqual(len(data["rotations"]), 1)
        self.assertEqual(data["rotations"][0]["account"], "alice@test.com")
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
