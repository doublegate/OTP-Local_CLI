"""Milestone M4 Adversarial Stress Testing & Empirical Challenge Suite.

Covers:
1. Dead/stale PID detection, socket cleanup, and auto-start recovery.
2. Corrupted PID file handling (garbage, empty, non-int, floats, binary bytes).
3. Adversarial PID handling (PID 0, negative PIDs, foreign user PID 1).
4. Stale PID stop and daemon clean combination matrix.
5. CLI subcommands (list, search, regex queries, invalid flags, RFC 8259 JSON).
6. Root compatibility flags and argv normalization.
"""

import io
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from authy_local import cli
from authy_local.daemon import (
    daemon_clean,
    daemon_restart,
    daemon_start,
    daemon_status,
    daemon_stop,
)
from authy_local.federation import FederatedToken
from authy_local.ipc import pid_path, socket_path


class TestMilestone4AdversarialStress(unittest.TestCase):
    """Empirical adversarial challenger test suite for Milestone M4."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="test_m4_adv_")
        self.env = {
            "HOME": self.temp_dir,
            "XDG_RUNTIME_DIR": os.path.join(self.temp_dir, "run"),
        }
        os.makedirs(self.env["XDG_RUNTIME_DIR"], mode=0o700, exist_ok=True)
        self.p_path = pid_path(self.env)
        self.s_path = socket_path(self.env)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # 1. Dead / Stale PID Handling
    # --------------------------------------------------------------------------

    @patch("authy_local.daemon.DaemonServer.start", return_value=None)
    def test_daemon_start_recovers_from_dead_pid(self, mock_server_start) -> None:
        """Verify daemon_start detects dead PID (99999999), unlinks stale artifacts, and starts."""
        self.p_path.write_text("99999999\n", encoding="ascii")
        self.s_path.touch()

        err_buf = io.StringIO()
        with patch("sys.stderr", err_buf):
            ret = daemon_start(foreground=True, env=self.env)

        self.assertEqual(ret, 0)
        self.assertFalse(self.p_path.exists())
        self.assertFalse(self.s_path.exists())
        self.assertIn("Cleaning up stale PID file", err_buf.getvalue())
        mock_server_start.assert_called_once()

    # --------------------------------------------------------------------------
    # 2. Corrupted PID File Variations
    # --------------------------------------------------------------------------

    def test_corrupted_pid_variations_across_lifecycle(self) -> None:
        """Test garbage strings, empty file, whitespace, floats, and binary bytes."""
        corrupt_payloads = [
            b"garbage_string_not_a_pid\n",
            b"!@#$%^&*()_+~`\n",
            b"",
            b"   \t\n  \n",
            b"0\n",
            b"-1\n",
            b"-99999\n",
            b"12345.678\n",
            b"0xDEADBEEF\n",
            b"NaN\n",
            b"Infinity\n",
            b"\x00\xff\xfe\x01\n",
            b"\x00" * 32,
        ]

        for payload in corrupt_payloads:
            with self.subTest(payload=payload):
                # Test daemon_clean on corrupted PID
                self.p_path.write_bytes(payload)
                self.s_path.touch()
                ret_clean = daemon_clean(env=self.env)
                self.assertEqual(ret_clean, 0)
                self.assertFalse(self.p_path.exists())
                self.assertFalse(self.s_path.exists())

                # Test daemon_stop on corrupted PID
                self.p_path.write_bytes(payload)
                self.s_path.touch()
                ret_stop = daemon_stop(env=self.env)
                self.assertEqual(ret_stop, 0)
                self.assertFalse(self.p_path.exists())
                self.assertFalse(self.s_path.exists())

                # Test daemon_start on corrupted PID
                self.p_path.write_bytes(payload)
                self.s_path.touch()
                with patch("authy_local.daemon.DaemonServer.start", return_value=None):
                    ret_start = daemon_start(foreground=True, env=self.env)
                self.assertEqual(ret_start, 0)
                self.assertFalse(self.p_path.exists())
                self.assertFalse(self.s_path.exists())

    # --------------------------------------------------------------------------
    # 3. Active Foreign User PID (PermissionError / PID 1)
    # --------------------------------------------------------------------------

    def test_foreign_user_pid_preservation(self) -> None:
        """Verify PermissionError (e.g. PID 1 / foreign user) safely refuses and preserves PID."""

        # On Linux, PID 1 is init/systemd (owned by root). If running as non-root, os.kill(1, 0) raises PermissionError.
        # We explicitly mock os.kill(1, ...) to raise PermissionError to guarantee deterministic behavior across all environments.
        def mock_kill_permission(pid, sig):
            if pid == 1:
                raise PermissionError(1, "Operation not permitted")
            raise ProcessLookupError(3, "No such process")

        with patch("os.kill", side_effect=mock_kill_permission):
            # 1. daemon_start with PID 1
            self.p_path.write_text("1\n", encoding="ascii")
            self.s_path.touch()
            err_buf = io.StringIO()
            with patch("sys.stderr", err_buf):
                ret_start = daemon_start(foreground=True, env=self.env)
            self.assertEqual(ret_start, 1)
            self.assertTrue(self.p_path.exists())
            self.assertIn("running under another user", err_buf.getvalue())

            # 2. daemon_stop with PID 1
            self.p_path.write_text("1\n", encoding="ascii")
            self.s_path.touch()
            err_buf2 = io.StringIO()
            with patch("sys.stderr", err_buf2):
                ret_stop = daemon_stop(env=self.env)
            self.assertEqual(ret_stop, 3)
            self.assertTrue(self.p_path.exists())
            self.assertIn("Permission denied stopping", err_buf2.getvalue())

            # 3. daemon_clean with PID 1
            self.p_path.write_text("1\n", encoding="ascii")
            self.s_path.touch()
            out_buf = io.StringIO()
            with patch("sys.stdout", out_buf):
                ret_clean = daemon_clean(env=self.env)
            self.assertEqual(ret_clean, 1)
            self.assertTrue(self.p_path.exists())
            self.assertIn("owned by another user", out_buf.getvalue())

    # --------------------------------------------------------------------------
    # 4. Adversarial PID Probing: PID 0 and Negative PIDs (Finding 1 Hardening)
    # --------------------------------------------------------------------------

    def test_adversarial_pid_zero_and_negative_stop_safety(self) -> None:
        """Verify daemon_stop, daemon_clean, and daemon_start reject 0 and negative PIDs without calling os.kill."""
        adversarial_pids = ["0\n", "-1\n", "-42\n", "-999999\n"]

        for raw in adversarial_pids:
            with self.subTest(raw_pid=raw, operation="daemon_stop"):
                self.p_path.write_text(raw, encoding="ascii")
                self.s_path.touch()
                with patch("os.kill") as mock_kill:
                    ret = daemon_stop(env=self.env)
                    self.assertEqual(ret, 0)
                    self.assertFalse(self.p_path.exists())
                    self.assertFalse(self.s_path.exists())
                    mock_kill.assert_not_called()

            with self.subTest(raw_pid=raw, operation="daemon_clean"):
                self.p_path.write_text(raw, encoding="ascii")
                self.s_path.touch()
                with patch("os.kill") as mock_kill:
                    ret = daemon_clean(env=self.env)
                    self.assertEqual(ret, 0)
                    self.assertFalse(self.p_path.exists())
                    self.assertFalse(self.s_path.exists())
                    mock_kill.assert_not_called()

            with self.subTest(raw_pid=raw, operation="daemon_start"):
                self.p_path.write_text(raw, encoding="ascii")
                self.s_path.touch()
                with (
                    patch("os.kill") as mock_kill,
                    patch("authy_local.daemon.DaemonServer.start", return_value=None),
                ):
                    ret = daemon_start(foreground=True, env=self.env)
                    self.assertEqual(ret, 0)
                    self.assertFalse(self.p_path.exists())
                    self.assertFalse(self.s_path.exists())
                    mock_kill.assert_not_called()

            with self.subTest(raw_pid=raw, operation="daemon_status"):
                self.p_path.write_text(raw, encoding="ascii")
                out = io.StringIO()
                with (
                    patch("os.kill") as mock_kill,
                    patch("sys.stdout", out),
                ):
                    code = daemon_status(env=self.env)
                    self.assertEqual(code, 0)
                    self.assertIn("Status: dead (stale PID file exists)", out.getvalue())
                    mock_kill.assert_not_called()

    def test_adversarial_pid_zero_and_negative_real_execution_preserves_process_group(self) -> None:
        """Verify real os.kill is NOT invoked on PID 0 or -1 (which would signal caller's process group)."""
        # If os.kill(0, ...) or os.kill(-1, ...) were called under POSIX, the test runner process group
        # would receive a signal. The hardened bounds validation guarantees os.kill is never called.
        for raw in ("0\n", "-1\n"):
            self.p_path.write_text(raw, encoding="ascii")
            self.s_path.touch()
            code_stop = daemon_stop(env=self.env)
            self.assertEqual(code_stop, 0)
            self.assertFalse(self.p_path.exists())

            self.p_path.write_text(raw, encoding="ascii")
            code_clean = daemon_clean(env=self.env)
            self.assertEqual(code_clean, 0)
            self.assertFalse(self.p_path.exists())

    # --------------------------------------------------------------------------
    # 5. Stale PID Stop & Daemon Clean Matrix
    # --------------------------------------------------------------------------

    def test_daemon_stop_missing_pid_orphaned_socket(self) -> None:
        """Verify daemon_stop unlinks orphaned socket when PID file does not exist."""
        self.s_path.touch()
        self.assertFalse(self.p_path.exists())
        self.assertTrue(self.s_path.exists())

        ret = daemon_stop(env=self.env)
        self.assertEqual(ret, 0)
        self.assertFalse(self.s_path.exists())

    def test_daemon_clean_combination_matrix(self) -> None:
        """Test daemon_clean across all artifact combinations."""
        # Case A: Dead PID + Dead socket
        self.p_path.write_text("99999999\n", encoding="ascii")
        self.s_path.touch()
        ret = daemon_clean(env=self.env)
        self.assertEqual(ret, 0)
        self.assertFalse(self.p_path.exists())
        self.assertFalse(self.s_path.exists())

        # Case B: Dead PID + Missing socket
        self.p_path.write_text("99999999\n", encoding="ascii")
        ret = daemon_clean(env=self.env)
        self.assertEqual(ret, 0)
        self.assertFalse(self.p_path.exists())

        # Case C: Missing PID + Orphaned socket
        self.s_path.touch()
        ret = daemon_clean(env=self.env)
        self.assertEqual(ret, 0)
        self.assertFalse(self.s_path.exists())

        # Case D: No artifacts at all
        out_buf = io.StringIO()
        with patch("sys.stdout", out_buf):
            ret = daemon_clean(env=self.env)
        self.assertEqual(ret, 0)
        self.assertIn("No stale daemon artifacts found", out_buf.getvalue())

        # Case E: Active process + responsive socket
        self.p_path.write_text(f"{os.getpid()}\n", encoding="ascii")
        self.s_path.touch()
        with patch("authy_local.daemon.send_ipc_request", return_value={"status": "ok"}):
            ret = daemon_clean(env=self.env)
        self.assertEqual(ret, 1)
        self.assertTrue(self.p_path.exists())
        self.assertTrue(self.s_path.exists())

        # Case F: Active process + unresponsive socket
        with patch("authy_local.daemon.send_ipc_request", return_value=None):
            ret = daemon_clean(env=self.env)
        self.assertEqual(ret, 1)
        self.assertTrue(self.p_path.exists())
        self.assertTrue(self.s_path.exists())

    # --------------------------------------------------------------------------
    # 6. CLI Subcommand: list
    # --------------------------------------------------------------------------

    @patch("authy_local.federation.FederatedResolver.resolve_all", return_value=[])
    def test_cli_list_empty_vault(self, mock_resolve) -> None:
        """Verify list subcommand outputs nothing on empty vault and returns 0."""
        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["list"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), "")

    @patch("authy_local.federation.FederatedResolver.resolve_all", return_value=[])
    def test_cli_list_empty_vault_json(self, mock_resolve) -> None:
        """Verify list --json on empty vault produces strictly valid RFC 8259 JSON '[]'."""
        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["list", "--json"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data, [])

    @patch("authy_local.federation.FederatedResolver.resolve_all")
    def test_cli_list_rfc8259_json_compliance(self, mock_resolve) -> None:
        """Verify list --json conforms strictly to expected schema and RFC 8259."""
        tok1 = FederatedToken(
            key="item1",
            title="Service Alpha: user1",
            backends=["onepassword", "bitwarden"],
            badge="[1P]",
        )
        tok1.account = "user1"
        tok1.issuer = "Service Alpha"

        tok2 = FederatedToken(
            key="item2",
            title="Service Beta",
            backends=["fido2"],
            badge="[FIDO]",
        )
        mock_resolve.return_value = [tok1, tok2]

        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["list", "--json"], stdout=out, stderr=err)
        self.assertEqual(code, 0)

        # Parse with strict JSON parser
        parsed = json.loads(out.getvalue())
        self.assertIsInstance(parsed, list)
        self.assertEqual(len(parsed), 2)
        required_keys = {"key", "title", "badge", "backends", "account", "issuer"}
        for item in parsed:
            self.assertTrue(required_keys.issubset(item.keys()))
        self.assertEqual(parsed[0]["account"], "user1")
        self.assertEqual(parsed[0]["issuer"], "Service Alpha")

    def test_cli_list_invalid_backend_and_flags(self) -> None:
        """Verify invalid backend choice and unrecognized flags exit with code 2."""
        out = io.StringIO()
        err = io.StringIO()

        code1 = cli.main(["list", "--backend", "nonexistent_backend"], stdout=out, stderr=err)
        self.assertEqual(code1, 2)
        self.assertIn("Invalid command or scope", err.getvalue())

        out2 = io.StringIO()
        err2 = io.StringIO()
        code2 = cli.main(["list", "--nonexistent-flag"], stdout=out2, stderr=err2)
        self.assertEqual(code2, 2)
        self.assertIn("Invalid command or scope", err2.getvalue())

    # --------------------------------------------------------------------------
    # 7. CLI Subcommand: search
    # --------------------------------------------------------------------------

    @patch("authy_local.federation.FederatedResolver.search")
    def test_cli_search_adversarial_regex_queries(self, mock_search) -> None:
        """Verify search queries containing regex characters do not crash or catastrophically backtrack."""
        mock_search.return_value = []
        regex_queries = [
            ".*",
            "[",
            "(",
            "\\",
            "+",
            "?",
            "^",
            "$",
            "(((a+)+)+)+",
            ".*.*.*.*.*.*.*.*.*.*.*.*a",
            "[a-z0-9_-]+@[a-z0-9.-]+",
            "\\\\",
            '""',
            "' OR '1'='1",
        ]

        for query in regex_queries:
            with self.subTest(query=query):
                out = io.StringIO()
                err = io.StringIO()
                code = cli.main(["search", query], stdout=out, stderr=err)
                self.assertEqual(code, 1)
                self.assertIn(f"No tokens found matching '{query}'", err.getvalue())

    @patch("authy_local.federation.FederatedResolver.search", return_value=[])
    def test_cli_search_empty_matches_json(self, mock_search) -> None:
        """Verify search --json with 0 matches returns valid JSON '[]' and exit code 1."""
        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["search", "notfound", "--json"], stdout=out, stderr=err)
        self.assertEqual(code, 1)
        data = json.loads(out.getvalue())
        self.assertEqual(data, [])

    @patch("authy_local.federation.FederatedResolver.search")
    def test_cli_search_code_and_copy_adversarial(self, mock_search) -> None:
        """Verify search --code and --copy behavior on 0, 1, and 2 matches."""
        tok1 = FederatedToken(key="t1", title="Token 1", backends=["bitwarden"])
        tok2 = FederatedToken(key="t2", title="Token 2", backends=["onepassword"])

        # Multiple matches with --code -> ambiguous error
        mock_search.return_value = [tok1, tok2]
        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["search", "token", "--code"], stdout=out, stderr=err)
        self.assertEqual(code, 1)
        self.assertIn("Ambiguous search query", err.getvalue())

        # Multiple matches with --copy -> ambiguous error
        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["search", "token", "--copy"], stdout=out, stderr=err)
        self.assertEqual(code, 1)
        self.assertIn("Ambiguous search query", err.getvalue())

        # No matches with --code -> not found error
        mock_search.return_value = []
        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["search", "missing", "--code"], stdout=out, stderr=err)
        self.assertEqual(code, 1)
        self.assertIn("No tokens found", err.getvalue())

        # No matches with --copy -> not found error
        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["search", "missing", "--copy"], stdout=out, stderr=err)
        self.assertEqual(code, 1)
        self.assertIn("No tokens found", err.getvalue())

    # --------------------------------------------------------------------------
    # 8. Root Compatibility Flags & Argv Normalization
    # --------------------------------------------------------------------------

    @patch("authy_local.doctor.status", return_value=0)
    @patch("authy_local.doctor.report", return_value={"item": {"state": "available"}})
    def test_root_flag_doctor_normalization(self, mock_report, mock_status) -> None:
        """Verify otp-local --doctor and otp-local --doctor --json normalization."""
        out = io.StringIO()
        err = io.StringIO()
        code1 = cli.main(["--doctor"], stdout=out, stderr=err)
        self.assertEqual(code1, 0)
        self.assertIn("item: available", out.getvalue())

        out2 = io.StringIO()
        err2 = io.StringIO()
        code2 = cli.main(["--doctor", "--json"], stdout=out2, stderr=err2)
        self.assertEqual(code2, 0)
        data = json.loads(out2.getvalue())
        self.assertIn("item", data)

    @patch("authy_local.daemon.daemon_start", return_value=0)
    def test_root_flag_daemon_normalization(self, mock_start) -> None:
        """Verify otp-local --daemon and otp-local --daemon --foreground."""
        out = io.StringIO()
        err = io.StringIO()
        code1 = cli.main(["--daemon"], stdout=out, stderr=err)
        self.assertEqual(code1, 0)
        mock_start.assert_called_with(foreground=False, env=unittest.mock.ANY)

        code2 = cli.main(["--daemon", "--foreground"], stdout=out, stderr=err)
        self.assertEqual(code2, 0)
        mock_start.assert_called_with(foreground=True, env=unittest.mock.ANY)

    @patch("authy_local.daemon.daemon_status", return_value=0)
    def test_root_flag_status_normalization(self, mock_status) -> None:
        """Verify otp-local --status."""
        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["--status"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        mock_status.assert_called_once()

    @patch("authy_local.daemon.daemon_stop", return_value=0)
    def test_root_flag_stop_normalization(self, mock_stop) -> None:
        """Verify otp-local --stop."""
        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["--stop"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        mock_stop.assert_called_once()

    @patch("authy_local.daemon.daemon_clean", return_value=0)
    def test_root_flag_clean_normalization(self, mock_clean) -> None:
        """Verify otp-local --clean."""
        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["--clean"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        mock_clean.assert_called_once()

    # --------------------------------------------------------------------------
    # 9. Concurrency & Race Conditions in daemon_clean
    # --------------------------------------------------------------------------

    def test_concurrent_daemon_clean_race_safety(self) -> None:
        """Verify concurrent executions of daemon_clean do not crash on race conditions."""
        import concurrent.futures

        self.p_path.write_text("99999999\n", encoding="ascii")
        self.s_path.touch()

        # Run 20 concurrent clean operations simultaneously
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futures = [ex.submit(daemon_clean, env=self.env) for _ in range(20)]
            results = [f.result() for f in futures]

        # All runs must succeed with exit code 0
        self.assertTrue(all(r == 0 for r in results))
        self.assertFalse(self.p_path.exists())
        self.assertFalse(self.s_path.exists())

    # --------------------------------------------------------------------------
    # 10. Daemon Status Matrix
    # --------------------------------------------------------------------------

    def test_daemon_status_matrix(self) -> None:
        """Verify daemon_status reporting across inactive, dead, active, and unresponsive."""
        # 1. Inactive (no PID file)
        out = io.StringIO()
        with patch("sys.stdout", out):
            code = daemon_status(env=self.env)
        self.assertEqual(code, 0)
        self.assertIn("Status: inactive", out.getvalue())

        # 2. Dead (stale PID file)
        self.p_path.write_text("99999999\n", encoding="ascii")
        out = io.StringIO()
        with patch("sys.stdout", out):
            code = daemon_status(env=self.env)
        self.assertEqual(code, 0)
        self.assertIn("Status: dead (stale PID file exists)", out.getvalue())

        # 3. Active (responsive)
        self.p_path.write_text(f"{os.getpid()}\n", encoding="ascii")
        resp = {"status": "ok", "uptime": 120, "cached_count": 5, "shm_name": "test-shm"}
        out = io.StringIO()
        with (
            patch("sys.stdout", out),
            patch("authy_local.daemon.send_ipc_request", return_value=resp),
        ):
            code = daemon_status(env=self.env)
        self.assertEqual(code, 0)
        self.assertIn("Status: active (running)", out.getvalue())
        self.assertIn("Cached Tokens: 5", out.getvalue())

        # 4. Unresponsive (active PID, unresponsive socket)
        out = io.StringIO()
        with (
            patch("sys.stdout", out),
            patch("authy_local.daemon.send_ipc_request", return_value=None),
        ):
            code = daemon_status(env=self.env)
        self.assertEqual(code, 1)
        self.assertIn("Status: unresponsive", out.getvalue())

    # --------------------------------------------------------------------------
    # 11. Daemon Restart Matrix
    # --------------------------------------------------------------------------

    @patch("authy_local.daemon.daemon_start", return_value=0)
    @patch("authy_local.daemon.daemon_stop", return_value=0)
    def test_daemon_restart_matrix(self, mock_stop, mock_start) -> None:
        """Verify daemon_restart stops existing instance if PID exists, then starts."""
        # Case A: PID file exists
        self.p_path.write_text("1234\n", encoding="ascii")
        code = daemon_restart(foreground=True, env=self.env)
        self.assertEqual(code, 0)
        mock_stop.assert_called_once_with(env=self.env)
        mock_start.assert_called_once_with(foreground=True, env=self.env)

        # Case B: PID file does not exist
        mock_stop.reset_mock()
        mock_start.reset_mock()
        self.p_path.unlink()
        code2 = daemon_restart(foreground=False, env=self.env)
        self.assertEqual(code2, 0)
        mock_stop.assert_not_called()
        mock_start.assert_called_once_with(foreground=False, env=self.env)

    # --------------------------------------------------------------------------
    # 12. Systemd Unit CLI Generation
    # --------------------------------------------------------------------------

    def test_cli_systemd_unit_command(self) -> None:
        """Verify 'otp-local daemon systemd-unit' outputs sandboxed systemd configuration."""
        out = io.StringIO()
        err = io.StringIO()
        code = cli.main(["daemon", "systemd-unit"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        output = out.getvalue()
        self.assertIn("[Unit]", output)
        self.assertIn("[Service]", output)
        self.assertIn("ReadWritePaths=%t %h/.local/state/authy-local", output)
        self.assertIn("LimitMEMLOCK=infinity", output)

    # --------------------------------------------------------------------------
    # 13. Search with Extreme Lengths and Unicode Strings
    # --------------------------------------------------------------------------

    @patch("authy_local.federation.FederatedResolver.search")
    def test_cli_search_extreme_lengths_and_unicode(self, mock_search) -> None:
        """Verify search handles 10,000-char queries and diverse Unicode safely."""
        mock_search.return_value = []
        queries = [
            "A" * 10000,
            "🔑 🔐 🛡️ 🚀",
            "اختبار التوثيق ثنائي العامل",
            "二要素認証トークン",
            "двухфакторная аутентификация",
            "überschüssige Sonderzeichen",
            "\t\t   \n\n",
        ]

        for q in queries:
            with self.subTest(query=q[:20]):
                out = io.StringIO()
                err = io.StringIO()
                code = cli.main(["search", q], stdout=out, stderr=err)
                self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
