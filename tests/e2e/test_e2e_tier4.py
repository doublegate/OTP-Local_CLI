"""Tier 4: Real-World Application Scenarios (>=5 realistic application-level scenarios).

Simulates end-to-end operator journeys:
- Scenario 1: Fresh Operator Onboarding & Validation
- Scenario 2: Daily Workflow - Rapid TOTP Code Retrieval (Show & Copy)
- Scenario 3: Multi-Account Browser Navigation & Search Workflow
- Scenario 4: Multi-Backend Offline Operator Workflow
- Scenario 5: Fail-Closed Security & Resilient Recovery Scenario
- Scenario 6: Full Subprocess PTY Interactive TUI Execution
"""

import fcntl
import json
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import unittest

from tests.e2e.harness import E2EEnvironment

ITEM_AWS = "a" * 26
ITEM_GITHUB = "b" * 26
ACCOUNT = "c" * 26
VAULT = "v" * 26


class TestTier4RealWorldApplicationScenarios(unittest.TestCase):
    """Tier 4: Multi-step real-world application user scenarios."""

    def test_scenario_1_operator_onboarding_and_validation(self):
        """Scenario 1: Fresh operator onboarding, capability check, guide review, preview, and scope setup."""
        with E2EEnvironment() as env:
            # 1. CLI Doctor verification
            doc = env.invoke_cli(["doctor", "--json"])
            self.assertEqual(doc.exit_code, 0)
            doc_data = json.loads(doc.stdout)
            self.assertEqual(doc_data["op"]["state"], "available")

            # 2. Review Private Migration Guide via CLI
            guide = env.invoke_cli(["guide", "migration"])
            self.assertEqual(guide.exit_code, 0)
            self.assertIn("Migration and recovery procedure", guide.stdout)

            # 3. Interactive TUI session: preview installation, then configure saved scope
            # Key '8' (preview), type wheel path, 10, 10 (dismiss)
            # Key '9' (guide modal), 10 (dismiss)
            # Key '6' (saved scope), account, 10, vault, 10, tag (10)
            # Key '7' (doctor), 10 (dismiss)
            # 'q' (exit)
            keys = [
                ord("8"), *map(ord, str(env.wheel_path)), 10, 10,
                ord("9"), 10,
                ord("6"), *map(ord, ACCOUNT), 10, *map(ord, VAULT), 10, 10,
                ord("7"), 10,
                ord("q"),
            ]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            profiles = env.load_profiles()
            self.assertEqual(profiles["onepassword"]["account"], ACCOUNT)
            self.assertEqual(profiles["onepassword"]["vault"], VAULT)
            self.assertTrue(screen.has_text("Doctor") or screen.has_text("available"))

    def test_scenario_2_daily_totp_show_and_copy_workflow(self):
        """Scenario 2: Daily morning login routine - show AWS OTP, dismiss, copy GitHub OTP."""
        with E2EEnvironment() as env:
            env.save_profile({"onepassword": {"account": ACCOUNT, "vault": VAULT}})

            # Operator launches TUI:
            # 1. Key '3' (Show code), types AWS item, Enter, views code, Enter to dismiss
            # 2. Key '4' (Copy code), types GitHub item, Enter, copies to clipboard, Enter to dismiss
            # 3. 'q' (exit dashboard)
            keys = [
                ord("3"), *map(ord, ITEM_AWS), 10, 10,
                ord("4"), *map(ord, ITEM_GITHUB), 10, 10,
                ord("q"),
            ]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("001234"))
            self.assertEqual(env.clipboard_content().strip(), "001234")

    def test_scenario_3_token_browser_search_and_copy(self):
        """Scenario 3: Operator browses catalog, searches for AWS, switches search to GitHub, copies code."""
        with E2EEnvironment() as env:
            env.save_profile({"onepassword": {"account": ACCOUNT, "vault": VAULT}})

            # 1. Key '1' (browse items)
            # 2. Search '/AWS', 10 (confirm search), 's' (view AWS code), 10 (dismiss)
            # 3. Search '/', backspace 3x (clear AWS), 'Git', 10 (confirm), 'c' (copy), 10 (dismiss)
            # 4. Escape (exit browser), 'q' (exit dashboard)
            keys = [
                ord("1"),
                ord("/"), ord("A"), ord("W"), ord("S"), 10,
                ord("s"), 10,
                ord("/"), 263, 263, 263, ord("G"), ord("i"), ord("t"), 10,
                ord("c"), 10,
                27,
                ord("q"),
            ]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("001234"))
            self.assertEqual(env.clipboard_content().strip(), "001234")

    def test_scenario_4_multi_backend_offline_operator_workflow(self):
        """Scenario 4: Offline operator with multiple local profiles (pass-otp and totpm)."""
        with E2EEnvironment() as env:
            # Configure saved scopes for multiple backends
            profiles = {
                "onepassword": {"account": ACCOUNT, "vault": VAULT},
                "pass-otp": {"store": "/var/pass", "key_home": "/var/keys"},
                "totpm": {"config": "/var/totpm.conf"},
            }
            env.save_profile(profiles)

            # In TUI:
            # 1. Start in onepassword, retrieve AWS code via Show (3)
            # 2. Switch backend to pass-otp ('b', '2')
            # 3. Inspect saved scope ('6', verify, Esc)
            # 4. Switch backend to totpm ('b', '3')
            # 5. Exit ('q')
            keys = [
                ord("3"), *map(ord, ITEM_AWS), 10, 10,
                ord("b"), ord("2"),
                ord("6"), 27,
                ord("b"), ord("3"),
                ord("q"),
            ]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            loaded = env.load_profiles()
            self.assertEqual(loaded["totpm"]["config"], "/var/totpm.conf")
            self.assertEqual(loaded["pass-otp"]["store"], "/var/pass")

    def test_scenario_5_fail_closed_recovery_workflow(self):
        """Scenario 5: Backend subprocess failure handled fail-closed, recovery guide reviewed, scope adjusted."""
        with E2EEnvironment() as env:
            # Set up initial profile with wrong vault ID
            wrong_vault = "z" * 26
            env.save_profile({"onepassword": {"account": ACCOUNT, "vault": wrong_vault}})

            # Make mock op return failure when called with wrong vault
            op = env.bin_dir / "op"
            op.write_text(
                f"#!{sys.executable}\n"
                "import sys\n"
                "if sys.argv[1:] == ['--version']: print('2.39.0'); sys.exit(0)\n"
                "if 'item' in sys.argv and '--vault' in sys.argv:\n"
                "    idx = sys.argv.index('--vault') + 1\n"
                f"    if sys.argv[idx] == '{wrong_vault}':\n"
                "        print('vault not found', file=sys.stderr)\n"
                "        sys.exit(1)\n"
                "    print('001234')\n"
                "    sys.exit(0)\n"
                "sys.exit(1)\n"
            )
            op.chmod(0o700)

            # Operator workflow:
            # 1. Attempt Show code (3) -> fails fail-closed
            # 2. Review Migration Guide (9)
            # 3. Fix Saved Scope (6) -> sets correct vault
            # 4. Attempt Show code (3) -> succeeds!
            # 5. Exit ('q')
            keys = [
                ord("3"), *map(ord, ITEM_AWS), 10, 10,  # Fails, dismisses error modal
                ord("9"), 10,                           # Check migration guide
                ord("6"), 21, *map(ord, ACCOUNT), 10, 21, *map(ord, VAULT), 10, 10,  # Fix vault
                ord("3"), *map(ord, ITEM_AWS), 10, 10,  # Succeeds!
                ord("q"),
            ]
            code, screen = env.run_tui(keys)
            self.assertEqual(code, 0)
            self.assertTrue(screen.has_text("001234"))
            profiles = env.load_profiles()
            self.assertEqual(profiles["onepassword"]["vault"], VAULT)

    def test_scenario_6_pty_subprocess_interactive_tui(self):
        """Scenario 6: Real OS pseudo-terminal subprocess execution of 'python -m authy_local tui'."""
        with E2EEnvironment() as env:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))

            def setup_terminal():
                os.setsid()
                fcntl.ioctl(0, termios.TIOCSCTTY, 0)

            pty_env = dict(env.env)
            pty_env["TERM"] = "xterm"
            proc = subprocess.Popen(
                [sys.executable, "-m", "authy_local", "tui"],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                preexec_fn=setup_terminal,
                env=pty_env,
            )
            os.close(slave)
            rendered = b""
            try:
                deadline = time.monotonic() + 5
                while b"Authy Local" not in rendered and time.monotonic() < deadline:
                    if select.select([master], [], [], 0.1)[0]:
                        rendered += os.read(master, 65536)
                self.assertIn(b"Authy Local", rendered)
                # Send 'q' to quit
                os.write(master, b"q")
                exit_status = proc.wait(timeout=5)
                self.assertEqual(exit_status, 0)
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                os.close(master)
