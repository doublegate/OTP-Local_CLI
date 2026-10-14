"""Tests for Federated multi-vault aggregation, search, and retrieval."""

import time
import unittest
from unittest.mock import patch

from authy_local import cli
from authy_local.errors import AppError
from authy_local.federation import (
    FederatedResolver,
    FederatedToken,
    _normalize_title,
)
from authy_local.tui_items import records as tui_records


class TestFederation(unittest.TestCase):
    def setUp(self):
        self.env = {
            "PATH": "/usr/bin:/bin",
            "HOME": "/tmp/test_home",
        }

    # -------------------------------------------------------------------------
    # 1. Badge & Token Initialization
    # -------------------------------------------------------------------------

    def test_federated_token_badges(self):
        tok1 = FederatedToken(key="item1", title="GitHub", backends=["bitwarden"])
        self.assertEqual(tok1.badge, "[BW]")
        self.assertEqual(tok1.display_label, "GitHub [BW]")

        tok2 = FederatedToken(key="item2", title="AWS", backends=["bitwarden", "keepass"])
        self.assertEqual(tok2.badge, "[BW+KP]")
        self.assertEqual(tok2.display_label, "AWS [BW+KP]")

        tok3 = FederatedToken(key="item3", title="Google", backends=["fido2", "keychain", "dpapi"])
        self.assertEqual(tok3.badge, "[FIDO2+KC+DP]")
        self.assertEqual(tok3.display_label, "Google [FIDO2+KC+DP]")

    def test_normalize_title(self):
        self.assertEqual(_normalize_title("GitHub (octocat) [Bitwarden]"), "GitHub (octocat)")
        self.assertEqual(_normalize_title("AWS [KeePassXC]"), "AWS")
        self.assertEqual(_normalize_title("Google [FIDO2]"), "Google")
        self.assertEqual(_normalize_title("Plain Title"), "Plain Title")

    # -------------------------------------------------------------------------
    # 2. Concurrent Multi-Vault Resolution & Deduplication
    # -------------------------------------------------------------------------

    @patch("authy_local.backends.bitwarden.bitwarden_records")
    @patch("authy_local.backends.keepass.keepass_records")
    @patch("authy_local.backends.fido2.fido2_records")
    def test_resolve_all_aggregation_and_deduplication(self, mock_fido, mock_keepass, mock_bw):
        mock_bw.return_value = [
            ("bw_gh", "GitHub (octocat) [Bitwarden]"),
            ("bw_slack", "Slack [Bitwarden]"),
        ]
        mock_keepass.return_value = [
            ("kp_gh", "GitHub (octocat) [KeePassXC]"),
            ("kp_aws", "AWS Console [KeePassXC]"),
        ]
        mock_fido.return_value = [
            ("fido_corp", "Corp SSO [FIDO2]"),
        ]

        resolver = FederatedResolver(candidate_backends=["bitwarden", "keepass", "fido2"])
        tokens = resolver.resolve_all(self.env)

        self.assertEqual(len(tokens), 4)
        titles = [t.title for t in tokens]
        self.assertEqual(titles, ["AWS Console", "Corp SSO", "GitHub (octocat)", "Slack"])

        # Check deduplicated GitHub token
        gh_tok = next(t for t in tokens if t.title == "GitHub (octocat)")
        self.assertIn("bitwarden", gh_tok.backends)
        self.assertIn("keepass", gh_tok.backends)
        self.assertIn("BW", gh_tok.badge)
        self.assertIn("KP", gh_tok.badge)

    # -------------------------------------------------------------------------
    # 3. Unified Search (Substring & Fuzzy)
    # -------------------------------------------------------------------------

    @patch("authy_local.backends.bitwarden.bitwarden_records")
    @patch("authy_local.backends.keepass.keepass_records")
    def test_search_substring_and_badge(self, mock_keepass, mock_bw):
        mock_bw.return_value = [
            ("bw1", "GitHub (personal) [Bitwarden]"),
            ("bw2", "GitLab [Bitwarden]"),
        ]
        mock_keepass.return_value = [
            ("kp1", "GitHub (work) [KeePassXC]"),
            ("kp2", "AWS [KeePassXC]"),
        ]

        resolver = FederatedResolver(candidate_backends=["bitwarden", "keepass"])

        # Search by query
        results = resolver.search("git", self.env)
        self.assertEqual(len(results), 3)

        # Search by specific term
        results_work = resolver.search("work", self.env)
        self.assertEqual(len(results_work), 1)
        self.assertEqual(results_work[0].title, "GitHub (work)")

        # Search by badge substring
        results_kp = resolver.search("KP", self.env)
        self.assertEqual(len(results_kp), 2)

        # Empty query returns all
        self.assertEqual(len(resolver.search("", self.env)), 4)

    # -------------------------------------------------------------------------
    # 4. Code Retrieval with Priority & Fallback
    # -------------------------------------------------------------------------

    @patch("authy_local.backends.bitwarden.bitwarden_code", return_value="111222")
    @patch("authy_local.backends.keepass.keepass_code", return_value="333444")
    def test_retrieve_code_preferred_priority(self, mock_kp_code, mock_bw_code):
        token = FederatedToken(key="gh", title="GitHub", backends=["bitwarden", "keepass"])
        resolver = FederatedResolver()

        # Default order (bitwarden first)
        code1 = resolver.retrieve_code(token, self.env)
        self.assertEqual(code1, "111222")
        mock_bw_code.assert_called_once_with("gh", self.env, timestamp=None)

        # Preferred keepass first
        mock_bw_code.reset_mock()
        mock_kp_code.reset_mock()
        code2 = resolver.retrieve_code(token, self.env, preferred_backend="keepass")
        self.assertEqual(code2, "333444")
        mock_kp_code.assert_called_once_with("gh", self.env, timestamp=None)
        mock_bw_code.assert_not_called()

    @patch("authy_local.backends.bitwarden.bitwarden_code", side_effect=AppError(4))
    @patch("authy_local.backends.keepass.keepass_code", return_value="999888")
    def test_retrieve_code_fallback_on_failure(self, mock_kp_code, mock_bw_code):
        token = FederatedToken(key="gh", title="GitHub", backends=["bitwarden", "keepass"])
        resolver = FederatedResolver()

        # Bitwarden fails, falls back to KeePassXC
        code = resolver.retrieve_code(token, self.env)
        self.assertEqual(code, "999888")
        mock_bw_code.assert_called_once()
        mock_kp_code.assert_called_once()

    def test_retrieve_code_all_fail_raises_app_error(self):
        token = FederatedToken(key="none", title="Nothing", backends=["bitwarden"])
        resolver = FederatedResolver()
        with patch("authy_local.backends.bitwarden.bitwarden_code", side_effect=Exception("error")):
            with self.assertRaises(AppError) as cm:
                resolver.retrieve_code(token, self.env)
            self.assertEqual(cm.exception.exit_code, 4)

    # -------------------------------------------------------------------------
    # 5. Performance Benchmark: Multi-Vault Resolution < 100ms
    # -------------------------------------------------------------------------

    @patch("authy_local.backends.bitwarden.bitwarden_records")
    @patch("authy_local.backends.keepass.keepass_records")
    @patch("authy_local.backends.fido2.fido2_records")
    @patch("authy_local.backends.keychain.keychain_records")
    @patch("authy_local.backends.dpapi.dpapi_records")
    def test_resolve_all_performance(self, mock_dpapi, mock_kc, mock_fido, mock_kp, mock_bw):
        mock_bw.return_value = [(f"bw_{i}", f"Item {i} [Bitwarden]") for i in range(50)]
        mock_kp.return_value = [(f"kp_{i}", f"Item {i} [KeePassXC]") for i in range(25, 75)]
        mock_fido.return_value = [("fido_1", "Hardware Key [FIDO2]")]
        mock_kc.return_value = []
        mock_dpapi.return_value = []

        resolver = FederatedResolver(
            candidate_backends=["bitwarden", "keepass", "fido2", "keychain", "dpapi"]
        )
        t0 = time.perf_counter()
        tokens = resolver.resolve_all(self.env)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertLess(elapsed_ms, 100.0, f"Resolution took {elapsed_ms:.2f}ms, target is < 100ms")
        self.assertEqual(len(tokens), 76)

    # -------------------------------------------------------------------------
    # 6. TUI & CLI Integration
    # -------------------------------------------------------------------------

    @patch("authy_local.federation.FederatedResolver.resolve_all")
    def test_tui_records_federated(self, mock_resolve):
        mock_resolve.return_value = [
            FederatedToken(
                key="gh",
                title="GitHub",
                backends=["bitwarden"],
                badge="[BW]",
                display_label="GitHub [BW]",
            ),
            FederatedToken(
                key="aws", title="AWS", backends=["keepass"], badge="[KP]", display_label="AWS [KP]"
            ),
        ]
        recs = tui_records("federated", {}, self.env)
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0], ("gh", "GitHub [BW]"))
        self.assertEqual(recs[1], ("aws", "AWS [KP]"))

    @patch("authy_local.cli.has_terminal", return_value=True)
    @patch("authy_local.federation.FederatedResolver.search")
    @patch("authy_local.federation.FederatedResolver.retrieve_code", return_value="654321")
    def test_cli_show_federated(self, mock_code, mock_search, mock_term):
        import io

        mock_search.return_value = [
            FederatedToken(key="gh", title="GitHub", backends=["bitwarden"])
        ]
        out = io.StringIO()
        out.isatty = lambda: True

        err = io.StringIO()
        code = cli.main(
            ["show", "--backend", "federated", "GitHub"],
            stdout=out,
            stderr=err,
        )
        self.assertEqual(code, 0)
        self.assertIn("654321", out.getvalue())

    @patch("authy_local.cli.has_terminal", return_value=True)
    @patch("authy_local.federation.FederatedResolver.resolve_all")
    @patch("authy_local.federation.FederatedResolver.retrieve_code", return_value="123789")
    @patch("authy_local.interaction.choose_records", return_value="gh")
    def test_cli_select_federated(self, mock_choose, mock_code, mock_resolve, mock_term):
        import io

        mock_resolve.return_value = [
            FederatedToken(
                key="gh", title="GitHub", backends=["bitwarden"], display_label="GitHub [BW]"
            )
        ]
        out = io.StringIO()
        out.isatty = lambda: True
        err = io.StringIO()

        code = cli.main(
            ["select", "--backend", "federated"],
            stdout=out,
            stderr=err,
        )
        self.assertEqual(code, 0)
        self.assertIn("123789", out.getvalue())
        mock_choose.assert_called_once()
        mock_code.assert_called_once()

    @patch("authy_local.cli.has_terminal", return_value=True)
    @patch("authy_local.federation.FederatedResolver.resolve_all")
    @patch("authy_local.federation.FederatedResolver.retrieve_code", return_value="987123")
    @patch("authy_local.interaction.launch_picker", return_value="gh")
    def test_cli_pick_federated(self, mock_picker, mock_code, mock_resolve, mock_term):
        import io

        mock_resolve.return_value = [
            FederatedToken(
                key="gh", title="GitHub", backends=["bitwarden"], display_label="GitHub [BW]"
            )
        ]
        out = io.StringIO()
        out.isatty = lambda: True
        err = io.StringIO()

        code = cli.main(
            ["pick", "--backend", "federated", "--stdout"],
            stdout=out,
            stderr=err,
        )
        self.assertEqual(code, 0)
        self.assertIn("987123", out.getvalue())
        mock_picker.assert_called_once()
        mock_code.assert_called_once()

    def test_federated_token_backend_keys(self):
        tok = FederatedToken(
            key="key1",
            title="GitHub",
            backends=["bitwarden", "keepass"],
            backend_keys={"bitwarden": "bw_uuid_1", "keepass": "/Vault/GitHub"},
        )
        self.assertEqual(tok.backend_keys["bitwarden"], "bw_uuid_1")
        self.assertEqual(tok.backend_keys["keepass"], "/Vault/GitHub")

        # Backward compatibility when backend_keys not provided
        tok2 = FederatedToken(key="key2", title="AWS", backends=["fido2"])
        self.assertEqual(tok2.backend_keys, {"fido2": "key2"})

    @patch("authy_local.backends.keepass.keepass_code")
    @patch("authy_local.backends.bitwarden.bitwarden_code", side_effect=Exception("BW locked"))
    def test_retrieve_code_uses_specific_backend_key(self, mock_bw, mock_kp):
        mock_kp.return_value = "888999"
        token = FederatedToken(
            key="bw_uuid_123",
            title="GitHub",
            backends=["bitwarden", "keepass"],
            backend_keys={"bitwarden": "bw_uuid_123", "keepass": "/Personal/GitHub"},
        )
        resolver = FederatedResolver()
        code = resolver.retrieve_code(token, self.env)
        self.assertEqual(code, "888999")
        # Ensure keepass received its own key '/Personal/GitHub', not 'bw_uuid_123'
        mock_kp.assert_called_once_with("/Personal/GitHub", self.env, timestamp=None)

    def test_resolve_all_empty_backends(self):
        resolver = FederatedResolver(candidate_backends=[])
        tokens = resolver.resolve_all(self.env)
        self.assertEqual(tokens, [])

    def test_resolve_all_timeout_nonblocking(self):
        def _slow_fetch(backend, env):
            time.sleep(0.5)
            return [(backend, "k1", "Title1")]

        resolver = FederatedResolver(candidate_backends=["bitwarden", "keepass"])
        with patch("authy_local.federation._fetch_records_for_backend", side_effect=_slow_fetch):
            t0 = time.perf_counter()
            tokens = resolver.resolve_all(self.env, timeout=0.05)
            elapsed = time.perf_counter() - t0
            # Ensure it didn't block for the full 0.5s * 2
            self.assertLess(elapsed, 0.3)
            self.assertEqual(tokens, [])

    @patch("authy_local.backends.onepassword.onepassword_records", create=True)
    @patch("authy_local.backends.local.pass_otp_records", create=True)
    @patch("authy_local.backends.local.totpm_records", create=True)
    def test_fetch_records_new_backends(self, mock_totpm, mock_pass, mock_op):
        from authy_local.federation import _fetch_records_for_backend

        mock_op.return_value = [("op_item1", "Item One [1Password]")]
        mock_pass.return_value = [("pass_entry1", "Entry One [pass-otp]")]
        mock_totpm.return_value = [("totpm_acc1", "Account One [totpm]")]

        res_op = _fetch_records_for_backend("onepassword", self.env)
        self.assertEqual(res_op, [("onepassword", "op_item1", "Item One")])

        res_pass = _fetch_records_for_backend("pass-otp", self.env)
        self.assertEqual(res_pass, [("pass-otp", "pass_entry1", "Entry One")])

        res_totpm = _fetch_records_for_backend("totpm", self.env)
        self.assertEqual(res_totpm, [("totpm", "totpm_acc1", "Account One")])

    @patch("authy_local.backends.onepassword.onepassword_code", return_value="111222", create=True)
    @patch("authy_local.backends.local.pass_otp_code", return_value="333444", create=True)
    @patch("authy_local.backends.local.totpm_code", return_value="555666", create=True)
    def test_retrieve_code_new_backends(self, mock_totpm, mock_pass, mock_op):
        resolver = FederatedResolver()

        tok_op = FederatedToken(key="op_1", title="OP", backends=["onepassword"])
        self.assertEqual(resolver.retrieve_code(tok_op, self.env), "111222")

        tok_pass = FederatedToken(key="pass_1", title="Pass", backends=["pass-otp"])
        self.assertEqual(resolver.retrieve_code(tok_pass, self.env), "333444")

        tok_totpm = FederatedToken(key="totpm_1", title="Totpm", backends=["totpm"])
        self.assertEqual(resolver.retrieve_code(tok_totpm, self.env), "555666")
