"""Milestone M2 Adversarial Input Validation & Secret Protection Test Suite.

Empirical verification suite written by Challenger M2-1 to stress-test:
1. YubiKey account names in hardware.py:
   - Option injection attacks (-s, --help, -v, --version, etc.).
   - Metacharacters, command substitution, and shell separators (; rm -rf, $(id), `id`, etc.).
   - Null bytes (\x00), escape sequences, newlines, and control characters.
   - Boundary lengths (empty, 1 char, 64 chars, 65 chars).
   - Legitimate OATH account labels (AWS:admin, user@example.com, etc.).
   - ykman missing and non-zero process exits.
2. Symlink attacks in importers.py:
   - Sensitive file targets (/etc/passwd, mock private keys).
   - Relative symlinks and multi-hop symlink chains.
   - Circular symlinks (self-referential and mutual cyclic links).
   - Dangling symlinks.
   - Kernel O_NOFOLLOW defense under simulated TOCTOU bypass.
   - Real multithreaded rapid TOCTOU replacement race.
   - Non-regular files and oversized files.
3. Secret repr leakage:
   - OtpParameters __repr__, __str__, and format string variants.
   - Nested collection representations (lists, dicts, tuples).
   - Exception wrapping representations.
   - Legitimate secret attribute and URI serialization preservation.
   - Scope repr shielding in models.py.
4. CLI top-level exception shielding:
   - Injection of diverse unhandled exceptions with embedded secrets across subcommands.
   - Verification of exit code 5, static notice MESSAGES[5], and zero traceback/variable leakage.
   - Verification of standard expected exception flows (SystemExit, AppError, KeyboardInterrupt).
"""

from __future__ import annotations

import io
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from authy_local import cli
from authy_local.backends.hardware import LABEL as HARDWARE_LABEL
from authy_local.backends.hardware import yubikey_code
from authy_local.enrollment import OtpParameters
from authy_local.errors import MESSAGES, AppError
from authy_local.importers import detect_and_parse_import
from authy_local.models import Scope


class TestYubiKeyAccountNameAdversarial(unittest.TestCase):
    """Stress-test YubiKey account name validation in hardware.py."""

    def setUp(self) -> None:
        self.env = {"PATH": "/usr/bin:/bin"}

    def test_option_injection_payloads_strictly_rejected(self) -> None:
        """Verify that CLI option injection strings are rejected with AppError(2)."""
        option_injections = [
            "-s",
            "-v",
            "-h",
            "-d",
            "--help",
            "--version",
            "--delete",
            "--device",
            "--account",
            "-o /tmp/evil",
            "--format=json",
            "--",
            "-",
        ]
        for payload in option_injections:
            with self.subTest(payload=payload):
                with self.assertRaises(AppError) as ctx:
                    yubikey_code(payload, self.env)
                self.assertEqual(ctx.exception.exit_code, 2)

    def test_shell_metacharacters_and_command_injection_rejected(self) -> None:
        """Verify shell metacharacters and injection strings are rejected with AppError(2)."""
        shell_payloads = [
            "; rm -rf /",
            "account; ls -la",
            "account | sh",
            "account && echo hacked",
            "$(whoami)",
            "account`id`",
            "account$(reboot)",
            "admin'--",
            "admin' OR '1'='1",
            'admin" OR "1"="1',
            "admin > /tmp/pwn",
            "admin < /tmp/pwn",
            "admin &",
            "admin || true",
        ]
        for payload in shell_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(AppError) as ctx:
                    yubikey_code(payload, self.env)
                self.assertEqual(ctx.exception.exit_code, 2)

    def test_control_characters_null_bytes_and_newlines_rejected(self) -> None:
        """Verify null bytes, newlines, and control sequences are rejected with AppError(2)."""
        control_payloads = [
            "\x00",
            "admin\x00extra",
            "admin\nlist",
            "admin\r\n",
            "admin\taccount",
            "\x1b[31madmin\x1b[0m",
            "admin\b",
            "admin\v",
            "admin\f",
        ]
        for payload in control_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(AppError) as ctx:
                    yubikey_code(payload, self.env)
                self.assertEqual(ctx.exception.exit_code, 2)

    def test_boundary_lengths_and_character_restrictions(self) -> None:
        """Verify length boundaries (0, 1, 64, 65) and starting character constraints."""
        # Empty string
        with self.assertRaises(AppError) as ctx:
            yubikey_code("", self.env)
        self.assertEqual(ctx.exception.exit_code, 2)

        # Whitespace
        for ws in [" ", "   ", "\t"]:
            with self.assertRaises(AppError) as ctx:
                yubikey_code(ws, self.env)
            self.assertEqual(ctx.exception.exit_code, 2)

        # Invalid leading punctuation (must be alphanumeric)
        invalid_starters = [
            ":leadingcolon",
            ".leadingdot",
            "-leadingdash",
            "@leadingat",
            "_leadingunderscore",
        ]
        for starter in invalid_starters:
            with self.subTest(starter=starter):
                with self.assertRaises(AppError) as ctx:
                    yubikey_code(starter, self.env)
                self.assertEqual(ctx.exception.exit_code, 2)

        # 64 characters (maximum allowed) -> matches regex
        len_64 = "A" + ("b" * 63)
        self.assertEqual(len(len_64), 64)
        self.assertIsNotNone(HARDWARE_LABEL.fullmatch(len_64))

        # 65 characters (exceeds limit) -> rejected
        len_65 = "A" + ("b" * 64)
        self.assertEqual(len(len_65), 65)
        self.assertIsNone(HARDWARE_LABEL.fullmatch(len_65))
        with self.assertRaises(AppError) as ctx:
            yubikey_code(len_65, self.env)
        self.assertEqual(ctx.exception.exit_code, 2)

    def test_legitimate_oath_account_labels_accepted(self) -> None:
        """Verify standard OATH account labels match regex and invoke ykman correctly."""
        legitimate_labels = [
            "AWS:admin",
            "user@example.com",
            "GitHub:octocat_user-123",
            "Google:alice.bob@company.org",
            "AzureAD:user-01@tenant.onmicrosoft.com",
            "192.168.1.1:root",
            "MyService123",
            "a",
            "0",
            "A" * 64,
        ]

        for label in legitimate_labels:
            with self.subTest(label=label):
                self.assertIsNotNone(
                    HARDWARE_LABEL.fullmatch(label),
                    f"Legitimate OATH label {label!r} failed regex validation",
                )
                with (
                    patch("shutil.which", return_value="/usr/bin/ykman"),
                    patch(
                        "authy_local.backends.hardware.run",
                        return_value=MagicMock(returncode=0, stdout=b"876543\n"),
                    ) as mock_run,
                ):
                    code = yubikey_code(label, self.env)
                    self.assertEqual(code, "876543")
                    mock_run.assert_called_once()
                    cmd = mock_run.call_args[0][0]
                    self.assertEqual(
                        cmd, ["/usr/bin/ykman", "oath", "accounts", "code", "-s", label]
                    )

    def test_ykman_missing_raises_app_error_3(self) -> None:
        """Verify missing ykman raises AppError(3) after label validation succeeds."""
        with patch("shutil.which", return_value=None):
            with self.assertRaises(AppError) as ctx:
                yubikey_code("AWS:admin", self.env)
            self.assertEqual(ctx.exception.exit_code, 3)

    def test_ykman_non_zero_exit_raises_app_error_4(self) -> None:
        """Verify ykman failure exit code raises AppError(4)."""
        with (
            patch("shutil.which", return_value="/usr/bin/ykman"),
            patch(
                "authy_local.backends.hardware.run",
                return_value=MagicMock(returncode=1, stdout=b"Error: Account not found\n"),
            ),
        ):
            with self.assertRaises(AppError) as ctx:
                yubikey_code("AWS:admin", self.env)
            self.assertEqual(ctx.exception.exit_code, 4)


class TestImportersSymlinkAndToctouAdversarial(unittest.TestCase):
    """Stress-test symlink defenses, circular links, and TOCTOU races in importers.py."""

    def test_symlink_to_sensitive_system_files_strictly_rejected(self) -> None:
        """Verify symlinks pointing to sensitive system files are rejected with AppError(3)."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sym_passwd = base / "passwd_link"
            sym_passwd.symlink_to("/etc/passwd")

            with self.assertRaises(AppError) as ctx:
                detect_and_parse_import(sym_passwd)
            self.assertEqual(ctx.exception.exit_code, 3)

    def test_symlink_to_private_key_strictly_rejected(self) -> None:
        """Verify symlinks pointing to confidential private keys are rejected with AppError(3)."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            key_file = base / "id_ed25519"
            key_file.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAA...\n")
            key_file.chmod(0o600)

            sym_key = base / "key_link"
            sym_key.symlink_to(key_file)

            with self.assertRaises(AppError) as ctx:
                detect_and_parse_import(sym_key)
            self.assertEqual(ctx.exception.exit_code, 3)

    def test_relative_and_nested_symlinks_strictly_rejected(self) -> None:
        """Verify relative symlinks traversing directories are rejected with AppError(3)."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            nested_dir = base / "a" / "b" / "c"
            nested_dir.mkdir(parents=True)

            rel_sym = nested_dir / "rel_passwd"
            rel_sym.symlink_to("../../../../../etc/passwd")

            with self.assertRaises(AppError) as ctx:
                detect_and_parse_import(rel_sym)
            self.assertEqual(ctx.exception.exit_code, 3)

    def test_circular_symlinks_strictly_rejected(self) -> None:
        """Verify circular symlinks (self-referential and cyclic pairs) raise AppError(3)."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)

            # 1. Self-referential loop (a -> a)
            circ_self = base / "circ_self"
            circ_self.symlink_to(circ_self)
            with self.assertRaises(AppError) as ctx:
                detect_and_parse_import(circ_self)
            self.assertEqual(ctx.exception.exit_code, 3)

            # 2. Mutual cyclic pair (a -> b -> a)
            circ_a = base / "circ_a"
            circ_b = base / "circ_b"
            circ_a.symlink_to(circ_b)
            circ_b.symlink_to(circ_a)
            with self.assertRaises(AppError) as ctx:
                detect_and_parse_import(circ_a)
            self.assertEqual(ctx.exception.exit_code, 3)

    def test_dangling_symlink_strictly_rejected(self) -> None:
        """Verify dangling symlinks to non-existent targets raise AppError(3)."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            dangling = base / "dangling_link"
            dangling.symlink_to(base / "nonexistent_target_12345.txt")

            with self.assertRaises(AppError) as ctx:
                detect_and_parse_import(dangling)
            self.assertEqual(ctx.exception.exit_code, 3)

    def test_atomic_kernel_o_nofollow_under_simulated_toctou_bypass(self) -> None:
        """Verify that kernel O_NOFOLLOW stops symlink traversal even if Path.is_symlink() is bypassed."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sym_target = base / "raced_symlink"
            sym_target.symlink_to("/etc/passwd")

            # Simulate race condition where user-space is_symlink() check returned False
            with patch.object(Path, "is_symlink", return_value=False):
                with self.assertRaises(AppError) as ctx:
                    detect_and_parse_import(sym_target)
                self.assertEqual(ctx.exception.exit_code, 3)

    def test_real_multithreaded_rapid_toctou_race_stress(self) -> None:
        """Stress-test 300 rapid file/symlink swaps under concurrent import calls.

        Ensures that at no point does detect_and_parse_import leak data from /etc/passwd.
        """
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            target = base / "race_file.txt"
            target.write_text("otpauth://totp/Acme:alice?secret=JBSWY3DPEHPK3PXP\n")

            stop_event = threading.Event()

            def swapper() -> None:
                while not stop_event.is_set():
                    try:
                        target.unlink(missing_ok=True)
                        target.symlink_to("/etc/passwd")
                    except OSError:
                        pass
                    time.sleep(0.0005)
                    try:
                        target.unlink(missing_ok=True)
                        target.write_text("otpauth://totp/Acme:alice?secret=JBSWY3DPEHPK3PXP\n")
                    except OSError:
                        pass
                    time.sleep(0.0005)

            thread = threading.Thread(target=swapper, daemon=True)
            thread.start()

            successes = 0
            rejections = 0
            leaked_records = 0

            try:
                for _ in range(300):
                    try:
                        tokens = detect_and_parse_import(target)
                        for tok in tokens:
                            if "root:" in str(tok.account) or "bin:" in str(tok.account):
                                leaked_records += 1
                        successes += 1
                    except AppError as err:
                        if err.exit_code in (2, 3):
                            rejections += 1
                        else:
                            self.fail(f"Unexpected exit code {err.exit_code} during TOCTOU race")
                    time.sleep(0.0005)
            finally:
                stop_event.set()
                thread.join(timeout=2.0)

            self.assertEqual(leaked_records, 0, "Confidential data from /etc/passwd was leaked!")
            self.assertGreater(successes + rejections, 250)

    def test_non_regular_file_and_size_limits(self) -> None:
        """Verify non-regular files and files exceeding size bounds are rejected with AppError(2)."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)

            # 1. Directory path
            dir_path = base / "directory_target"
            dir_path.mkdir()
            with self.assertRaises(AppError) as ctx:
                detect_and_parse_import(dir_path)
            self.assertEqual(ctx.exception.exit_code, 2)

            # 2. Oversized file (> 10MB)
            oversized = base / "oversized.txt"
            # Write sparse or seek-based file to save disk
            with open(oversized, "wb") as f:
                f.seek(10 * 1024 * 1024 + 1024)
                f.write(b"TRAIL")
            with self.assertRaises(AppError) as ctx:
                detect_and_parse_import(oversized)
            self.assertEqual(ctx.exception.exit_code, 2)


class TestSecretReprShieldingAdversarial(unittest.TestCase):
    """Stress-test secret shielding across representations, string formatting, and containers."""

    def setUp(self) -> None:
        self.secret = "JBSWY3DPEHPK3PXP_SUPER_CONFIDENTIAL_KEY_999"
        self.account = "secops@corp.internal"
        self.issuer = "EnterpriseVault"
        self.otp = OtpParameters(secret=self.secret, account=self.account, issuer=self.issuer)

    def test_secret_shielded_across_all_string_formats(self) -> None:
        """Verify secret never appears in repr, str, f-strings, format(), or modulo strings."""
        representations = [
            ("repr", repr(self.otp)),
            ("str", str(self.otp)),
            ("f-string", f"{self.otp}"),
            ("f-string !r", f"{self.otp!r}"),
            ("f-string !s", f"{self.otp!s}"),
            ("format()", format(self.otp)),
            ("%r", "%r" % self.otp),
            ("%s", "%s" % self.otp),
        ]
        for name, rendered in representations:
            with self.subTest(name=name):
                self.assertNotIn(
                    self.secret,
                    rendered,
                    f"Plaintext secret leaked in {name}: {rendered}",
                )
                self.assertIn(
                    self.account,
                    rendered,
                    f"Account metadata should be present in {name}",
                )

    def test_secret_shielded_in_nested_collections(self) -> None:
        """Verify secret is shielded when OtpParameters is housed in lists, dicts, or tuples."""
        collections = [
            ("list repr", repr([self.otp])),
            ("list str", str([self.otp])),
            ("dict repr", repr({"key": self.otp})),
            ("dict str", str({"key": self.otp})),
            ("tuple repr", repr((self.otp,))),
            ("tuple str", str((self.otp,))),
            ("nested list repr", repr([[self.otp], (self.otp,)])),
        ]
        for name, rendered in collections:
            with self.subTest(name=name):
                self.assertNotIn(
                    self.secret,
                    rendered,
                    f"Plaintext secret leaked in collection {name}: {rendered}",
                )

    def test_secret_shielded_when_wrapped_in_exceptions(self) -> None:
        """Verify secret is shielded when OtpParameters is passed to exception constructors."""
        exc = ValueError(self.otp)
        self.assertNotIn(self.secret, str(exc))
        self.assertNotIn(self.secret, repr(exc))

    def test_direct_secret_accessibility_and_uri_serialization(self) -> None:
        """Verify secret is strictly protected in representation but accessible for valid cryptography."""
        self.assertEqual(self.otp.secret, self.secret)
        uri = self.otp.to_uri()
        self.assertIn(self.secret, uri)
        self.assertTrue(uri.startswith("otpauth://totp/"))

    def test_scope_model_repr_shielding(self) -> None:
        """Verify Scope model in models.py also suppresses item, account, and vault IDs in repr."""
        item_id = "A" * 26
        account_id = "B" * 26
        vault_id = "C" * 26
        scope = Scope(item_id, account_id, vault_id)

        rep = repr(scope)
        self.assertNotIn(item_id, rep)
        self.assertNotIn(account_id, rep)
        self.assertNotIn(vault_id, rep)


class TestCliExceptionShieldingAdversarial(unittest.TestCase):
    """Stress-test CLI top-level exception shield to prevent traceback leaks across subcommands."""

    def test_unexpected_exceptions_shielded_across_subcommands(self) -> None:
        """Verify diverse unhandled exceptions return exit code 5 and emit static sanitized notice."""
        subcommand_scenarios = [
            (["doctor"], "authy_local.doctor.report", {}),
            (
                ["import", "valid_tokens.txt", "--apply"],
                "authy_local.importers.detect_and_parse_import",
                {},
            ),
            (
                ["show", "A" * 26, "--account", "B" * 26, "--vault", "C" * 26, "--allow-pipe"],
                "authy_local.cli.retrieve",
                {"has_terminal": True},
            ),
            (
                ["copy", "A" * 26, "--account", "B" * 26, "--vault", "C" * 26],
                "authy_local.cli.retrieve",
                {"has_terminal": True, "clipboard": True},
            ),
        ]

        malicious_exceptions = [
            RuntimeError("DATABASE_LEAK: private_key=0xDEADBEEF1234567890ABCDEF"),
            ValueError("DECRYPTION_ERROR: master_password=MyP@ssw0rd!123"),
            KeyError("SECRET_TOKEN_IN_LOCAL_FRAME_xyz"),
            ZeroDivisionError("math error secret=42"),
            AssertionError("INTERNAL INVARIANT BROKEN: plaintext_seed=SECRET999"),
        ]

        sensitive_substrings = [
            "DEADBEEF",
            "MyP@ssw0rd",
            "SECRET_TOKEN",
            "secret=42",
            "SECRET999",
        ]

        for cmd, patch_target, opts in subcommand_scenarios:
            for exc in malicious_exceptions:
                with self.subTest(cmd=cmd[0], exc_type=type(exc).__name__):
                    out, err = io.StringIO(), io.StringIO()
                    patches = [patch(patch_target, side_effect=exc)]
                    if opts.get("has_terminal"):
                        patches.append(patch("authy_local.cli.has_terminal", return_value=True))
                    if opts.get("clipboard"):
                        patches.append(
                            patch("authy_local.cli.clipboard_capability", return_value=None)
                        )

                    with patches[0]:
                        if len(patches) > 1:
                            with patches[1]:
                                if len(patches) > 2:
                                    with patches[2]:
                                        exit_code = cli.main(cmd, stdout=out, stderr=err)
                                else:
                                    exit_code = cli.main(cmd, stdout=out, stderr=err)
                        else:
                            exit_code = cli.main(cmd, stdout=out, stderr=err)

                    # 1. Exit code must be 5
                    self.assertEqual(exit_code, 5)

                    err_output = err.getvalue()
                    out_output = out.getvalue()

                    # 2. No tracebacks leaked
                    self.assertNotIn("Traceback (most recent call last):", err_output)
                    self.assertNotIn('File "', err_output)

                    # 3. No sensitive exception messages or frame variables leaked
                    for sensitive in sensitive_substrings:
                        self.assertNotIn(sensitive, err_output)
                        self.assertNotIn(sensitive, out_output)

                    # 4. Static notice MESSAGES[5] must be printed
                    self.assertIn(MESSAGES[5], err_output)

    def test_expected_exceptions_preserve_standard_exit_codes(self) -> None:
        """Verify expected exceptions (AppError, KeyboardInterrupt, SystemExit) preserve proper semantics."""
        # 1. AppError(2) -> exit 2
        out, err = io.StringIO(), io.StringIO()
        with patch("authy_local.cli.has_terminal", return_value=True):
            code = cli.main(["show", "invalid_item"], stdout=out, stderr=err)
        self.assertEqual(code, 2)
        self.assertIn(MESSAGES[2], err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

        # 2. KeyboardInterrupt -> exit 130
        out, err = io.StringIO(), io.StringIO()
        with patch("authy_local.doctor.report", side_effect=KeyboardInterrupt()):
            code = cli.main(["doctor"], stdout=out, stderr=err)
        self.assertEqual(code, 130)
        self.assertIn("Operation cancelled.", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())


if __name__ == "__main__":
    unittest.main()
