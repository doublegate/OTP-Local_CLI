"""Exercise the real module entry point and independently malformed responses."""

import fcntl
import io
import json
import os
import pty
import random
import runpy
import select
import signal
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from authy_local import cli, doctor
from authy_local.backends import onepassword
from authy_local.errors import AppError
from authy_local.models import parse_code

ITEM, ACCOUNT, VAULT = "a" * 26, "b" * 26, "c" * 26
SHOW = ["show", ITEM, "--account", ACCOUNT, "--vault", VAULT]


def take_terminal():
    os.setsid()
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)


class CliEdges(unittest.TestCase):
    def setUp(self):
        root = Path("/tmp/Authy-to-1Password_Local")
        root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="cli-edges-", dir=root)
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.record = self.home / "calls.jsonl"
        self.ready = self.home / "ready"
        self.env = {
            "PATH": str(self.home),
            "HOME": str(self.home),
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
            "FAKE_RECORD": str(self.record),
            "FAKE_READY": str(self.ready),
        }
        self.executable(
            "op",
            "import json,os,pathlib,sys,time\n"
            "with open(os.environ['FAKE_RECORD'],'a') as f:\n"
            " f.write(json.dumps(sys.argv[1:])+'\\n')\n"
            "if sys.argv[1:]==['--version']:\n"
            " print(os.environ.get('FAKE_VERSION','2.39.0'));sys.exit(0)\n"
            "pathlib.Path(os.environ['FAKE_READY']).touch()\n"
            "if os.environ.get('FAKE_HANG'): time.sleep(30)\n"
            "os.write(1,b'001234\\n')\n",
        )

    def executable(self, name, body):
        path = self.home / name
        path.write_text(f"#!{sys.executable}\n{body}")
        path.chmod(0o700)

    def calls(self):
        if not self.record.exists():
            return []
        return [json.loads(line) for line in self.record.read_text().splitlines()]

    def command(self, args, *, terminal=False, pipe=True, **extra):
        master = slave = None
        if terminal:
            master, slave = pty.openpty()
        child = subprocess.Popen(
            [sys.executable, "-m", "authy_local", *args],
            env=self.env | extra,
            stdin=slave if terminal else subprocess.DEVNULL,
            stdout=subprocess.PIPE if pipe else slave,
            stderr=subprocess.PIPE,
            preexec_fn=take_terminal if terminal else None,
        )
        if slave is not None:
            os.close(slave)
        self.addCleanup(self.stop, child)
        if master is not None:
            self.addCleanup(os.close, master)
        return child, master

    @staticmethod
    def stop(child):
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
        for stream in (child.stdout, child.stderr):
            if stream is not None:
                stream.close()

    def test_real_controlling_terminal_outputs_only_code(self):
        child, master = self.command(SHOW, terminal=True, pipe=False)
        _, err = child.communicate(timeout=5)
        ready, _, _ = select.select([master], [], [], 2)
        self.assertTrue(ready)
        self.assertEqual(os.read(master, 1024), b"001234\r\n")
        self.assertEqual((child.returncode, err), (0, b""))
        self.assertEqual(len(self.calls()), 2)

    def test_pipe_stdout_requires_explicit_opt_in_even_with_controlling_tty(self):
        child, _ = self.command(SHOW, terminal=True)
        out, err = child.communicate(timeout=5)
        self.assertEqual((child.returncode, out), (3, b""))
        self.assertTrue(err)
        self.assertEqual(self.calls(), [])

    def test_allow_pipe_preserves_interactive_stdin_requirement(self):
        child, _ = self.command([*SHOW, "--allow-pipe"])
        out, _ = child.communicate(timeout=5)
        self.assertEqual((child.returncode, out), (3, b""))
        self.assertEqual(self.calls(), [])

    def test_allow_pipe_accepts_real_controlling_tty_with_interactive_stdin(self):
        child, _ = self.command([*SHOW, "--allow-pipe"], terminal=True)
        out, err = child.communicate(timeout=5)
        self.assertEqual((child.returncode, out, err), (0, b"001234\n", b""))

    def test_sigint_returns_130_without_traceback_or_code(self):
        child, _ = self.command([*SHOW, "--allow-pipe"], terminal=True, FAKE_HANG="yes")
        deadline = time.monotonic() + 5
        while not self.ready.exists() and time.monotonic() < deadline:
            if child.poll() is not None:
                break
            time.sleep(0.01)
        self.assertTrue(self.ready.exists(), "Synthetic provider never started")
        child.send_signal(signal.SIGINT)
        out, err = child.communicate(timeout=5)
        self.assertEqual((child.returncode, out), (130, b""))
        self.assertNotIn(b"Traceback", err)
        self.assertNotIn(b"KeyboardInterrupt", err)

    def test_bad_arguments_never_echo_user_values_or_call_provider(self):
        sentinel = "SYNTHETIC_PRIVATE_ARGUMENT"
        cases = (
            ["--" + sentinel],
            ["show", sentinel, "--account", ACCOUNT, "--vault", VAULT],
            [*SHOW, "--unexpected", sentinel],
            [sentinel],
        )
        for args in cases:
            with self.subTest(args=args):
                child, _ = self.command(args)
                out, err = child.communicate(timeout=5)
                self.assertEqual((child.returncode, out), (2, b""))
                self.assertNotIn(sentinel.encode(), err)
                self.assertNotIn(b"Traceback", err)
        self.assertEqual(self.calls(), [])

    def inspect_doctor(self, **extra):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, self.env | extra, clear=True):
            status = cli.main(["doctor", "--json"], stdout=out, stderr=err)
        self.assertEqual(err.getvalue(), "")
        return status, json.loads(out.getvalue())

    def test_doctor_clock_yes_no_and_failed_probe_are_distinct(self):
        for body, state, exit_code in (
            ("print('yes')", "available", 0),
            ("print('no')", "missing", 3),
            ("raise SystemExit(1)", "unknown", 0),
            ("print('SYNTHETIC_NOT_A_CLOCK')", "unknown", 0),
        ):
            with self.subTest(state=state, body=body):
                self.executable("timedatectl", body)
                status, report = self.inspect_doctor()
                self.assertEqual((status, report["clock"]["state"]), (exit_code, state))
                self.assertEqual(report["authentication"]["state"], "unknown")
        self.assertTrue(all(call == ["--version"] for call in self.calls()))

    def test_doctor_malformed_version_never_echoes_provider_output(self):
        status, report = self.inspect_doctor(FAKE_VERSION="SYNTHETIC_PRIVATE_VERSION")
        self.assertEqual((status, report["op"]["state"]), (3, "unknown"))
        self.assertNotIn("SYNTHETIC_PRIVATE_VERSION", json.dumps(report))

    def test_doctor_probe_interrupt_is_cancellation_not_unknown_capability(self):
        self.executable("timedatectl", "print('yes')")
        for target in (onepassword, doctor):
            with self.subTest(probe=target.__name__):
                out, err = io.StringIO(), io.StringIO()
                with (
                    patch.dict(os.environ, self.env, clear=True),
                    patch.object(target, "run", side_effect=AppError(130)),
                ):
                    status = cli.main(["doctor", "--json"], stdout=out, stderr=err)
                self.assertEqual((status, out.getvalue()), (130, ""))
                self.assertNotIn("Traceback", err.getvalue())
                self.assertTrue(err.getvalue())

    def test_doctor_probe_deadlines_remain_unknown_not_false_success(self):
        self.executable("timedatectl", "print('yes')")
        for target, key, expected in (
            (onepassword, "op", 3),
            (doctor, "clock", 0),
        ):
            with (
                self.subTest(probe=key),
                patch.object(target, "run", side_effect=AppError(7)),
            ):
                status, report = self.inspect_doctor()
            self.assertEqual((status, report[key]["state"]), (expected, "unknown"))

    def test_doctor_text_report_discards_sensitive_stderr_from_fake_probes(self):
        self.executable(
            "timedatectl",
            "import os; os.write(2,b'SYNTHETIC_PRIVATE_CLOCK'); raise SystemExit(1)",
        )
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, self.env, clear=True):
            status = cli.main(["doctor"], stdout=out, stderr=err)
        self.assertEqual(status, 0)
        self.assertIn("clock: unknown\n", out.getvalue())
        self.assertIn("authentication: unknown\n", out.getvalue())
        self.assertNotIn("SYNTHETIC_PRIVATE_CLOCK", out.getvalue() + err.getvalue())
        self.assertEqual(err.getvalue(), "")

    def test_module_help_entrypoint_never_contacts_provider(self):
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.dict(os.environ, self.env, clear=True),
            patch.object(sys, "argv", ["otp-local", "--help"]),
            patch.object(sys, "stdout", out),
            patch.object(sys, "stderr", err),
            self.assertRaises(SystemExit) as caught,
        ):
            runpy.run_module("authy_local", run_name="__main__")
        self.assertEqual(caught.exception.code, 0)
        self.assertIn("doctor", out.getvalue())
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(self.calls(), [])

    def test_doctor_rejects_unsupported_platform(self):
        with patch.object(doctor.sys, "platform", "darwin"):
            status, report = self.inspect_doctor()
        self.assertEqual((status, report["platform"]["state"]), (3, "missing"))

    def test_doctor_rejects_unsupported_python(self):
        with patch.object(doctor.sys, "version_info", (3, 13, 0)):
            status, report = self.inspect_doctor()
        self.assertEqual((status, report["python"]["state"]), (3, "missing"))

    def test_show_rejects_unsupported_platform_before_provider_contact(self):
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.dict(os.environ, self.env, clear=True),
            patch.object(cli.sys, "platform", "darwin"),
            patch.object(cli, "has_terminal", return_value=True),
        ):
            status = cli.main([*SHOW, "--allow-pipe"], stdout=out, stderr=err)
        self.assertEqual((status, out.getvalue()), (3, ""))
        self.assertEqual(self.calls(), [])

    def test_show_rejects_unsupported_python_before_provider_contact(self):
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.dict(os.environ, self.env, clear=True),
            patch.object(cli.sys, "version_info", (3, 13, 0)),
            patch.object(cli, "has_terminal", return_value=True),
        ):
            status = cli.main([*SHOW, "--allow-pipe"], stdout=out, stderr=err)
        self.assertEqual((status, out.getvalue()), (3, ""))
        self.assertEqual(self.calls(), [])

    def test_terminal_requires_controlling_device_not_only_tty_stdin(self):
        class TtyInput(io.StringIO):
            def isatty(self):
                return True

        with patch.object(cli.os, "open", side_effect=PermissionError):
            self.assertFalse(cli.has_terminal(TtyInput()))

    def test_noninteractive_stdin_is_not_a_terminal(self):
        self.assertFalse(cli.has_terminal(io.StringIO()))

    def test_seeded_invalid_byte_insertions_cannot_escape_code_parser(self):
        rng = random.Random(1414)
        forbidden = [value for value in range(256) if value not in b"0123456789\r\n"]
        for _ in range(256):
            valid = rng.choice((b"001234", b"00001234\n"))
            where = rng.randrange(len(valid) + 1)
            raw = valid[:where] + bytes([rng.choice(forbidden)]) + valid[where:]
            with self.subTest(raw=raw):
                with self.assertRaises(AppError) as caught:
                    parse_code(raw)
                self.assertEqual(caught.exception.exit_code, 5)


if __name__ == "__main__":
    unittest.main()
