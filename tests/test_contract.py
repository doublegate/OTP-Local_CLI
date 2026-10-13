"""Catch invalid retrieval output, wrong scope, and accidental disclosure."""

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ITEM = "a" * 26
ACCOUNT = "b" * 26
VAULT = "c" * 26


class CoreContract(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("authy_local"), "Phase 1 package is missing")
        from authy_local import cli, models
        from authy_local.errors import AppError

        self.cli, self.models, self.error = cli, models, AppError
        scratch = Path("/tmp/Authy-to-1Password_Local")
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="contract-", dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.op = self.home / "op"
        self.record = self.home / "calls.jsonl"
        self.op.write_text(
            f"#!{sys.executable}\n"
            "import json,os,sys\n"
            "with open(os.environ['FAKE_RECORD'],'a') as f:\n"
            " f.write(json.dumps({'argv':sys.argv[1:],'sid':os.getsid(0),"
            "'env':{k:v for k,v in os.environ.items() if k.startswith('OP_')}})+'\\n')\n"
            "if sys.argv[1:]==['--version']:\n"
            " print(os.environ.get('FAKE_VERSION','2.39.0'));sys.exit(0)\n"
            "if '--encoding' in sys.argv: sys.exit(1)\n"
            "os.write(1,bytes.fromhex(os.environ.get('FAKE_OUTPUT','3030313233340a')))\n"
            "os.write(2,b'SYNTHETIC_PRIVATE_DIAGNOSTIC')\n"
            "sys.exit(int(os.environ.get('FAKE_EXIT','0')))\n"
        )
        self.op.chmod(0o700)
        self.env = {
            "PATH": str(self.home),
            "HOME": str(self.home),
            "FAKE_RECORD": str(self.record),
        }

    def invoke(self, args, *, interactive=True, **env):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, self.env | env, clear=True):
            with patch("authy_local.cli.has_terminal", return_value=interactive):
                result = self.cli.main(args, stdin=io.StringIO(), stdout=out, stderr=err)
        self.assertNotIn("SYNTHETIC_PRIVATE_DIAGNOSTIC", out.getvalue() + err.getvalue())
        return result, out.getvalue(), err.getvalue()

    def show(self, **env):
        return self.invoke(
            ["show", ITEM, "--account", ACCOUNT, "--vault", VAULT, "--allow-pipe"],
            **env,
        )

    def calls(self):
        if not self.record.exists():
            return []
        return [json.loads(line) for line in self.record.read_text().splitlines()]

    def test_codes_preserve_leading_zeros_and_accept_only_exact_supported_forms(self):
        for raw, expected in (
            (b"001234", "001234"),
            (b"001234\n", "001234"),
            (b"001234\r\n", "001234"),
            (b"00001234\n", "00001234"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(self.models.parse_code(raw), expected)

    def test_malformed_output_never_becomes_a_code(self):
        for raw in (
            b"",
            b"12345",
            b"1234567",
            b"123456789",
            b" 123456",
            b"123456 ",
            b"123456\n\n",
            b"123456\r",
            b"123456\x1b[0m",
            b"\xff",
            "１２３４５６".encode(),
            b"otpauth://totp/SYNTHETIC",
            b"1" * 65,
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(self.error) as raised:
                    self.models.parse_code(raw)
                self.assertEqual(raised.exception.exit_code, 5)

    def test_success_is_code_only_with_exact_read_only_scoped_argv(self):
        result, out, err = self.show()
        self.assertEqual((result, out, err), (0, "001234\n", ""))
        retrieval = self.calls()[-1]
        self.assertTrue(all(row["sid"] == os.getsid(0) for row in self.calls()))
        self.assertEqual(
            retrieval["argv"],
            [
                "item",
                "get",
                ITEM,
                "--account",
                ACCOUNT,
                "--vault",
                VAULT,
                "--otp",
                "--format",
                "human-readable",
                "--no-color",
                "--cache=false",
                "--debug=false",
            ],
        )
        self.assertEqual(retrieval["env"].get("OP_BIOMETRIC_UNLOCK_ENABLED"), "true")

    def test_invalid_scope_fails_before_any_backend_call(self):
        for item in ("", "--reveal", "a" * 25, "a" * 27, "a" * 25 + "\n", "$(touch x)"):
            with self.subTest(item=item):
                status, out, _ = self.invoke(["show", item, "--account", ACCOUNT, "--vault", VAULT])
                self.assertEqual((status, out), (2, ""))
        self.assertEqual(self.calls(), [])

    def test_missing_scope_and_unimplemented_commands_never_contact_backend(self):
        for args in (["show", ITEM], ["copy", ITEM], ["select"], ["--unexpected"]):
            self.assertEqual(self.invoke(args)[0], 2)
        self.assertEqual(self.calls(), [])

    def test_terminal_and_pipe_guards_prevent_backend_calls(self):
        args = ["show", ITEM, "--account", ACCOUNT, "--vault", VAULT]
        self.assertEqual(self.invoke(args, interactive=False)[0], 3)
        self.assertEqual(self.invoke(args)[0], 3)
        self.assertEqual(self.calls(), [])

    def test_nonzero_and_malformed_success_never_print_code_or_diagnostic(self):
        for env, expected in (
            ({"FAKE_EXIT": "1"}, 4),
            ({"FAKE_OUTPUT": ""}, 5),
            ({"FAKE_OUTPUT": (b"1" * 65).hex()}, 5),
        ):
            with self.subTest(env=env):
                status, out, err = self.show(**env)
                self.assertEqual((status, out), (expected, ""))
                self.assertTrue(err)

    def test_unsupported_version_blocks_retrieval(self):
        status, out, _ = self.show(FAKE_VERSION="1.12.0")
        self.assertEqual((status, out), (3, ""))
        self.assertEqual([row["argv"] for row in self.calls()], [["--version"]])

    def test_foreign_auth_overrides_are_rejected_without_contacting_backend(self):
        for key in (
            "OP_SERVICE_ACCOUNT_TOKEN",
            "OP_CONNECT_TOKEN",
            "OP_CONNECT_HOST",
            "OP_SESSION",
            "OP_SESSION_example",
        ):
            with self.subTest(key=key):
                status, out, err = self.show(**{key: "SYNTHETIC_PRIVATE_DIAGNOSTIC"})
                self.assertEqual((status, out), (3, ""))
                self.assertNotIn(key, err)
        self.assertEqual(self.calls(), [])

    def test_debug_and_scope_defaults_cannot_override_explicit_contract(self):
        status, _, _ = self.show(
            OP_DEBUG="true",
            OP_FORMAT="json",
            OP_ACCOUNT="bad",
            OP_CACHE="true",
            OP_BIOMETRIC_UNLOCK_ENABLED="false",
        )
        self.assertEqual(status, 0)
        env = self.calls()[-1]["env"]
        self.assertNotIn("OP_DEBUG", env)
        self.assertNotIn("OP_FORMAT", env)
        self.assertNotIn("OP_ACCOUNT", env)

    def test_doctor_reports_capabilities_without_authentication(self):
        status, out, err = self.invoke(["doctor", "--json"])
        report = json.loads(out)
        self.assertEqual((status, err), (0, ""))
        self.assertEqual(report["authentication"]["state"], "unknown")
        self.assertEqual(report["op"]["state"], "available")
        self.assertEqual(report["clock"]["state"], "unknown")
        self.assertEqual([row["argv"] for row in self.calls()], [["--version"]])

    def test_doctor_missing_op_is_failure_without_sensitive_data(self):
        self.op.unlink()
        status, out, _ = self.invoke(["doctor", "--json"])
        self.assertEqual(status, 3)
        self.assertEqual(json.loads(out)["op"]["state"], "missing")

    def test_help_and_version_never_probe_backend(self):
        for args in (["--help"], ["--version"], ["show", "--help"]):
            status, out, err = self.invoke(args)
            self.assertEqual((status, err), (0, ""))
            self.assertTrue(out)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
