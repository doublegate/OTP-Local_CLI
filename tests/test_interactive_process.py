"""Actual fzf under a synthetic controlling terminal, never a real vault."""

import fcntl
import json
import os
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from pathlib import Path


class InteractiveProcess(unittest.TestCase):
    def test_backend_style_child_retains_controlling_terminal(self):
        master, slave = pty.openpty()
        expected_tty = os.ttyname(slave)
        child_code = (
            "import os,json; fd=os.open('/dev/tty',os.O_RDONLY); "
            "print(json.dumps([os.getsid(0),os.getpgrp(),os.getpid(),os.ttyname(fd)]))"
        )
        code = (
            "import os,json\nfrom authy_local.processes import run\n"
            f"r=run([{sys.executable!r},'-c',{child_code!r}],env={{}},"
            "preserve_session=True,stdout_cap=1024,timeout=3)\n"
            "print(json.dumps([os.getsid(0),os.getpgrp(),r.returncode,json.loads(r.stdout)]))"
        )

        def terminal():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        try:
            child = subprocess.Popen(
                [sys.executable, "-c", code],
                stdin=slave,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=terminal,
            )
            try:
                out, err = child.communicate(timeout=5)
                self.assertEqual((child.returncode, err), (0, b""))
                session, group, status, backend = json.loads(out)
                self.assertEqual(status, 0)
                self.assertEqual(backend[0], session)
                self.assertEqual(backend[1], backend[2])
                self.assertNotEqual(backend[1], group)
                # /dev/tty refers to the controlling terminal regardless of its alias.
                self.assertEqual(backend[3], "/dev/tty")
                self.assertTrue(expected_tty.startswith("/dev/pts/"))
            finally:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        finally:
            os.close(master)
            os.close(slave)

    @unittest.skipUnless(shutil.which("fzf"), "fzf unavailable")
    def test_actual_fzf_accepts_selection_in_controlling_terminal(self):
        with tempfile.TemporaryDirectory(dir="/tmp/Authy-to-1Password_Local") as directory:
            result = Path(directory) / "result"
            code = (
                "import json,os,pathlib\n"
                "from authy_local.processes import run\n"
                f"r=run([{shutil.which('fzf')!r},'--delimiter=\\t','--accept-nth=1',"
                "'--no-multi','--height=10','--bind=load:accept'],"
                "env={'TERM':'xterm','PATH':'/usr/bin'},"
                "input_data=b'0\\tSynthetic\\n',timeout=5,stdout_cap=128,interactive=True)\n"
                f"pathlib.Path({str(result)!r}).write_text(json.dumps([r.returncode,r.stdout.decode()]))\n"
            )
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))

            def terminal():
                os.setsid()
                fcntl.ioctl(0, termios.TIOCSCTTY, 0)

            child = subprocess.Popen(
                [sys.executable, "-c", code],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                preexec_fn=terminal,
            )
            os.close(slave)
            try:
                # Wait for the input-load event rather than guessing when Enter
                # is safe. Reply only to actual cursor-position queries; an
                # unsolicited reply can become a search query and hide the row.
                pending = b""
                deadline = time.monotonic() + 8
                while child.poll() is None and time.monotonic() < deadline:
                    if not select.select([master], [], [], 0.1)[0]:
                        continue
                    try:
                        pending += os.read(master, 65536)
                    except OSError:
                        break
                    while b"\x1b[6n" in pending:
                        _, pending = pending.split(b"\x1b[6n", 1)
                        os.write(master, b"\x1b[1;1R")
                    pending = pending[-3:]
                self.assertEqual(child.wait(timeout=1), 0)
                self.assertEqual(json.loads(result.read_text()), [0, "0\n"])
            finally:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                os.close(master)
