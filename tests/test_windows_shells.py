"""Tests for Windows shell integrations (PowerShell and NuShell)."""

import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class WindowsShellsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ps1_path = REPO_ROOT / "shell" / "otp-local.ps1"
        self.nu_path = REPO_ROOT / "shell" / "otp-local.nu"

    def test_powershell_script_exists_and_readable(self) -> None:
        self.assertTrue(self.ps1_path.is_file(), "shell/otp-local.ps1 must exist")
        content = self.ps1_path.read_text(encoding="utf-8")
        self.assertGreater(len(content), 100)

    def test_powershell_functions_and_aliases(self) -> None:
        content = self.ps1_path.read_text(encoding="utf-8")
        self.assertIn("function Get-OtpCode", content)
        self.assertIn("function Copy-OtpCode", content)
        self.assertIn("function Select-OtpCode", content)

        # Verify aliases
        self.assertRegex(content, r"Set-Alias\s+-Name\s+otp\s+-Value\s+Get-OtpCode")
        self.assertRegex(content, r"Set-Alias\s+-Name\s+totp\s+-Value\s+Get-OtpCode")
        self.assertRegex(content, r"Set-Alias\s+-Name\s+otpc\s+-Value\s+Copy-OtpCode")

    def test_powershell_completions_registration(self) -> None:
        content = self.ps1_path.read_text(encoding="utf-8")
        self.assertIn("Register-ArgumentCompleter -Native -CommandName 'otp-local'", content)
        self.assertIn("Register-ArgumentCompleter -CommandName 'Get-OtpCode'", content)
        self.assertIn("Register-ArgumentCompleter -CommandName 'Copy-OtpCode'", content)

        # Expected subcommands
        for subcmd in (
            "doctor",
            "tui",
            "guide",
            "show",
            "copy",
            "select",
            "enroll",
            "pick",
            "import",
            "export",
            "audit",
            "qr",
            "agent",
            "unlock",
        ):
            self.assertIn(f"'{subcmd}'", content)

        # Expected backends in ValidateSet and completion
        for backend in (
            "dpapi",
            "onepassword",
            "pass-otp",
            "totpm",
            "yubikey",
            "tpm2-totp",
            "keychain",
        ):
            self.assertIn(f'"{backend}"', content)

    @unittest.skipUnless(
        shutil.which("pwsh") or shutil.which("powershell"),
        "PowerShell binary (pwsh/powershell) unavailable",
    )
    def test_powershell_syntax_execution(self) -> None:
        bin_name = shutil.which("pwsh") or shutil.which("powershell")
        cmd = [
            bin_name,
            "-NoProfile",
            "-Command",
            f"& {{ [System.Management.Automation.Language.Parser]::ParseFile('{self.ps1_path}', [ref]$null, [ref]$errors); if ($errors.Count -gt 0) {{ exit 1 }} }}",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"PowerShell syntax errors: {res.stderr}")

    def test_nushell_script_exists_and_readable(self) -> None:
        self.assertTrue(self.nu_path.is_file(), "shell/otp-local.nu must exist")
        content = self.nu_path.read_text(encoding="utf-8")
        self.assertGreater(len(content), 100)

    def test_nushell_commands_and_structure(self) -> None:
        content = self.nu_path.read_text(encoding="utf-8")
        self.assertIn('export extern "otp-local"', content)
        self.assertIn('export def "otp show"', content)
        self.assertIn('export def "otp copy"', content)
        self.assertIn('export def "otp record"', content)

        # Check subcommands
        for subcmd in (
            "doctor",
            "tui",
            "guide",
            "show",
            "copy",
            "select",
            "enroll",
            "pick",
            "import",
            "export",
            "audit",
            "qr",
            "agent",
            "unlock",
        ):
            self.assertIn(f'"{subcmd}"', content)

        # Check backends
        for backend in (
            "dpapi",
            "onepassword",
            "pass-otp",
            "totpm",
            "yubikey",
            "tpm2-totp",
            "keychain",
        ):
            self.assertIn(f'"{backend}"', content)

    def test_nushell_record_fields(self) -> None:
        content = self.nu_path.read_text(encoding="utf-8")
        # Ensure record returns account, backend, code, remaining_seconds
        self.assertIn("account: $account", content)
        self.assertIn("backend: $backend", content)
        self.assertIn("code: $code", content)
        self.assertIn("remaining_seconds: $remaining", content)

    @unittest.skipUnless(shutil.which("nu"), "NuShell (nu) unavailable")
    def test_nushell_syntax_execution(self) -> None:
        nu_bin = shutil.which("nu")
        cmd = [nu_bin, "--commands", f"use {self.nu_path} *; print 'syntax-ok'"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"NuShell syntax error: {res.stderr}")
