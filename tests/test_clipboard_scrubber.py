"""Tests for automated clipboard scrubbing daemon."""

import unittest
from unittest.mock import MagicMock, patch

from authy_local.interaction import copy_code, scrub_clipboard


class TestClipboardScrubber(unittest.TestCase):
    def setUp(self):
        self.env = {
            "PATH": "/usr/bin:/bin",
            "WAYLAND_DISPLAY": "wayland-0",
        }

    def test_scrubber_clears_matching_otp_code(self):
        """Verify scrubber invokes wl-copy --clear when clipboard content matches code."""
        mock_check = MagicMock(returncode=0, stdout=b"123456\n")
        mock_clear = MagicMock(returncode=0, stdout=b"")

        with (
            patch("shutil.which", side_effect=lambda name, path="": f"/usr/bin/{name}"),
            patch("authy_local.interaction.run", side_effect=[mock_check, mock_clear]) as mock_run,
        ):
            thread = scrub_clipboard("123456", self.env, delay=0.01)
            self.assertIsNotNone(thread)
            thread.join(timeout=1.0)
            self.assertFalse(thread.is_alive())

            # 2 calls: 1st wl-paste --no-newline, 2nd wl-copy --clear
            self.assertEqual(mock_run.call_count, 2)
            first_cmd = mock_run.call_args_list[0].args[0]
            self.assertIn("wl-paste", first_cmd[0])
            self.assertIn("--no-newline", first_cmd)

            second_cmd = mock_run.call_args_list[1].args[0]
            self.assertIn("wl-copy", second_cmd[0])
            self.assertIn("--clear", second_cmd)

    def test_scrubber_skips_when_clipboard_content_changed(self):
        """Verify scrubber does NOT clear if clipboard holds different content."""
        # Clipboard now holds a different string (e.g. user copied a URL or password)
        mock_check = MagicMock(returncode=0, stdout=b"https://github.com\n")

        with (
            patch("shutil.which", side_effect=lambda name, path="": f"/usr/bin/{name}"),
            patch("authy_local.interaction.run", return_value=mock_check) as mock_run,
        ):
            thread = scrub_clipboard("123456", self.env, delay=0.01)
            self.assertIsNotNone(thread)
            thread.join(timeout=1.0)
            self.assertFalse(thread.is_alive())

            # Only checked, never called wl-copy --clear
            self.assertEqual(mock_run.call_count, 1)
            first_cmd = mock_run.call_args_list[0].args[0]
            self.assertIn("wl-paste", first_cmd[0])

    def test_scrubber_disabled_by_env_or_zero_delay(self):
        """Verify scrubber is not launched when disabled by environment or delay=0."""
        env_disabled = self.env | {"AUTHY_NO_CLIP_CLEAR": "1"}
        thread1 = scrub_clipboard("123456", env_disabled, delay=0.01)
        self.assertIsNone(thread1)

        thread2 = scrub_clipboard("123456", self.env, delay=0)
        self.assertIsNone(thread2)

    def test_scrubber_handles_missing_tools_gracefully(self):
        """Verify scrubber handles missing wl-paste or error silently without crashing."""
        with (
            patch("shutil.which", return_value=None),
            patch("authy_local.interaction.run", side_effect=Exception("Failed")),
        ):
            thread = scrub_clipboard("123456", self.env, delay=0.01)
            self.assertIsNotNone(thread)
            thread.join(timeout=1.0)
            self.assertFalse(thread.is_alive())

    def test_copy_code_triggers_scrubbing(self):
        """Verify copy_code spawns scrubbing daemon thread."""
        with (
            patch("authy_local.interaction.clipboard_capability", return_value="/usr/bin/wl-copy"),
            patch("authy_local.interaction.handoff"),
            patch("authy_local.interaction.scrub_clipboard") as mock_scrub,
        ):
            copy_code("654321", self.env)

            mock_scrub.assert_called_once_with("654321", self.env, delay=45.0)

    def test_darwin_copy_and_scrub(self):
        """Verify macOS uses pbcopy/pbpaste and scrubs with empty input."""
        mock_check = MagicMock(returncode=0, stdout=b"999888\n")
        mock_clear = MagicMock(returncode=0, stdout=b"")

        darwin_env = {"PATH": "/usr/bin:/bin"}
        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", side_effect=lambda name, path="": f"/usr/bin/{name}"),
            patch("authy_local.interaction.handoff") as mock_handoff,
            patch("authy_local.interaction.run", side_effect=[mock_check, mock_clear]) as mock_run,
        ):
            copy_code("999888", darwin_env, scrub_delay=0.01)

            mock_handoff.assert_called_once()
            cmd = mock_handoff.call_args[0][0]
            self.assertEqual(cmd, ["/usr/bin/pbcopy"])

            time_slept = 0
            while mock_run.call_count < 2 and time_slept < 1.0:
                import time

                time.sleep(0.02)
                time_slept += 0.02

            self.assertEqual(mock_run.call_count, 2)
            first_cmd = mock_run.call_args_list[0].args[0]
            self.assertIn("pbpaste", first_cmd[0])
            second_cmd = mock_run.call_args_list[1].args[0]
            self.assertIn("pbcopy", second_cmd[0])
            self.assertEqual(mock_run.call_args_list[1].kwargs.get("input_data"), b"")
