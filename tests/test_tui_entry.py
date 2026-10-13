"""Public TUI entry enforces terminal policy and reuses real command dispatch."""

import fcntl
import io
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from authy_local import cli


class Entry(unittest.TestCase):
    def test_actual_curses_menu_quits_without_any_backend(self):
        scratch = Path("/tmp/Authy-to-1Password_Local")
        scratch.mkdir(exist_ok=True)
        home = tempfile.TemporaryDirectory(prefix="tui-entry-", dir=scratch)
        self.addCleanup(home.cleanup)
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))

        def terminal():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        child = subprocess.Popen(
            [sys.executable, "-m", "authy_local", "tui"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            preexec_fn=terminal,
            env={
                "HOME": home.name,
                "PATH": "",
                "TERM": "xterm",
                "PYTHONPATH": os.environ.get(
                    "PYTHONPATH", str(Path(__file__).resolve().parents[1] / "src")
                ),
            },
        )
        os.close(slave)
        rendered = b""
        try:
            deadline = time.monotonic() + 5
            while b"Authy Local" not in rendered and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    rendered += os.read(master, 65536)
            self.assertIn(b"Authy Local", rendered)
            os.write(master, b"q")
            self.assertEqual(child.wait(timeout=5), 0)
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            os.close(master)

    def test_no_terminal_fails_before_tui(self):
        with patch.object(cli, "has_terminal", return_value=False):
            self.assertEqual(cli.main(["tui"], stdout=io.StringIO(), stderr=io.StringIO()), 3)

    def test_shared_dispatch_and_preview_only_callback(self):
        from authy_local import tui

        output, diagnostic = io.StringIO(), io.StringIO()
        output.isatty = lambda: True

        def screen(dispatch, *, preview):
            out, err = io.StringIO(), io.StringIO()
            self.assertEqual(dispatch(["show", "bad"], out, err), 2)
            self.assertEqual(out.getvalue(), "")
            self.assertEqual(preview("/missing-synthetic.whl", out, err), 3)
            return 0

        with patch.object(cli, "has_terminal", return_value=True), patch.object(tui, "run", screen):
            self.assertEqual(cli.main(["tui"], stdout=output, stderr=diagnostic), 0)
