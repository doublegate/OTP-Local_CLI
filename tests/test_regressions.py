"""Regression coverage for malformed versions and interrupts during cleanup."""

import io
import json
import os
import signal
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from authy_local import cli, processes
from authy_local.errors import AppError


def proc_stat_state(pid: int) -> str:
    """Namespace-aware and host-proc-safe process state probe.

    Distinguishes an owned child from recycled/host kernel threads.
    """
    if pid <= 0:
        return "gone"

    try:
        wpid, _ = os.waitpid(pid, os.WNOHANG)
        if wpid == pid:
            return "Z"
    except ChildProcessError:
        pass

    try:
        os.kill(pid, 0)
    except ProcessLookupError, PermissionError:
        return "gone"

    proc_dir = Path(f"/proc/{pid}")
    stat_file = proc_dir / "stat"
    if stat_file.is_file():
        try:
            st = proc_dir.stat()
            cmdline = (proc_dir / "cmdline").read_bytes()
            if st.st_uid == os.getuid() and cmdline:
                stat_content = stat_file.read_text()
                return stat_content.rsplit(")", 1)[1].split()[0]
            return "gone"
        except FileNotFoundError, ProcessLookupError, PermissionError:
            return "gone"

    return "S" if sys.platform != "linux" else "gone"


class RegressionTests(unittest.TestCase):
    def setUp(self):
        root = Path("/tmp/Authy-to-1Password_Local")
        root.mkdir(exist_ok=True)
        self.scratch = tempfile.TemporaryDirectory(prefix="regressions-", dir=root)
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)

    def test_oversized_version_components_fail_closed_at_public_cli(self):
        executable = self.root / "op"
        retrieval_marker = self.root / "retrieval"
        for version in ("2." + "9" * 5000 + ".0", "2.39." + "9" * 5000):
            executable.write_text(
                f"#!{sys.executable}\n"
                "import pathlib,sys\n"
                "if sys.argv[1:] == ['--version']:\n"
                f" print({version!r})\n"
                "else:\n"
                f" pathlib.Path({str(retrieval_marker)!r}).touch()\n"
            )
            executable.chmod(0o700)
            for args in (
                ["doctor", "--json"],
                ["show", "a" * 26, "--account", "b" * 26, "--vault", "c" * 26, "--allow-pipe"],
            ):
                with self.subTest(component_length=len(version), command=args[0]):
                    out, err = io.StringIO(), io.StringIO()
                    with patch.dict(os.environ, {"PATH": str(self.root)}, clear=True):
                        with patch("authy_local.cli.has_terminal", return_value=True):
                            status = cli.main(args, stdin=io.StringIO(), stdout=out, stderr=err)
                    self.assertEqual(status, 3)
                    self.assertNotIn("9999999999", out.getvalue() + err.getvalue())
                    self.assertNotIn("Traceback", out.getvalue() + err.getvalue())
                    if args[0] == "doctor":
                        self.assertEqual(json.loads(out.getvalue())["op"]["state"], "unknown")
                    else:
                        self.assertEqual(out.getvalue(), "")
                    self.assertFalse(retrieval_marker.exists())

    def test_interrupt_during_cleanup_cannot_abandon_owned_child(self):
        pidfile = self.root / "child.pid"
        code = (
            "import os,pathlib,signal,time; "
            "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
            f"pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid())); "
            "os.write(1,b'x'*100000); time.sleep(30)"
        )
        original_sleep = time.sleep
        interrupted = False
        failure = None

        def interrupt_cleanup(seconds):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                os.kill(os.getpid(), signal.SIGINT)
            original_sleep(seconds)

        try:
            with patch("authy_local.processes.time.sleep", side_effect=interrupt_cleanup):
                try:
                    processes.run([sys.executable, "-c", code], env={"PATH": ""})
                except (AppError, KeyboardInterrupt) as error:
                    failure = error
            pid = int(pidfile.read_text())
            state = "unknown"
            for _ in range(50):
                state = proc_stat_state(pid)
                if state in ("gone", "Z"):
                    break
                time.sleep(0.01)
            self.assertIn(state, ("gone", "Z"), "Repeated interrupt abandoned an owned child")
            self.assertIsInstance(failure, AppError)
            self.assertEqual(failure.exit_code, 5)
        finally:
            if pidfile.exists():
                pid = int(pidfile.read_text())
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    os.waitpid(pid, 0)
                except ChildProcessError:
                    pass


if __name__ == "__main__":
    unittest.main()
