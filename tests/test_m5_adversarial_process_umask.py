"""Adversarial Stress Suite for Milestone M5: Process Safety, Umask Invariance & TUI Edges.

Authored by Challenger 2 (Empirical Challenger) to adversarially test:
1. Process Safety & Isolation:
   - alive(pid) behavior under simulated zombie PIDs (direct child and subreaper reparented),
     non-existent PIDs, and permission-denied PIDs (no false positive returns).
   - Concurrent process reaping under heavy thread/process stress.
2. Host Umask Invariance:
   - Directory permissions and ownership checks in optional_setup across extreme umasks
     (0000, 0002, 0022, 0027, 0077).
   - Profile storage permissions in tui_profiles across extreme umasks.
   - Refusal of unsafe group/world writable parent directories (0775, 0777).
3. Untested Branch & Boundary Probing:
   - Edge branches and interface contracts in tui_items.py (fuzzy_filter, SearchIndex, _values,
     _local_scope, arguments, remove, records).
   - Edge branches and security boundaries in tui_profiles.py (valid_tag, _validate, _check_path,
     _object duplicate keys, payload limits).
   - Error handling and modal protection in tui.py (scope validation failure, save failure,
     deletion failure modal).
"""

import ctypes
import hashlib
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from textual.widgets import Button, Input, Static

from authy_local import optional_setup, tui_items, tui_profiles
from authy_local.errors import AppError
from authy_local.tui import (
    AuthyApp,
    MessageModal,
    SavedScopeModal,
    TokenBrowserScreen,
    TokenOptionList,
)
from tests.test_processes import alive


class TestProcessSafetyAdversarial(unittest.TestCase):
    """Adversarial stress testing for alive(pid) and process isolation."""

    @classmethod
    def setUpClass(cls):
        try:
            libc = ctypes.CDLL(None)
            libc.prctl(36, 1, 0, 0, 0)  # PR_SET_CHILD_SUBREAPER
        except Exception:
            pass

    def test_alive_nonexistent_positive_pids_return_false(self):
        """Positive non-existent PIDs must never return True."""
        for invalid_pid in (999999, 2147483647):
            with self.subTest(pid=invalid_pid):
                self.assertFalse(alive(invalid_pid))

    def test_alive_nonpositive_pids_posix_broadcast_edge_case(self):
        """Verify non-positive PIDs return False with the PID guard."""
        # alive() in tests/test_processes.py guards pid <= 0, returning False safely.
        self.assertFalse(alive(0))
        self.assertFalse(alive(-1))

    def test_alive_permission_denied_returns_false_without_exception(self):
        """Permission-denied PIDs must safely return False without crashing."""
        with mock.patch("os.kill", side_effect=PermissionError("Operation not permitted")):
            self.assertFalse(alive(12345))

    def test_alive_process_lookup_error_returns_false_without_exception(self):
        """ProcessLookupError during probe must safely return False."""
        with mock.patch("os.kill", side_effect=ProcessLookupError("No such process")):
            self.assertFalse(alive(54321))

    def test_alive_direct_child_zombie_returns_false_and_is_reaped(self):
        """Direct child process that has exited (zombie) must be reaped and return False."""
        child = os.fork()
        if child == 0:
            os._exit(0)
        # Give child a moment to terminate into zombie state
        time.sleep(0.05)
        # First probe reaps the zombie child
        self.assertFalse(alive(child))
        # Second probe confirms it is completely gone
        self.assertFalse(alive(child))

    def test_alive_subreaper_reparented_orphan_zombie_returns_false(self):
        """Orphaned grandchild reparented to subreaper must be reaped and return False."""
        pipe_r, pipe_w = os.pipe()
        child = os.fork()
        if child == 0:
            os.close(pipe_r)
            grandchild = os.fork()
            if grandchild == 0:
                os._exit(0)
            os.write(pipe_w, str(grandchild).encode())
            os.close(pipe_w)
            os._exit(0)

        os.close(pipe_w)
        grandchild_pid = int(os.read(pipe_r, 32).decode())
        os.close(pipe_r)
        os.waitpid(child, 0)  # reap immediate child

        time.sleep(0.05)  # grandchild now reparented to subreaper
        self.assertFalse(alive(grandchild_pid))

    def test_concurrent_child_exit_stress(self):
        """Concurrent child creation and termination must not leak or crash alive()."""
        failures = []
        children = [
            subprocess.Popen(
                [sys.executable, "-c", "import sys; sys.exit(0)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(30)
        ]
        for child in children:
            child.wait(timeout=5)
            # Child has exited; alive probe must reap / report dead immediately
            if alive(child.pid):
                failures.append(f"PID {child.pid} falsely reported alive")

        self.assertEqual(failures, [])


class TestUmaskInvarianceAdversarial(unittest.TestCase):
    """Adversarial stress testing for filesystem permissions under extreme host umasks."""

    def _setup_runtime_scratch(self, scratch):
        home = Path(scratch) / "home"
        source = Path(scratch) / "source"
        source.mkdir(parents=True)
        (source / "otp.bash").write_bytes(b"synthetic extension")
        (source / "LICENSE").write_bytes(b"synthetic license")
        binary = Path(scratch) / "totpm"
        binary.write_bytes(b"synthetic binary")
        replacements = {
            "PASS_OTP_SHA256": hashlib.sha256(b"synthetic extension").hexdigest(),
            "PASS_OTP_LICENSE_SHA256": hashlib.sha256(b"synthetic license").hexdigest(),
            "hardened_extension": lambda value: value,
            "TOTPM_BINARY_SHA256": hashlib.sha256(b"synthetic binary").hexdigest(),
        }
        for name, replacement in replacements.items():
            patcher = mock.patch.object(optional_setup, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        return home, source, binary

    def test_optional_setup_apply_runtime_under_extreme_umasks(self):
        """apply_runtime must create private files/dirs (0700/0600) invariant of host umask."""
        for test_umask in (0o000, 0o002, 0o022, 0o027, 0o077):
            with self.subTest(umask=oct(test_umask)):
                saved_umask = os.umask(test_umask)
                try:
                    with tempfile.TemporaryDirectory() as scratch:
                        home, source, binary = self._setup_runtime_scratch(scratch)
                        status = optional_setup.apply_runtime(home, source, binary)
                        self.assertEqual(status, "installed")

                        totpm = home / ".local/share/authy-local/optional/bin/totpm"
                        self.assertEqual(stat.S_IMODE(totpm.stat().st_mode), 0o700)

                        totpm_lic = home / ".local/share/authy-local/optional/bin/totpm-LICENSE"
                        self.assertEqual(stat.S_IMODE(totpm_lic.stat().st_mode), 0o600)

                        opt_dir = home / ".local/share/authy-local/optional"
                        self.assertEqual(stat.S_IMODE(opt_dir.stat().st_mode), 0o700)

                        state_file = home / ".local/state/authy-local/optional-runtime.json"
                        self.assertEqual(stat.S_IMODE(state_file.stat().st_mode), 0o600)
                finally:
                    os.umask(saved_umask)

    def test_optional_setup_rejects_group_or_world_writable_ancestors(self):
        """Ancestors inside home with group or world write bits must be strictly rejected."""
        with tempfile.TemporaryDirectory() as scratch:
            home, source, binary = self._setup_runtime_scratch(scratch)
            # Create shared parent directory with group-writable permissions (0775)
            shared = home / ".local/share/authy-local"
            shared.mkdir(parents=True, mode=0o775)
            shared.chmod(0o775)

            with self.assertRaises(ValueError) as ctx:
                optional_setup.apply_runtime(home, source, binary)
            self.assertIn("foreign ownership", str(ctx.exception))

            # Test world-writable permissions (0777)
            shared.chmod(0o777)
            with self.assertRaises(ValueError) as ctx:
                optional_setup.apply_runtime(home, source, binary)
            self.assertIn("foreign ownership", str(ctx.exception))

    def test_tui_profiles_save_and_load_under_extreme_umasks(self):
        """tui_profiles save and load must strictly enforce 0700 dir and 0600 file modes."""
        for test_umask in (0o000, 0o002, 0o022, 0o027, 0o077):
            with self.subTest(umask=oct(test_umask)):
                saved_umask = os.umask(test_umask)
                try:
                    with tempfile.TemporaryDirectory() as scratch:
                        home = Path(scratch)
                        tui_profiles.save(
                            {"pass-otp": {"store": "/valid/store", "key_home": "/valid/keys"}},
                            home=home,
                        )

                        profile_path = home / ".config/authy-local/tui-profiles.json"
                        self.assertTrue(profile_path.exists())
                        self.assertEqual(stat.S_IMODE(profile_path.stat().st_mode), 0o600)

                        authy_dir = home / ".config/authy-local"
                        self.assertEqual(stat.S_IMODE(authy_dir.stat().st_mode), 0o700)

                        loaded = tui_profiles.load(home=home)
                        self.assertIn("pass-otp", loaded)
                finally:
                    os.umask(saved_umask)


class TestTuiItemsUntestedBranches(unittest.TestCase):
    """Adversarial branch coverage and boundary probing for tui_items.py."""

    def test_fuzzy_filter_interface_contract_and_empty_queries(self):
        """fuzzy_filter must handle empty queries, whitespace, exact, prefix, and non-matches."""
        rows = [
            ("k1", "GitHub: personal"),
            ("k2", "Google Workspace: work"),
            ("k3", "AWS Production: infra"),
        ]
        # Empty and whitespace queries return entire catalog
        self.assertEqual(tui_items.fuzzy_filter(rows, ""), rows)
        self.assertEqual(tui_items.fuzzy_filter(rows, "   "), rows)

        # Exact match
        res_exact = tui_items.fuzzy_filter(rows, "github: personal")
        self.assertEqual(res_exact[0], ("k1", "GitHub: personal"))

        # Prefix match
        res_prefix = tui_items.fuzzy_filter(rows, "git")
        self.assertEqual(res_prefix[0], ("k1", "GitHub: personal"))

        # Substring match
        res_sub = tui_items.fuzzy_filter(rows, "workspace")
        self.assertEqual(res_sub[0], ("k2", "Google Workspace: work"))

        # Subsequence match
        res_subseq = tui_items.fuzzy_filter(rows, "awsinf")
        self.assertEqual(res_subseq[0], ("k3", "AWS Production: infra"))

        # Non-matching query
        self.assertEqual(tui_items.fuzzy_filter(rows, "nonexistentxyz"), [])

    def test_search_index_empty_and_exact_match(self):
        """SearchIndex must handle empty queries and exact match tier."""
        rows = [("k1", "Admin Dashboard"), ("k2", "Database Root")]
        idx = tui_items.SearchIndex(rows)

        self.assertEqual(idx.filter(""), rows)
        self.assertEqual(idx.filter("   "), rows)

        # Exact match tier
        exact = idx.filter("admin dashboard")
        self.assertEqual(exact[0], ("k1", "Admin Dashboard"))

    def test_subsequence_score_clamping(self):
        """_subsequence_score must clamp negative raw scores to minimum 1."""
        # Query with long span and long string that drives raw score negative
        score = tui_items._subsequence_score("az", "a" + "x" * 1000 + "z", 2, 1002)
        self.assertEqual(score, 1)

        # Subsequence not completed
        score_incomplete = tui_items._subsequence_score("abc", "ab", 3, 2)
        self.assertIsNone(score_incomplete)

    def test_local_scope_invalid_backend(self):
        """_local_scope must raise AppError(2) on unsupported backend."""
        with self.assertRaises(AppError) as ctx:
            tui_items._local_scope("unsupported", {})
        self.assertEqual(ctx.exception.exit_code, 2)

    def test_values_validation(self):
        """_values must raise AppError(2) on non-dict or missing/empty strings."""
        with self.assertRaises(AppError):
            tui_items._values("not a dict", ("store",))  # type: ignore

        with self.assertRaises(AppError):
            tui_items._values({"store": ""}, ("store",))

        with self.assertRaises(AppError):
            tui_items._values({"store": None}, ("store",))  # type: ignore

    def test_arguments_validation_branches(self):
        """arguments() must validate key type, backend, and totpm formatting."""
        with tempfile.TemporaryDirectory() as scratch:
            cfg = Path(scratch) / "totpm.conf"
            cfg.write_text("synthetic config")
            cfg.chmod(0o600)

            # Non-string key
            with self.assertRaises(AppError):
                tui_items.arguments("pass-otp", {"store": "/s", "key_home": "/k"}, 123)  # type: ignore

            # Invalid totpm key format (no colon or multiple colons)
            with self.assertRaises(AppError):
                tui_items.arguments("totpm", {"config": str(cfg)}, "no-colon")
            with self.assertRaises(AppError):
                tui_items.arguments("totpm", {"config": str(cfg)}, "too:many:colons")

            # Valid totpm key formatting
            args = tui_items.arguments("totpm", {"config": str(cfg)}, "svc:acct")
            self.assertIn("--service", args)
            self.assertIn("svc", args)
            self.assertIn("--account", args)
            self.assertIn("acct", args)

    def test_remove_unsupported_backend(self):
        """remove() must raise AppError(2) on onepassword or unknown backends."""
        with self.assertRaises(AppError):
            tui_items.remove("onepassword", {}, "key", {})
        with self.assertRaises(AppError):
            tui_items.remove("unknown", {}, "key", {})

    def test_records_invalid_tag(self):
        """records() must raise AppError(2) when tag in profile is invalid."""
        with self.assertRaises(AppError):
            tui_items.records(
                "onepassword",
                {
                    "account": "A" * 26,
                    "vault": "V" * 26,
                    "tag": "-invalid-tag-starts-with-hyphen",
                },
                {},
            )


class TestTuiProfilesUntestedBranches(unittest.TestCase):
    """Adversarial branch coverage and boundary probing for tui_profiles.py."""

    def test_valid_tag_adversarial_inputs(self):
        """valid_tag must reject non-strings, hyphens, commas, control chars, and > 64 chars."""
        self.assertFalse(tui_profiles.valid_tag(None))
        self.assertFalse(tui_profiles.valid_tag(12345))
        self.assertFalse(tui_profiles.valid_tag("-leading-hyphen"))
        self.assertFalse(tui_profiles.valid_tag("tag,with,comma"))
        self.assertFalse(tui_profiles.valid_tag("A" * 65))
        self.assertFalse(tui_profiles.valid_tag("tag\x00with\x00null"))
        self.assertFalse(tui_profiles.valid_tag("tag\nnewline"))
        self.assertTrue(tui_profiles.valid_tag("VALID_TAG_123"))
        self.assertTrue(tui_profiles.valid_tag(""))

    def test_validate_adversarial_profiles(self):
        """_validate must reject invalid backends, missing fields, or bad values."""
        # Backend not in allowlist
        with self.assertRaises(AppError):
            tui_profiles._validate({"unsupported": {}})

        # 1Password ID not 26 alphanumeric chars
        with self.assertRaises(AppError):
            tui_profiles._validate({"onepassword": {"account": "TOO_SHORT", "vault": "A" * 26}})

        # Path not absolute
        with self.assertRaises(AppError):
            tui_profiles._validate(
                {"pass-otp": {"store": "relative/path", "key_home": "/valid/keys"}}
            )

        # Path with traversal (..)
        with self.assertRaises(AppError):
            tui_profiles._validate(
                {"pass-otp": {"store": "/path/../traversal", "key_home": "/valid/keys"}}
            )

        # Path with control characters
        with self.assertRaises(AppError):
            tui_profiles._validate(
                {"pass-otp": {"store": "/path\x00null", "key_home": "/valid/keys"}}
            )

        # Path exceeding 1024 characters
        with self.assertRaises(AppError):
            tui_profiles._validate(
                {"pass-otp": {"store": "/" + "a" * 1025, "key_home": "/valid/keys"}}
            )

    def test_duplicate_json_keys_rejected(self):
        """_object must reject duplicate keys in profile JSON."""
        with self.assertRaises(AppError):
            tui_profiles._object([("key", "val1"), ("key", "val2")])

    def test_load_and_save_payload_limit(self):
        """load and save must reject files or documents exceeding _LIMIT (8192 bytes)."""
        oversized = {
            "pass-otp": {
                "store": "/store",
                "key_home": "/keys",
                "padding": "x" * 9000,
            }
        }
        with self.assertRaises(AppError):
            tui_profiles.save(oversized)


class TestTuiAppModalErrorBranches(unittest.IsolatedAsyncioTestCase):
    """Adversarial testing of TUI error paths and modal dialog protections."""

    async def test_scope_form_validation_failure_shows_banner_without_crash(self):
        """SavedScopeModal invalid input must display error banner and refuse dismissal."""
        app = AuthyApp(profiles={})
        async with app.run_test() as pilot:
            screen = SavedScopeModal(backend="onepassword")
            await app.push_screen(screen)
            await pilot.pause()

            # Set invalid 1Password account ID
            screen.query_one("#scope-op-account", Input).value = "short"
            screen.query_one("#scope-op-vault", Input).value = "V" * 26

            # Click save
            screen.query_one("#btn-save-scope", Button).press()
            await pilot.pause()

            # Verify error banner updated and modal remains displayed
            banner = screen.query_one("#scope-error-banner", Static)
            self.assertIn("Validation failed", str(banner.render()))
            self.assertIs(app.screen, screen)

    async def test_scope_form_save_callback_exception_shows_banner(self):
        """Exceptions in save_profiles callback must be caught and displayed in banner."""

        def faulty_save(prof):
            raise OSError("Synthetic disk failure")

        app = AuthyApp(profiles={}, save_profiles=faulty_save)
        async with app.run_test() as pilot:
            screen = SavedScopeModal(backend="onepassword")
            await app.push_screen(screen)
            await pilot.pause()

            screen.query_one("#scope-op-account", Input).value = "A" * 26
            screen.query_one("#scope-op-vault", Input).value = "V" * 26

            screen.query_one("#btn-save-scope", Button).press()
            await pilot.pause()

            banner = screen.query_one("#scope-error-banner", Static)
            self.assertIn("Synthetic disk failure", str(banner.render()))

    async def test_token_browser_delete_exception_shows_message_modal(self):
        """Exceptions during delete_record in TokenBrowserScreen must show Deletion Failed modal."""
        profile = {"store": "/store", "key_home": "/keys"}
        raw_items = [("item1", "Item One")]
        app = AuthyApp(profiles={"pass-otp": profile})
        app.delete_record = mock.Mock(side_effect=RuntimeError("Synthetic backend crash"))
        app.load_records = mock.Mock(return_value=raw_items)

        async with app.run_test() as pilot:
            browser = TokenBrowserScreen(backend="pass-otp", profile=profile, records=raw_items)
            await app.push_screen(browser)
            await pilot.pause()

            # Highlight item
            opt = browser.query_one(TokenOptionList)
            opt.highlighted = 0
            await pilot.pause()

            # Trigger delete confirmation
            browser.action_request_delete()
            await pilot.pause()

            # Authorize delete by typing DELETE
            confirm_input = app.screen.query_one("#delete-confirm-input", Input)
            confirm_input.value = "DELETE"
            await pilot.pause()

            # Press delete confirm button
            await pilot.click("#btn-confirm-delete")
            await pilot.pause()

            # MessageModal("Deletion Failed") should be pushed
            self.assertIsInstance(app.screen, MessageModal)
            self.assertEqual(app.screen.modal_title, "Deletion Failed")

            # Dismiss modal and verify item list is preserved
            await pilot.click("#btn-dismiss-message")
            await pilot.pause()
            self.assertEqual(len(browser.raw_records), 1)


if __name__ == "__main__":
    unittest.main()
