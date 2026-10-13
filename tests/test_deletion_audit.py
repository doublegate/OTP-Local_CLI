"""Coarse audit records use synthetic private homes only."""

import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from authy_local import deletion_audit
from authy_local.errors import AppError


class DeletionAuditTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.home = Path(self.scratch.name)
        self.path = self.home / ".local/state/authy-local/deletions.jsonl"

    def rejected(self, operation, code=3):
        with self.assertRaises(AppError) as raised:
            operation()
        self.assertEqual(raised.exception.exit_code, code)
        self.assertNotIn(str(self.home), str(raised.exception))

    def test_append_only_coarse_records_and_private_permissions(self):
        deletion_audit.record("pass-otp", self.home)
        deletion_audit.record("totpm", self.home)
        values = [json.loads(line) for line in self.path.read_text().splitlines()]
        self.assertEqual([value["backend"] for value in values], ["pass-otp", "totpm"])
        for value in values:
            self.assertEqual(set(value), {"time", "uid", "action", "backend", "scope"})
            self.assertRegex(value["time"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
            self.assertEqual(value["uid"], os.getuid())
            self.assertEqual(value["action"], "delete-attempt")
            self.assertEqual(value["scope"], "one-confirmed-local-entry")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)

    def test_unknown_backend_does_not_create_state(self):
        for backend in ("onepassword", "secret", [], None):
            self.rejected(lambda backend=backend: deletion_audit.record(backend, self.home), 2)
        self.assertFalse((self.home / ".local").exists())

    def test_unsafe_modes_and_multiple_links_fail_closed(self):
        deletion_audit.record("totpm", self.home)
        original = self.path.read_bytes()
        self.path.chmod(0o644)
        self.rejected(lambda: deletion_audit.record("totpm", self.home))
        self.path.chmod(0o600)
        os.link(self.path, self.home / "other-link")
        self.rejected(lambda: deletion_audit.record("totpm", self.home))
        self.assertEqual(self.path.read_bytes(), original)

    def test_symlink_file_and_ancestor_are_refused(self):
        deletion_audit.record("totpm", self.home)
        self.path.unlink()
        self.path.symlink_to(self.home / "absent")
        self.rejected(lambda: deletion_audit.record("totpm", self.home))
        self.path.unlink()
        moved = self.home / "private-state"
        self.path.parent.rename(moved)
        self.path.parent.symlink_to(moved, target_is_directory=True)
        self.rejected(lambda: deletion_audit.record("totpm", self.home))

    def test_unsafe_directories_are_not_repaired(self):
        (self.home / ".local").mkdir(mode=0o700)
        (self.home / ".local").chmod(0o770)
        self.rejected(lambda: deletion_audit.record("totpm", self.home))
        self.assertFalse(self.path.parent.exists())
        (self.home / ".local").chmod(0o755)
        deletion_audit.record("totpm", self.home)
        self.path.parent.chmod(0o750)
        self.rejected(lambda: deletion_audit.record("totpm", self.home))

    def test_size_limit_prevents_any_append(self):
        deletion_audit.record("totpm", self.home)
        self.path.write_bytes(b" " * (1024 * 1024))
        self.rejected(lambda: deletion_audit.record("totpm", self.home))
        self.assertEqual(self.path.stat().st_size, 1024 * 1024)

    def test_wrong_owner_and_nonregular_file_are_refused(self):
        deletion_audit.record("totpm", self.home)
        with mock.patch("authy_local.deletion_audit.os.getuid", return_value=os.getuid() + 1):
            self.rejected(lambda: deletion_audit.record("totpm", self.home))
        self.path.unlink()
        os.mkfifo(self.path, mode=0o600)
        self.rejected(lambda: deletion_audit.record("totpm", self.home))

    def test_write_lock_and_fsync_failures_are_static(self):
        for target in ("os.write", "os.fsync", "fcntl.flock"):
            with mock.patch("authy_local.deletion_audit." + target, side_effect=OSError):
                self.rejected(lambda: deletion_audit.record("totpm", self.home))

    def test_concurrent_append_produces_complete_records(self):
        deletion_audit.record("totpm", self.home)
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda _: deletion_audit.record("totpm", self.home), range(20)))
        values = [json.loads(line) for line in self.path.read_text().splitlines()]
        self.assertEqual(len(values), 21)

    def test_default_home_and_invalid_home(self):
        with mock.patch("authy_local.deletion_audit.Path.home", return_value=self.home):
            deletion_audit.record("totpm")
        self.assertTrue(self.path.exists())
        for home in (Path("relative"), self.home / "absent"):
            self.rejected(lambda home=home: deletion_audit.record("totpm", home))

    def test_short_writes_finish_record_and_zero_write_fails_closed(self):
        write = os.write
        with mock.patch(
            "authy_local.deletion_audit.os.write",
            side_effect=lambda fd, data: write(fd, data[:3]),
        ):
            deletion_audit.record("totpm", self.home)
        self.assertEqual(json.loads(self.path.read_text())["backend"], "totpm")
        with mock.patch("authy_local.deletion_audit.os.write", return_value=0):
            self.rejected(lambda: deletion_audit.record("totpm", self.home))

    def test_size_is_rechecked_after_lock_acquisition(self):
        deletion_audit.record("totpm", self.home)

        def competing_append(_fd, _operation):
            self.path.write_bytes(b" " * (1024 * 1024))

        with mock.patch("authy_local.deletion_audit.fcntl.flock", side_effect=competing_append):
            self.rejected(lambda: deletion_audit.record("totpm", self.home))
        self.assertEqual(self.path.stat().st_size, 1024 * 1024)
