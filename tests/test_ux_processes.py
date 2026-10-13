"""Synthetic stdin backpressure and clipboard-server lifetime regressions."""

import ctypes
import os
import signal
import sys
import tempfile
import time
import unittest
from pathlib import Path

from authy_local.errors import AppError
from authy_local.processes import handoff, run
from tests.test_processes import SYNTHETIC_ENV, alive

try:
    _libc = ctypes.CDLL(None)
    _PR_SET_CHILD_SUBREAPER = 36
    _libc.prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0)
except Exception:
    pass


class UXProcessTests(unittest.TestCase):
    def setUp(self):
        root = Path("/tmp/Authy-to-1Password_Local")
        root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root, prefix="ux-process-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def assert_error(self, code, operation):
        with self.assertRaises(AppError) as caught:
            operation()
        self.assertEqual(caught.exception.exit_code, code)

    def cleanup_pid(self, pid):
        if alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def assert_stopped(self, pid):
        deadline = time.monotonic() + 2
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(alive(pid), "Owned synthetic child remains alive")

    def test_large_input_and_both_output_pipes_progress_together(self):
        payload = b"synthetic-row\n" * 100000
        code = """
import os, sys, threading
def write(fd, data):
    while data:
        data = data[os.write(fd, data):]
threads = [threading.Thread(target=write, args=(fd, byte * 150000))
           for fd, byte in ((1, b'x'), (2, b'y'))]
for thread in threads: thread.start()
data = sys.stdin.buffer.read()
for thread in threads: thread.join()
os.write(1, str(len(data)).encode())
"""
        result = run(
            [sys.executable, "-c", code],
            env=SYNTHETIC_ENV,
            input_data=payload,
            stdout_cap=150020,
            stderr_cap=150000,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"x" * 150000 + str(len(payload)).encode())

    def test_early_stdin_close_still_collects_child_result(self):
        result = run(
            [sys.executable, "-c", "import os; os.close(0); os.write(1,b'closed')"],
            env=SYNTHETIC_ENV,
            input_data=b"x" * 1000000,
            timeout=3,
        )
        self.assertEqual((result.returncode, result.stdout), (0, b"closed"))

    def test_stalled_stdin_obeys_deadline_and_cleans_child(self):
        pidfile = self.home / "stalled-pid"
        code = (
            "import os,pathlib,signal,time; "
            "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
            f"pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(30)"
        )
        started = time.monotonic()
        self.assert_error(
            7,
            lambda: run(
                [sys.executable, "-c", code],
                env=SYNTHETIC_ENV,
                input_data=b"x" * 1000000,
                timeout=0.5,
            ),
        )
        self.assertLess(time.monotonic() - started, 3)
        pid = int(pidfile.read_text())
        self.addCleanup(self.cleanup_pid, pid)
        self.assert_stopped(pid)

    def server(self, ending):
        pidfile = self.home / "server-pid"
        content = self.home / "received"
        code = f"""
import os, pathlib, signal, sys, time
pathlib.Path({str(content)!r}).write_bytes(sys.stdin.buffer.read())
pid = os.fork()
if pid == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid()))
    os.write(1, b'SYNTHETIC_DISCARDED_OUTPUT')
    os.write(2, b'SYNTHETIC_DISCARDED_DIAGNOSTIC')
    time.sleep(30)
    os._exit(0)
while not pathlib.Path({str(pidfile)!r}).exists(): time.sleep(.01)
{ending}
"""
        return code, pidfile, content

    def invoke_server(self, ending, expected_error=None):
        code, pidfile, content = self.server(ending)
        try:

            def operation():
                handoff(
                    [sys.executable, "-c", code],
                    env=SYNTHETIC_ENV,
                    input_data=b"001234",
                    timeout=3.0,
                )

            if expected_error is None:
                operation()
            else:
                self.assert_error(expected_error, operation)
        finally:
            if pidfile.exists():
                self.addCleanup(self.cleanup_pid, int(pidfile.read_text()))
        self.assertEqual(content.read_bytes(), b"001234")
        return int(pidfile.read_text())

    def test_successful_clipboard_handoff_preserves_server_and_closes_stdin(self):
        pid = self.invoke_server("raise SystemExit(0)")
        self.assertTrue(alive(pid))

    def test_failed_clipboard_handoff_cleans_server_group(self):
        pid = self.invoke_server("raise SystemExit(1)", expected_error=6)
        self.assert_stopped(pid)

    def test_timed_out_clipboard_handoff_cleans_server_group(self):
        pid = self.invoke_server("time.sleep(30)", expected_error=7)
        self.assert_stopped(pid)
