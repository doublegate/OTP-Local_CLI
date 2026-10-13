"""Unit and integration tests for desktop quick-launcher picker."""

import io
import os
import unittest
from unittest.mock import patch

from authy_local import cli
from authy_local.errors import AppError
from authy_local.interaction import launch_picker, notify_desktop
from authy_local.processes import Completed


class TestPickerInteraction(unittest.TestCase):
    def setUp(self):
        self.rows = [
            ("item-1", "AWS Production [12345678]"),
            ("item-2", "GitHub: alice [87654321]"),
            ("item-3", "Google Cloud [11223344]"),
        ]
        self.env = {
            "PATH": "/usr/bin:/bin",
            "WAYLAND_DISPLAY": "wayland-1",
            "HOME": "/home/user",
        }

    def test_launch_picker_invalid_launcher_argument(self):
        with self.assertRaises(AppError) as ctx:
            launch_picker(self.rows, self.env, launcher="invalid-launcher")
        self.assertEqual(ctx.exception.exit_code, 2)

    def test_launch_picker_empty_rows_fails(self):
        with self.assertRaises(AppError) as ctx:
            launch_picker([], self.env, launcher="fzf")
        self.assertEqual(ctx.exception.exit_code, 4)

    @patch("shutil.which")
    @patch("authy_local.interaction.run")
    def test_launch_picker_rofi_success(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/rofi"
        mock_run.return_value = Completed(
            returncode=0,
            stdout=b"1\n",
        )
        selected = launch_picker(self.rows, self.env, launcher="rofi")
        self.assertEqual(selected, "item-2")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[0], "/usr/bin/rofi")
        self.assertIn("-dmenu", cmd)
        self.assertIn("-format", cmd)
        self.assertIn("i", cmd)

    @patch("shutil.which")
    @patch("authy_local.interaction.run")
    def test_launch_picker_rofi_cancellation(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/rofi"
        mock_run.return_value = Completed(
            returncode=1,
            stdout=b"",
        )
        with self.assertRaises(AppError) as ctx:
            launch_picker(self.rows, self.env, launcher="rofi")
        self.assertEqual(ctx.exception.exit_code, 130)

    @patch("shutil.which")
    @patch("authy_local.interaction.run")
    def test_launch_picker_wofi_success(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/wofi"
        mock_run.return_value = Completed(
            returncode=0,
            stdout=b"2: Google Cloud [11223344]\n",
        )
        selected = launch_picker(self.rows, self.env, launcher="wofi")
        self.assertEqual(selected, "item-3")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[0], "/usr/bin/wofi")
        self.assertIn("--dmenu", cmd)

    @patch("shutil.which")
    @patch("authy_local.interaction.choose_records")
    def test_launch_picker_fzf_success(self, mock_choose, mock_which):
        mock_choose.return_value = "item-1"
        selected = launch_picker(self.rows, self.env, launcher="fzf")
        self.assertEqual(selected, "item-1")
        mock_choose.assert_called_once_with(self.rows, self.env)

    @patch("shutil.which")
    @patch("authy_local.interaction.choose_records")
    def test_launch_picker_auto_falls_back_to_fzf_if_no_gui(self, mock_choose, mock_which):
        # No wofi, no rofi
        def _which(name, path=None):
            if name == "fzf":
                return "/usr/bin/fzf"
            return None

        mock_which.side_effect = _which
        mock_choose.return_value = "item-3"
        env = dict(self.env)
        env.pop("WAYLAND_DISPLAY", None)

        selected = launch_picker(self.rows, env, launcher="auto")
        self.assertEqual(selected, "item-3")
        mock_choose.assert_called_once_with(self.rows, env)

    @patch("shutil.which")
    @patch("authy_local.interaction.run")
    def test_notify_desktop_sends_notification(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/notify-send"
        notify_desktop("Test Title", "Test Message", self.env)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertIn("/usr/bin/notify-send", cmd)
        self.assertIn("Test Title", cmd)
        self.assertIn("Test Message", cmd)

    @patch("shutil.which")
    def test_notify_desktop_handles_missing_tool_silently(self, mock_which):
        mock_which.return_value = None
        # Should not raise exception
        notify_desktop("Test Title", "Test Message", self.env)


class TestPickerCLI(unittest.TestCase):
    def invoke(self, args, **env):
        out, err = io.StringIO(), io.StringIO()
        out.isatty = lambda: True
        full_env = {
            "PATH": "/usr/bin:/bin",
            "WAYLAND_DISPLAY": "wayland-1",
            "HOME": "/tmp",
        } | env
        with patch.dict(os.environ, full_env, clear=True):
            status = cli.main(args, stdout=out, stderr=err)
        return status, out.getvalue(), err.getvalue()

    def test_pick_help_displays_launcher_options(self):
        status, out, _ = self.invoke(["pick", "--help"])
        self.assertEqual(status, 0)
        self.assertIn("--launcher", out)
        self.assertIn("--no-notify", out)
        self.assertIn("--stdout", out)

    def test_pick_missing_scope_without_profile_fails(self):
        status, _, err = self.invoke(["pick", "--backend", "onepassword"])
        self.assertEqual(status, 2)

    @patch("authy_local.cli.retrieve")
    @patch("authy_local.interaction.list_items")
    @patch("authy_local.interaction.launch_picker")
    @patch("authy_local.cli.copy_code")
    @patch("authy_local.interaction.notify_desktop")
    def test_pick_onepassword_copies_code_and_notifies(
        self, mock_notify, mock_copy, mock_picker, mock_list, mock_retrieve
    ):
        mock_list.return_value = [("a" * 26, "AWS [12345678]")]
        mock_picker.return_value = "a" * 26
        mock_retrieve.return_value = "123456"

        status, out, _ = self.invoke(["pick", "--account", "b" * 26, "--vault", "c" * 26])
        self.assertEqual(status, 0)
        mock_picker.assert_called_once()
        mock_retrieve.assert_called_once()
        mock_copy.assert_called_once_with("123456", unittest.mock.ANY)
        mock_notify.assert_called_once()

    @patch("authy_local.cli.retrieve")
    @patch("authy_local.interaction.list_items")
    @patch("authy_local.interaction.launch_picker")
    def test_pick_stdout_flag_outputs_code_directly(self, mock_picker, mock_list, mock_retrieve):
        mock_list.return_value = [("a" * 26, "AWS [12345678]")]
        mock_picker.return_value = "a" * 26
        mock_retrieve.return_value = "654321"

        status, out, _ = self.invoke(
            ["pick", "--account", "b" * 26, "--vault", "c" * 26, "--stdout"]
        )
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "654321")
