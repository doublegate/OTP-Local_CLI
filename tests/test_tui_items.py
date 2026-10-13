"""Synthetic scoped item browser; never read a live vault or TPM store."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from authy_local import interaction
from authy_local.errors import AppError


class ItemBrowserTests(unittest.TestCase):
    def test_metadata_browser_uses_only_scoped_login_listing_without_fzf(self):
        from authy_local import tui_items

        profile = {"account": "a" * 26, "vault": "v" * 26}
        payload = [{"id": "i" * 26, "title": "Synthetic\nLogin", "vault": {"id": "v" * 26}}]
        with (
            patch.object(interaction, "probe", return_value={"state": "available", "path": "/op"}),
            patch.object(
                interaction,
                "run",
                return_value=SimpleNamespace(returncode=0, stdout=json.dumps(payload).encode()),
            ) as runner,
            patch.object(interaction, "capability", side_effect=AssertionError("no fzf")),
        ):
            self.assertEqual(
                tui_items.records("onepassword", profile, {}),
                [("i" * 26, "Synthetic\\u000aLogin [iiiiiiii]")],
            )
        self.assertEqual(
            runner.call_args.args[0],
            [
                "/op",
                "item",
                "list",
                "--account",
                "a" * 26,
                "--vault",
                "v" * 26,
                "--categories",
                "Login",
                "--tags",
                "OTP",
                "--format",
                "json",
                "--no-color",
                "--cache=false",
                "--debug=false",
            ],
        )
        self.assertTrue(runner.call_args.kwargs["preserve_session"])
        self.assertEqual(
            tui_items.arguments("onepassword", profile, "i" * 26),
            ["i" * 26, "--account", "a" * 26, "--vault", "v" * 26],
        )
        for key in ("invalid", None):
            with self.assertRaises(AppError):
                tui_items.arguments("onepassword", profile, key)

    def test_listing_rejects_foreign_scope_and_malformed_metadata(self):
        from authy_local import tui_items

        profile = {"account": "a" * 26, "vault": "v" * 26}
        with (
            patch.object(interaction, "probe", return_value={"state": "available", "path": "/op"}),
            patch.object(interaction, "run") as runner,
        ):
            for payload in (
                b"{}",
                json.dumps([{"id": "i" * 26, "title": "x", "vault": {"id": "z" * 26}}]).encode(),
            ):
                runner.return_value = SimpleNamespace(returncode=0, stdout=payload)
                with self.assertRaises(AppError):
                    tui_items.records("onepassword", profile, {})

            runner.return_value = SimpleNamespace(returncode=1, stdout=b"")
            with self.assertRaises(AppError):
                tui_items.records("onepassword", profile, {})
        with patch.object(interaction, "run", side_effect=AssertionError("must not run")):
            for invalid in (
                {"account": "bad", "vault": "v" * 26},
                {"account": 42, "vault": "v" * 26},
            ):
                with self.assertRaises(AppError):
                    tui_items.records("onepassword", invalid, {})
            with self.assertRaises(AppError):
                tui_items.records("onepassword", profile, {"OP_SERVICE_ACCOUNT_TOKEN": "synthetic"})
        with patch.object(interaction, "probe", return_value={"state": "missing"}):
            with self.assertRaises(AppError):
                tui_items.records("onepassword", profile, {})

    def test_saved_tag_and_blank_tag_use_metadata_only_and_allow_empty_list(self):
        from authy_local import tui_items

        profile = {"account": "a" * 26, "vault": "v" * 26}
        with (
            patch.object(interaction, "probe", return_value={"state": "available", "path": "/op"}),
            patch.object(
                interaction, "run", return_value=SimpleNamespace(returncode=0, stdout=b"[]")
            ) as runner,
        ):
            for tag in ("Personal/OTP", ""):
                with self.subTest(tag=tag):
                    self.assertEqual(
                        tui_items.records("onepassword", {**profile, "tag": tag}, {}), []
                    )
                    command = runner.call_args.args[0]
                    if tag:
                        self.assertEqual(command[command.index("--tags") + 1], tag)
                    else:
                        self.assertNotIn("--tags", command)
                    self.assertNotIn("--otp", command)
            with self.assertRaises(AppError):
                interaction.list_items(profile["account"], profile["vault"], {})

    def test_invalid_saved_tag_is_rejected_before_native_listing(self):
        from authy_local import tui_items

        profile = {"account": "a" * 26, "vault": "v" * 26}
        with (
            patch.object(interaction, "probe", return_value={"state": "available", "path": "/op"}),
            patch.object(interaction, "run", side_effect=AssertionError("must not run")),
        ):
            for tag in (None, "OTP,Other", "-bad", "x" * 65, "OTP\x1b"):
                with self.subTest(tag=tag), self.assertRaises(AppError):
                    tui_items.records("onepassword", {**profile, "tag": tag}, {})

    def test_local_browser_lists_metadata_and_rejects_unsafe_selected_keys(self):
        from authy_local import tui_items

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store, keys = root / "store", root / "keys"
            store.mkdir(mode=0o700)
            keys.mkdir(mode=0o700)
            (store / ".gpg-id").touch(mode=0o600)
            (store / "acceptance-001.gpg").touch(mode=0o600)
            profile = {"store": str(store), "key_home": str(keys)}
            self.assertEqual(
                tui_items.records("pass-otp", profile, {}), [("acceptance-001", "acceptance-001")]
            )
            self.assertEqual(
                tui_items.arguments("pass-otp", profile, "acceptance-001"),
                [
                    "--backend",
                    "pass-otp",
                    "--store",
                    str(store),
                    "--key-home",
                    str(keys),
                    "--entry",
                    "acceptance-001",
                ],
            )
            with self.assertRaises(AppError):
                tui_items.arguments("pass-otp", profile, "../other")
            config = root / "totpm.conf"
            config.touch(mode=0o600)
            profile = {"config": str(config)}
            with (
                patch("authy_local.backends.local._totpm_ready", return_value="/totpm"),
                patch(
                    "authy_local.backends.local.run",
                    return_value=SimpleNamespace(returncode=0, stdout=b"synthetic (account)\n"),
                ) as runner,
            ):
                self.assertEqual(
                    tui_items.records("totpm", profile, {}),
                    [("synthetic:account", "synthetic (account)")],
                )
                self.assertEqual(
                    runner.call_args.args[0], ["/totpm", "--config", str(config), "list"]
                )
            self.assertEqual(
                tui_items.arguments("totpm", profile, "synthetic:account"),
                [
                    "--backend",
                    "totpm",
                    "--config",
                    str(config),
                    "--service",
                    "synthetic",
                    "--account",
                    "account",
                ],
            )
            for key in ("missing-colon", "x:y:z", "../x:y", "x:"):
                with self.assertRaises(AppError):
                    tui_items.arguments("totpm", profile, key)
        for backend in ("unknown", "onepassword", "pass-otp", "totpm"):
            with self.assertRaises(AppError):
                tui_items.arguments(backend, {}, "x")
        with self.assertRaises(AppError):
            tui_items.records("unknown", {}, {})
        with self.assertRaises(AppError):
            tui_items.arguments("onepassword", None, "i" * 26)

    def test_coarse_audit_failure_prevents_file_deletion(self):
        from authy_local import deletion_audit, tui_items

        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            store, keys = root / "store", root / "keys"
            store.mkdir(mode=0o700)
            keys.mkdir(mode=0o700)
            (store / ".gpg-id").touch(mode=0o600)
            entry = store / "test.gpg"
            entry.touch(mode=0o600)
            with patch.object(deletion_audit, "record", side_effect=AppError(3)):
                with self.assertRaises(AppError):
                    tui_items.remove(
                        "pass-otp",
                        {"store": str(store), "key_home": str(keys)},
                        "test",
                        {"HOME": name},
                    )
            self.assertTrue(entry.exists())
        with self.assertRaises(AppError):
            tui_items.remove("onepassword", {}, "a" * 26, {})

    def test_successful_deletion_audits_before_removing_exact_file(self):
        import json

        from authy_local import tui_items

        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            store, keys = root / "store", root / "keys"
            store.mkdir(mode=0o700)
            keys.mkdir(mode=0o700)
            (store / ".gpg-id").touch(mode=0o600)
            entry, neighbor = store / "test.gpg", store / "test-other.gpg"
            entry.touch(mode=0o600)
            neighbor.touch(mode=0o600)
            tui_items.remove(
                "pass-otp", {"store": str(store), "key_home": str(keys)}, "test", {"HOME": name}
            )
            self.assertFalse(entry.exists())
            self.assertTrue(neighbor.exists())
            row = json.loads((root / ".local/state/authy-local/deletions.jsonl").read_text())
            self.assertEqual(row["backend"], "pass-otp")
            self.assertNotIn("test", json.dumps(row))

    def test_remove_totpm_scope(self):
        from authy_local import tui_items

        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            config = root / "totpm.conf"
            config.touch(mode=0o600)
            profile = {"config": str(config)}
            with (
                patch("authy_local.backends.local.delete") as mock_delete,
                patch("authy_local.deletion_audit.record") as mock_audit,
            ):
                tui_items.remove("totpm", profile, "myservice:myaccount", {"HOME": name})
                self.assertEqual(mock_audit.call_count, 1)
                self.assertEqual(mock_delete.call_count, 1)
                scope = mock_delete.call_args.args[0]
                self.assertEqual(scope.service, "myservice")
                self.assertEqual(scope.account, "myaccount")

    def test_subsequence_score_mismatched_string(self):
        from authy_local.tui_items import _subsequence_score

        self.assertIsNone(_subsequence_score("xyz", "abc", 3, 3))
        self.assertIsNone(_subsequence_score("abc", "a", 3, 1))
        self.assertIsNone(_subsequence_score("query", "quex", 5, 4))
