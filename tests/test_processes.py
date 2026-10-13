"""Real, synthetic child processes exercise the bounded process boundary."""

import ctypes
import importlib
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SYNTHETIC_ENV = {"PATH": "", "LANG": "C.UTF-8"}

try:
    _libc = ctypes.CDLL(None)
    _PR_SET_CHILD_SUBREAPER = 36
    _libc.prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0)
except Exception:
    pass


def alive(pid):
    """Namespace-aware liveness probe that reaps zombies and checks namespace PID."""
    if pid <= 0:
        return False
    try:
        wpid, _ = os.waitpid(pid, os.WNOHANG)
        if wpid == pid:
            return False
    except ChildProcessError:
        pass

    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError, PermissionError:
        return False


def stop(child):
    if child.poll() is None:
        child.kill()
    child.wait(timeout=5)


class ProcessTests(unittest.TestCase):
    def setUp(self):
        try:
            self.processes = importlib.import_module("authy_local.processes")
            self.errors = importlib.import_module("authy_local.errors")
        except ModuleNotFoundError:
            self.fail("The planned bounded subprocess runner is not implemented")
        root = Path("/tmp/Authy-to-1Password_Local")
        root.mkdir(exist_ok=True)
        self.scratch = tempfile.TemporaryDirectory(prefix="process-tests-", dir=root)
        self.addCleanup(self.scratch.cleanup)

    def run_child(self, code, **kwargs):
        return self.processes.run(
            [sys.executable, "-c", code],
            env=dict(SYNTHETIC_ENV),
            preserve_session=True,
            **kwargs,
        )

    def test_preserved_session_has_separate_owned_process_group(self):
        result = self.run_child("import os; print(os.getsid(0), os.getpgrp(), os.getpid())")
        session, group, pid = map(int, result.stdout.split())
        self.assertEqual(session, os.getsid(0))
        self.assertEqual(group, pid)
        self.assertNotEqual(group, os.getpgrp())

    def test_default_still_isolates_session(self):
        result = self.processes.run(
            [sys.executable, "-c", "import os; print(os.getsid(0),os.getpid())"],
            env=dict(SYNTHETIC_ENV),
        )
        session, pid = map(int, result.stdout.split())
        self.assertEqual(session, pid)
        self.assertNotEqual(session, os.getsid(0))

    def assert_error(self, code, callback):
        with self.assertRaises(self.errors.AppError) as caught:
            callback()
        self.assertEqual(caught.exception.exit_code, code)

    def wait_for_file(self, path, child=None):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if path.exists() and path.stat().st_size:
                return
            if child is not None and child.poll() is not None:
                self.fail("Synthetic runner exited before its child became ready")
            time.sleep(0.01)
        self.fail("Synthetic child did not become ready")

    def assert_stopped(self, pid):
        deadline = time.monotonic() + 2
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.01)
        if alive(pid):
            os.kill(pid, signal.SIGKILL)
            self.fail("Runner left an owned child alive")

    def test_returns_exact_stdout_without_stderr(self):
        result = self.run_child(
            "import os; os.write(1, b'001234\\r\\n'); os.write(2, b'SYNTHETIC_DIAGNOSTIC')"
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"001234\r\n")
        self.assertFalse(hasattr(result, "stderr"))
        self.assertNotIn("SYNTHETIC_DIAGNOSTIC", repr(result))

    def test_nonzero_result_preserves_status_for_caller(self):
        result = self.run_child(
            "import os; os.write(1, b'001234'); "
            "os.write(2, b'SYNTHETIC_PRIVATE_ERROR'); raise SystemExit(9)"
        )
        self.assertEqual(result.returncode, 9)
        self.assertEqual(result.stdout, b"001234")
        self.assertNotIn("SYNTHETIC_PRIVATE_ERROR", repr(result))

    def test_only_explicit_environment_is_passed_to_child(self):
        result = self.processes.run(
            [sys.executable, "-c", "import os; print(os.getenv('SYNTHETIC_FLAG'))"],
            env={**SYNTHETIC_ENV, "SYNTHETIC_FLAG": "isolated"},
        )
        self.assertEqual(result.stdout, b"isolated\n")

    def test_missing_executable_maps_to_capability_failure(self):
        self.assert_error(
            3,
            lambda: self.processes.run(
                [str(Path(self.scratch.name) / "missing")], env=dict(SYNTHETIC_ENV)
            ),
        )

    def test_output_exactly_at_both_limits_succeeds(self):
        result = self.run_child(
            "import os; os.write(1, b'a'*64); os.write(2, b'b'*64)", stderr_cap=64
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"a" * 64)

    def test_stdout_flood_is_rejected(self):
        self.assert_error(5, lambda: self.run_child("import os; os.write(1, b'x'*100000)"))

    def test_stderr_flood_is_rejected(self):
        self.assert_error(
            5,
            lambda: self.run_child("import os; os.write(2, b'x'*100000)", stderr_cap=64),
        )

    def test_simultaneous_pipes_do_not_deadlock(self):
        result = self.run_child(
            "import os, threading; "
            "t=threading.Thread(target=lambda: os.write(2, b'b'*100000)); "
            "t.start(); os.write(1, b'a'*100000); t.join()",
            timeout=3,
            stdout_cap=100000,
            stderr_cap=100000,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"a" * 100000)

    def test_argv_is_not_interpreted_as_shell(self):
        marker = Path(self.scratch.name) / "must-not-exist"
        argument = f"$(touch {marker}); printf wrong"
        result = self.processes.run(
            [sys.executable, "-c", "import sys; print(sys.argv[1], end='')", argument],
            env=dict(SYNTHETIC_ENV),
            stdout_cap=1024,
        )
        self.assertEqual(result.stdout, argument.encode())
        self.assertFalse(marker.exists())

    def test_timeout_kills_signal_ignoring_process(self):
        pidfile = Path(self.scratch.name) / "pid"
        code = (
            "import os, pathlib, signal, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            f"pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(30)"
        )
        started = time.monotonic()
        self.assert_error(7, lambda: self.run_child(code, timeout=0.5))
        self.assertLess(time.monotonic() - started, 3)
        self.assert_stopped(int(pidfile.read_text()))

    def test_closed_pipes_do_not_remove_process_deadline(self):
        started = time.monotonic()
        self.assert_error(
            7,
            lambda: self.run_child(
                "import os, time; os.close(1); os.close(2); time.sleep(30)",
                timeout=0.2,
            ),
        )
        self.assertLess(time.monotonic() - started, 3)

    def descendant_code(self, pidfile, ending):
        descendant = (
            "import os, pathlib, signal, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            f"pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(30)"
        )
        return (
            "import pathlib, subprocess, sys, time, os; "
            f"subprocess.Popen([sys.executable, '-c', {descendant!r}]); "
            f"p=pathlib.Path({str(pidfile)!r}); "
            "\nwhile not p.exists(): time.sleep(.01)\n" + ending
        )

    def test_timeout_cleans_descendant_without_killing_unrelated_process(self):
        unrelated = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            env=dict(SYNTHETIC_ENV),
            start_new_session=True,
        )
        self.addCleanup(stop, unrelated)
        pidfile = Path(self.scratch.name) / "descendant"
        self.assert_error(
            7,
            lambda: self.run_child(self.descendant_code(pidfile, "time.sleep(30)"), timeout=0.5),
        )
        self.assert_stopped(int(pidfile.read_text()))
        self.assertIsNone(unrelated.poll())

    def test_cap_failure_cleans_descendants(self):
        pidfile = Path(self.scratch.name) / "descendant"
        self.assert_error(
            5,
            lambda: self.run_child(
                self.descendant_code(pidfile, "os.write(1,b'x'*100000); time.sleep(30)"),
                timeout=3,
            ),
        )
        self.assert_stopped(int(pidfile.read_text()))

    def test_exited_parent_with_open_descendant_pipe_obeys_deadline(self):
        pidfile = Path(self.scratch.name) / "descendant"
        self.assert_error(
            7,
            lambda: self.run_child(
                self.descendant_code(pidfile, "raise SystemExit(0)"), timeout=0.5
            ),
        )
        self.assert_stopped(int(pidfile.read_text()))

    def test_interrupt_maps_to_130_and_cleans_descendants(self):
        pidfile = Path(self.scratch.name) / "descendant"
        code = (
            "from authy_local.processes import run\n"
            "from authy_local.errors import AppError\n"
            "import sys\n"
            "try:\n"
            f" run([sys.executable, '-c', {self.descendant_code(pidfile, 'time.sleep(30)')!r}], "
            f"env={SYNTHETIC_ENV!r}, timeout=10, preserve_session=True)\n"
            "except AppError as error:\n"
            " raise SystemExit(error.exit_code)\n"
        )
        env = dict(SYNTHETIC_ENV)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        child = subprocess.Popen(
            [sys.executable, "-c", code],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.addCleanup(stop, child)
        self.wait_for_file(pidfile, child)
        child.send_signal(signal.SIGINT)
        self.assertEqual(child.wait(timeout=5), 130)
        self.assert_stopped(int(pidfile.read_text()))


if __name__ == "__main__":
    unittest.main()
