"""Public routing and enrollment guards use synthetic adapter boundaries."""

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from authy_local import cli


class BackendCLI(unittest.TestCase):
    def invoke(self, args, terminal=True):
        out, err = io.StringIO(), io.StringIO()
        out.isatty = lambda: True
        with patch.object(cli, "has_terminal", return_value=terminal):
            status = cli.main(args, stdout=out, stderr=err)
        return status, out.getvalue(), err.getvalue()

    def test_backend_flags_are_documented(self):
        status, out, _ = self.invoke(["show", "--help"])
        self.assertEqual(status, 0)
        self.assertIn("--backend", out)
        self.assertIn("--key-home", out)

    def test_local_backend_rejects_mixed_onepassword_scope(self):
        status, out, _ = self.invoke(
            [
                "show",
                "--backend",
                "pass-otp",
                "--store",
                "/missing",
                "--key-home",
                "/missing",
                "--entry",
                "synthetic",
                "--vault",
                "b" * 26,
            ]
        )
        self.assertEqual((status, out), (2, ""))

    def test_enrollment_requires_explicit_apply_before_secret_prompt(self):
        with patch("getpass.getpass") as hidden:
            status, out, _ = self.invoke(
                [
                    "enroll",
                    "--backend",
                    "pass-otp",
                    "--store",
                    "/missing",
                    "--key-home",
                    "/missing",
                    "--entry",
                    "synthetic",
                ]
            )
        self.assertEqual(status, 2)
        self.assertEqual(out, "")
        hidden.assert_not_called()

    def test_no_terminal_enrollment_never_reads_secret(self):
        with patch("getpass.getpass") as hidden:
            status, _, _ = self.invoke(
                [
                    "enroll",
                    "--backend",
                    "totpm",
                    "--config",
                    "/missing",
                    "--service",
                    "synthetic",
                    "--account",
                    "synthetic",
                    "--apply",
                ],
                terminal=False,
            )
        self.assertEqual(status, 3)
        hidden.assert_not_called()

    def test_guides_are_available_without_backend(self):
        status, out, err = self.invoke(["guide", "optional"])
        self.assertEqual((status, err), (0, ""))
        self.assertIn("pass-otp", out)
        status, out, err = self.invoke(["guide", "acceptance"])
        self.assertEqual((status, err), (0, ""))
        self.assertIn("private operator acceptance", out)

    def test_unknown_guide_cannot_read_arbitrary_paths(self):
        status, out, err = self.invoke(["guide", "../../private"])
        self.assertEqual((status, out), (2, ""))
        self.assertNotIn("private", err)

    def test_local_show_uses_only_explicit_backend(self):
        with (
            patch.object(cli, "local_scope", return_value=object()),
            patch("authy_local.backends.local.retrieve", return_value="001234") as local,
            patch.object(cli, "retrieve") as vendor,
        ):
            status, out, err = self.invoke(["show", "--backend", "pass-otp"])
        self.assertEqual((status, out, err), (0, "001234\n", ""))
        local.assert_called_once()
        vendor.assert_not_called()

    def test_local_failure_does_not_fall_back(self):
        from authy_local.errors import AppError

        with (
            patch.object(cli, "local_scope", return_value=object()),
            patch("authy_local.backends.local.retrieve", side_effect=AppError(4)),
            patch.object(cli, "retrieve") as vendor,
        ):
            status, out, _ = self.invoke(["show", "--backend", "totpm"])
        self.assertEqual((status, out), (4, ""))
        vendor.assert_not_called()

    def test_local_selection_routes_exact_record_and_copy(self):
        from authy_local.backends.local import LocalScope

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "synthetic.conf"
            config.touch(mode=0o600)
            scope = LocalScope("totpm", config=str(config))
            with (
                patch.object(cli, "local_scope", return_value=scope),
                patch("authy_local.backends.local.records", return_value=[("pilot:one", "pilot")]),
                patch("authy_local.interaction.choose_records", return_value="pilot:one"),
                patch("authy_local.backends.local.retrieve", return_value="001234") as local,
                patch.object(cli, "clipboard_capability"),
                patch.object(cli, "copy_code") as copy,
                patch.object(cli, "retrieve") as vendor,
            ):
                status, out, err = self.invoke(["select", "--backend", "totpm", "--copy"])
            self.assertEqual((status, out, err), (0, "", ""))
            self.assertEqual(
                (local.call_args.args[0].service, local.call_args.args[0].account), ("pilot", "one")
            )
            copy.assert_called_once()
            vendor.assert_not_called()

    def test_unavailable_enrollment_never_prompts(self):
        from authy_local.errors import AppError

        with (
            patch.object(cli, "local_scope", return_value=object()),
            patch("authy_local.backends.local.preflight", side_effect=AppError(3)),
            patch("getpass.getpass") as hidden,
        ):
            status, out, _ = self.invoke(["enroll", "--backend", "totpm", "--apply"])
        self.assertEqual((status, out), (3, ""))
        hidden.assert_not_called()

    def test_enrollment_confirms_hidden_input_and_sanitizes_mismatch(self):
        with (
            patch.object(cli, "local_scope", return_value=object()),
            patch("authy_local.backends.local.preflight"),
            patch("getpass.getpass", side_effect=["SYNTHETIC_SECRET", "other"]),
            patch("authy_local.backends.local.enroll") as enroll,
        ):
            status, out, err = self.invoke(["enroll", "--backend", "totpm", "--apply"])
        self.assertEqual((status, out), (2, ""))
        self.assertNotIn("SYNTHETIC_SECRET", err)
        enroll.assert_not_called()

    def test_enrollment_fails_closed_if_hidden_input_unavailable(self):
        import getpass
        import warnings

        def unavailable(*args, **kwargs):
            warnings.warn("synthetic", getpass.GetPassWarning, stacklevel=2)

        with (
            patch.object(cli, "local_scope", return_value=object()),
            patch("authy_local.backends.local.preflight"),
            patch("getpass.getpass", side_effect=unavailable),
            patch("authy_local.backends.local.enroll") as enroll,
        ):
            status, out, _ = self.invoke(["enroll", "--backend", "totpm", "--apply"])
        self.assertEqual((status, out), (3, ""))
        enroll.assert_not_called()

    def test_enrollment_success_never_prints_supplied_value(self):
        scope = object()
        with (
            patch.object(cli, "local_scope", return_value=scope),
            patch("authy_local.backends.local.preflight"),
            patch("getpass.getpass", return_value="SYNTHETIC_SECRET"),
            patch("authy_local.backends.local.enroll") as enroll,
        ):
            status, out, err = self.invoke(["enroll", "--backend", "totpm", "--apply"])
        self.assertEqual((status, out), (0, ""))
        self.assertNotIn("SYNTHETIC_SECRET", err)
        self.assertEqual(enroll.call_args.args[0], scope)

    def test_unlock_requires_terminal(self):
        status, out, _ = self.invoke(["unlock"], terminal=False)
        self.assertEqual((status, out), (3, ""))

    def test_unlock_delegates_to_interactive_unlock(self):
        with patch("authy_local.interaction.interactive_unlock") as mock_unlock:
            status, out, err = self.invoke(["unlock"])
        self.assertEqual((status, out), (0, ""))
        self.assertIn("Session unlocked.", err)
        mock_unlock.assert_called_once()

    def test_unlock_passes_account(self):
        with patch("authy_local.interaction.interactive_unlock") as mock_unlock:
            status, out, err = self.invoke(["unlock", "--account", "my.1password.com"])
        self.assertEqual((status, out), (0, ""))
        self.assertIn("Session unlocked.", err)
        self.assertEqual(mock_unlock.call_args.kwargs["account"], "my.1password.com")

    def test_interactive_unlock_validates_account_and_foreign_auth(self):
        from authy_local.errors import AppError
        from authy_local.interaction import interactive_unlock

        with self.assertRaises(AppError) as cm:
            interactive_unlock({"OP_SESSION": "fake"})
        self.assertEqual(cm.exception.exit_code, 3)

        with self.assertRaises(AppError) as cm:
            interactive_unlock({}, account="bad;injection")
        self.assertEqual(cm.exception.exit_code, 2)
