"""Tests for CLI subcommands, flag normalization, ergonomics, and daemon dispatch."""

import io
import json
import unittest
from unittest.mock import MagicMock, patch

from authy_local import cli
from authy_local.federation import FederatedToken


class TestCliSubcommands(unittest.TestCase):
    """Tests for CLI subcommands: list, search, daemon restart/clean, and root flags."""

    def test_build_parser_alias(self) -> None:
        """Verify build_parser alias exists and equals parser."""
        self.assertTrue(hasattr(cli, "build_parser"))
        self.assertIs(cli.build_parser, cli.parser)

    @patch("authy_local.federation.FederatedResolver.resolve_all")
    def test_list_subcommand_plain_text(self, mock_resolve_all) -> None:
        """Verify list subcommand outputs badge tags, account labels, and issuers."""
        tokens = [
            FederatedToken(
                key="github_alice",
                title="GitHub: alice",
                backends=["onepassword"],
                badge="[1P]",
                display_label="GitHub: alice [1P]",
            ),
            FederatedToken(
                key="aws_admin",
                title="AWS: admin",
                backends=["bitwarden"],
                badge="[BW]",
                display_label="AWS: admin [BW]",
            ),
            FederatedToken(
                key="corp_vpn",
                title="VPN: corp",
                backends=["yubikey"],
                badge="[YK]",
                display_label="VPN: corp [YK]",
            ),
            FederatedToken(
                key="kp_sec",
                title="KeePass: sec",
                backends=["keepass"],
                badge="[KP]",
                display_label="KeePass: sec [KP]",
            ),
            FederatedToken(
                key="gpg_pass",
                title="Pass: key",
                backends=["pass-otp"],
                badge="[PASS]",
                display_label="Pass: key [PASS]",
            ),
            FederatedToken(
                key="tpm_totp",
                title="TOTP: tpm",
                backends=["totpm"],
                badge="[TOTP]",
                display_label="TOTP: tpm [TOTP]",
            ),
        ]
        mock_resolve_all.return_value = tokens

        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["list"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        output = out.getvalue()
        self.assertIn("[1P] GitHub: alice", output)
        self.assertIn("[BW] AWS: admin", output)
        self.assertIn("[YK] VPN: corp", output)
        self.assertIn("[KP] KeePass: sec", output)
        self.assertIn("[PASS] Pass: key", output)
        self.assertIn("[TOTP] TOTP: tpm", output)

    @patch("authy_local.federation.FederatedResolver.resolve_all")
    def test_list_subcommand_json(self, mock_resolve_all) -> None:
        """Verify list subcommand with --json returns structured JSON list."""
        tok = FederatedToken(
            key="github_alice",
            title="GitHub: alice",
            backends=["onepassword"],
            badge="[1P]",
            display_label="GitHub: alice [1P]",
        )
        mock_resolve_all.return_value = [tok]

        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["list", "--json"], stdout=out, stderr=err)
        self.assertEqual(code, 0)

        data = json.loads(out.getvalue())
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["key"], "github_alice")
        self.assertEqual(data[0]["title"], "GitHub: alice")
        self.assertEqual(data[0]["badge"], "[1P]")
        self.assertEqual(data[0]["backends"], ["onepassword"])

    @patch("authy_local.federation.FederatedResolver")
    def test_list_subcommand_backend_filter(self, mock_resolver_cls) -> None:
        """Verify list subcommand respects --backend parameter."""
        mock_inst = MagicMock()
        mock_inst.resolve_all.return_value = []
        mock_resolver_cls.return_value = mock_inst

        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["list", "--backend", "bitwarden"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        mock_resolver_cls.assert_called_once_with(candidate_backends=["bitwarden"])

    @patch("authy_local.federation.FederatedResolver.search")
    def test_search_subcommand_plain_text(self, mock_search) -> None:
        """Verify search subcommand outputs matching tokens in plain text."""
        tok = FederatedToken(
            key="github_alice",
            title="GitHub: alice",
            backends=["onepassword"],
            badge="[1P]",
            display_label="GitHub: alice [1P]",
        )
        mock_search.return_value = [tok]

        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["search", "alice"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        self.assertIn("[1P] GitHub: alice", out.getvalue())

    @patch("authy_local.federation.FederatedResolver.search")
    def test_search_subcommand_no_matches(self, mock_search) -> None:
        """Verify search subcommand returns 1 and error notice when no matches found."""
        mock_search.return_value = []

        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["search", "nonexistent"], stdout=out, stderr=err)
        self.assertEqual(code, 1)
        self.assertIn("No tokens found", err.getvalue())

    @patch("authy_local.federation.FederatedResolver.search")
    def test_search_subcommand_json(self, mock_search) -> None:
        """Verify search subcommand with --json returns structured JSON list."""
        tok = FederatedToken(
            key="aws_root",
            title="AWS: root",
            backends=["bitwarden"],
            badge="[BW]",
            display_label="AWS: root [BW]",
        )
        mock_search.return_value = [tok]

        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["search", "root", "--json"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["key"], "aws_root")

    @patch("authy_local.federation.FederatedResolver.retrieve_code")
    @patch("authy_local.federation.FederatedResolver.search")
    def test_search_subcommand_code_single_match(self, mock_search, mock_retrieve) -> None:
        """Verify search --code outputs OTP code for single unambiguous match."""
        tok = FederatedToken(
            key="github_bob",
            title="GitHub: bob",
            backends=["bitwarden"],
            badge="[BW]",
        )
        mock_search.return_value = [tok]
        mock_retrieve.return_value = "889900"

        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["search", "bob", "--code"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().strip(), "889900")

    @patch("authy_local.federation.FederatedResolver.search")
    def test_search_subcommand_code_ambiguous(self, mock_search) -> None:
        """Verify search --code fails with returncode 1 when multiple tokens match."""
        tok1 = FederatedToken(key="acct1", title="Acct 1", backends=["bitwarden"])
        tok2 = FederatedToken(key="acct2", title="Acct 2", backends=["onepassword"])
        mock_search.return_value = [tok1, tok2]

        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["search", "acct", "--code"], stdout=out, stderr=err)
        self.assertEqual(code, 1)
        self.assertIn("Ambiguous search query", err.getvalue())

    @patch("authy_local.cli.copy_code")
    @patch("authy_local.federation.FederatedResolver.retrieve_code")
    @patch("authy_local.federation.FederatedResolver.search")
    def test_search_subcommand_copy(self, mock_search, mock_retrieve, mock_copy) -> None:
        """Verify search --copy copies code to clipboard."""
        tok = FederatedToken(key="acct1", title="Acct 1", backends=["bitwarden"])
        mock_search.return_value = [tok]
        mock_retrieve.return_value = "112233"

        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["search", "acct1", "--copy"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        mock_copy.assert_called_once_with("112233", unittest.mock.ANY)
        self.assertIn("Code copied to clipboard", err.getvalue())

    @patch("authy_local.daemon.daemon_start", return_value=0)
    @patch("authy_local.daemon.daemon_stop", return_value=0)
    def test_daemon_restart_dispatch(self, mock_stop, mock_start) -> None:
        """Verify daemon restart subcommand executes stop and start sequence."""
        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["daemon", "restart"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        mock_stop.assert_called_once()
        mock_start.assert_called_once()

    @patch("authy_local.daemon.daemon_clean", return_value=0)
    def test_daemon_clean_dispatch(self, mock_clean) -> None:
        """Verify daemon clean, daemon --clean, and root --clean invocations."""
        out = io.StringIO()
        err = io.StringIO()

        code1 = cli.main(["daemon", "clean"], stdout=out, stderr=err)
        self.assertEqual(code1, 0)
        self.assertEqual(mock_clean.call_count, 1)

        code2 = cli.main(["daemon", "--clean"], stdout=out, stderr=err)
        self.assertEqual(code2, 0)
        self.assertEqual(mock_clean.call_count, 2)

        code3 = cli.main(["--clean"], stdout=out, stderr=err)
        self.assertEqual(code3, 0)
        self.assertEqual(mock_clean.call_count, 3)

    @patch("authy_local.doctor.status", return_value=0)
    @patch("authy_local.doctor.report", return_value={"test": {"state": "available"}})
    def test_root_doctor_flag(self, mock_report, mock_status) -> None:
        """Verify root --doctor flag dispatches doctor report."""
        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["--doctor"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        self.assertIn("test: available", out.getvalue())

    @patch("authy_local.daemon.daemon_start", return_value=0)
    def test_root_daemon_flag(self, mock_start) -> None:
        """Verify root --daemon flag starts daemon."""
        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["--daemon"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        mock_start.assert_called_once()

    @patch("authy_local.daemon.daemon_status", return_value=0)
    def test_root_status_flag(self, mock_status) -> None:
        """Verify root --status flag queries daemon status."""
        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["--status"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        mock_status.assert_called_once()

    @patch("authy_local.daemon.daemon_stop", return_value=0)
    def test_root_stop_flag(self, mock_stop) -> None:
        """Verify root --stop flag stops daemon."""
        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["--stop"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        mock_stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
