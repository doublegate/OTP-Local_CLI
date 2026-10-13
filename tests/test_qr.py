"""Unit tests for terminal QR code generation and diagnostic probes."""

import io
import unittest
from unittest.mock import patch

from authy_local import cli, doctor


class TestQrDiagnostics(unittest.IsolatedAsyncioTestCase):
    def test_doctor_includes_qr_and_pinentry_probes(self):
        env = {"PATH": "/usr/bin:/bin"}
        report = doctor.report(env)
        self.assertIn("qrencode", report)
        self.assertIn("pinentry", report)
        self.assertIn("gpg-agent", report)
        self.assertIn(report["qrencode"]["state"], ("available", "missing"))
        self.assertIn(report["pinentry"]["state"], ("available", "missing"))
        self.assertIn(report["gpg-agent"]["state"], ("available", "missing", "unknown"))

    def test_qr_cli_requires_terminal_or_pipe(self):
        out = io.StringIO()
        err = io.StringIO()
        # Non-terminal without --allow-pipe fails closed
        with patch("authy_local.cli.has_terminal", return_value=False):
            status = cli.main(["qr", "test_item"], stdout=out, stderr=err)
            self.assertEqual(status, 3)

    def test_qr_cli_missing_item_fails_closed(self):
        out = io.StringIO()
        err = io.StringIO()
        with patch("authy_local.cli.has_terminal", return_value=True):
            status = cli.main(["qr"], stdout=out, stderr=err)
            self.assertEqual(status, 2)

    async def test_action_show_token_qr_calls_run_with_env(self):
        from authy_local.processes import Completed
        from authy_local.tui import AuthyApp, InteractiveQrModal

        app = AuthyApp(dispatch=lambda args, out, diag: 0)
        async with app.run_test() as pilot:
            with (
                patch("shutil.which", return_value="/usr/bin/qrencode"),
                patch.object(
                    app,
                    "aget_token_uri",
                    return_value="otpauth://totp/Test:user?secret=JBSWY3DPEHPK3PXP",
                ),
                patch(
                    "authy_local.processes.run", return_value=Completed(0, b"mock_qr_output")
                ) as mock_run,
            ):
                app.action_show_token_qr("Test [12345678]", "onepassword")
                await pilot.pause()
                mock_run.assert_called_once()
                self.assertIn("env", mock_run.call_args.kwargs)
                self.assertIsInstance(app.screen, InteractiveQrModal)


if __name__ == "__main__":
    unittest.main()
