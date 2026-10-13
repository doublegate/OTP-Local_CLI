"""Single-entry deletion boundaries using temporary synthetic stores only."""

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from authy_local.backends import local
from authy_local.errors import AppError


class LocalDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="authy-local-delete-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / "store"
        self.keys = self.root / "keys"
        self.store.mkdir(mode=0o700)
        self.keys.mkdir(mode=0o700)
        self.recipient = self.store / ".gpg-id"
        self.recipient.write_text("synthetic")
        self.recipient.chmod(0o600)
        self.target = self.store / "pilot.gpg"
        self.target.write_bytes(b"synthetic encrypted entry")
        self.target.chmod(0o600)
        self.scope = local.LocalScope(
            "pass-otp", store=str(self.store), key_home=str(self.keys), entry="pilot"
        )

    def test_deletes_only_exact_encrypted_entry_without_native_commands(self):
        other = self.store / "pilot2.gpg"
        other.write_bytes(b"other")
        with patch.object(local, "run") as run:
            local.delete(self.scope, {})
        run.assert_not_called()
        self.assertFalse(self.target.exists())
        self.assertTrue(other.exists())
        self.assertEqual(self.recipient.read_text(), "synthetic")
        self.assertTrue(self.keys.is_dir())

    def test_refuses_missing_entry_and_invalid_file_types(self):
        scope = local.LocalScope("pass-otp", store=str(self.store), key_home=str(self.keys))
        with self.assertRaises(AppError):
            local.delete(scope, {})
        for kind in ("symlink", "directory", "public", "hardlink"):
            with self.subTest(kind=kind):
                self.target.unlink(missing_ok=True)
                if kind == "symlink":
                    self.target.symlink_to(self.recipient)
                elif kind == "directory":
                    self.target.mkdir()
                elif kind == "hardlink":
                    os.link(self.recipient, self.target)
                else:
                    self.target.write_bytes(b"encrypted")
                    self.target.chmod(0o644)
                with self.assertRaises(AppError):
                    local.delete(self.scope, {})
                self.assertTrue(self.target.exists())
                if self.target.is_dir():
                    self.target.rmdir()

    def test_refuses_entry_replacement_before_unlink(self):
        real_stat = os.stat
        count = 0

        def replace(name, *args, **kwargs):
            nonlocal count
            if name == "pilot.gpg":
                count += 1
                if count == 2:
                    self.target.rename(self.store / "original.gpg")
                    self.target.write_bytes(b"replacement")
                    self.target.chmod(0o600)
            return real_stat(name, *args, **kwargs)

        with patch.object(local.os, "stat", side_effect=replace), self.assertRaises(AppError):
            local.delete(self.scope, {})
        self.assertEqual(self.target.read_bytes(), b"replacement")

    def test_refuses_store_symlink_replacement(self):
        moved = self.root / "moved"
        self.store.rename(moved)
        self.store.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(AppError):
            local.delete(self.scope, {})
        self.assertTrue((moved / "pilot.gpg").exists())

    def test_refuses_changed_store_permissions(self):
        self.store.chmod(0o755)
        with self.assertRaises(AppError):
            local.delete(self.scope, {})
        self.assertTrue(self.target.exists())


class TpmDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="authy-local-tpm-delete-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config"
        self.config.write_text(
            f'user_data_path = "{self.root}"\n'
            f'system_data_path = "{self.root}"\n'
            'tpm = "device:/synthetic"\npv_timeout = 10\npv_method = "none"\n'
        )
        self.config.chmod(0o600)
        self.db = self.root / "secrets.sqlite"
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute(
                "CREATE TABLE __version (id INTEGER PRIMARY KEY, version INTEGER NOT NULL, CHECK(id = 1))"
            )
            connection.execute("INSERT INTO __version VALUES (1, 1)")
            connection.execute(
                "CREATE TABLE secrets (id INTEGER PRIMARY KEY, service TEXT NOT NULL, account TEXT NOT NULL, digits INTEGER NOT NULL, interval INTEGER NOT NULL, public_data BLOB NOT NULL, private_data BLOB NOT NULL)"
            )
            connection.executemany(
                "INSERT INTO secrets VALUES (?, ?, ?, 6, 30, X'00', X'00')",
                [(1, "svc_1", "user"), (2, "svcX1", "user"), (3, "svc_1", "user2")],
            )
        self.db.chmod(0o600)
        self.scope = local.LocalScope(
            "totpm", config=str(self.config), service="svc_1", account="user"
        )

    def rows(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            return connection.execute("SELECT id FROM secrets ORDER BY id").fetchall()

    @patch.object(local, "_totpm_ready", return_value="/synthetic/totpm")
    def test_exact_transaction_preserves_substring_and_like_neighbors(self, ready):
        with patch.object(local, "run") as run:
            local.delete(self.scope, {})
        run.assert_not_called()
        self.assertEqual(self.rows(), [(2,), (3,)])
        self.assertTrue(self.config.exists())

    @patch.object(local, "_totpm_ready", return_value="/synthetic/totpm")
    def test_duplicate_missing_and_unknown_schema_roll_back(self, ready):
        for mutation in (
            "INSERT INTO secrets SELECT 4, service, account, digits, interval, public_data, private_data FROM secrets WHERE id=1",
            "DELETE FROM secrets WHERE id=1",
            "UPDATE __version SET version=2",
            "CREATE TRIGGER bad AFTER DELETE ON secrets BEGIN DELETE FROM secrets; END",
            "CREATE TRIGGER sqliteXbad AFTER DELETE ON secrets BEGIN DELETE FROM secrets; END",
        ):
            with self.subTest(mutation=mutation):
                with closing(sqlite3.connect(self.db)) as connection, connection:
                    connection.execute(mutation)
                before = self.rows()
                with self.assertRaises(AppError):
                    local.delete(self.scope, {})
                self.assertEqual(self.rows(), before)
                with closing(sqlite3.connect(self.db)) as connection, connection:
                    connection.execute("DROP TRIGGER IF EXISTS bad")
                    connection.execute("DROP TRIGGER IF EXISTS sqliteXbad")
                    connection.execute("UPDATE __version SET version=1")
                    connection.execute("DELETE FROM secrets WHERE id=4")
                    connection.execute(
                        "INSERT OR IGNORE INTO secrets VALUES (1, 'svc_1', 'user', 6, 30, X'00', X'00')"
                    )

    @patch.object(local, "_totpm_ready", return_value="/synthetic/totpm")
    def test_refuses_unsafe_database_and_config(self, ready):
        self.db.chmod(0o644)
        with self.assertRaises(AppError):
            local.delete(self.scope, {})
        self.db.chmod(0o600)
        os.link(self.db, self.root / "linked")
        with self.assertRaises(AppError):
            local.delete(self.scope, {})
        (self.root / "linked").unlink()
        self.config.write_text('user_data_path = "relative"\n')
        with self.assertRaises(AppError):
            local.delete(self.scope, {})

    @patch.object(local, "_totpm_ready", return_value="/synthetic/totpm")
    def test_writer_lock_prevents_mutation(self, ready):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            with self.assertRaises(AppError):
                local.delete(self.scope, {})
        self.assertEqual(self.rows(), [(1,), (2,), (3,)])

    @patch.object(local, "_totpm_ready", return_value="/synthetic/totpm")
    def test_missing_database_is_not_created_and_missing_selection_refused(self, ready):
        unselected = local.LocalScope("totpm", config=str(self.config))
        with self.assertRaises(AppError):
            local.delete(unselected, {})
        self.db.unlink()
        with self.assertRaises(AppError):
            local.delete(self.scope, {})
        self.assertFalse(self.db.exists())

    @patch.object(local, "_totpm_ready", return_value="/synthetic/totpm")
    def test_unsafe_sidecars_and_public_parent_are_refused(self, ready):
        for suffix in ("-journal", "-wal", "-shm"):
            sidecar = self.root / ("secrets.sqlite" + suffix)
            sidecar.symlink_to(self.config)
            with self.assertRaises(AppError):
                local.delete(self.scope, {})
            sidecar.unlink()
        self.root.chmod(0o755)
        with self.assertRaises(AppError):
            local.delete(self.scope, {})
        self.root.chmod(0o700)
        self.assertEqual(self.rows(), [(1,), (2,), (3,)])

    @patch.object(local, "_totpm_ready", return_value="/synthetic/totpm")
    def test_config_is_bounded_and_requires_selected_local_format(self, ready):
        original = self.config.read_text()
        for content in (
            "#" + "x" * 8192,
            "invalid[",
            original.replace('pv_method = "none"', 'pv_method = "fprintd"'),
            original.replace("pv_timeout = 10", "pv_timeout = true"),
            original.replace(str(self.root), "relative"),
            original + "unexpected = 1\n",
        ):
            with self.subTest(content=content[:30]):
                self.config.write_text(content)
                with self.assertRaises(AppError):
                    local.delete(self.scope, {})
                self.assertEqual(self.rows(), [(1,), (2,), (3,)])
