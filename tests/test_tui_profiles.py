"""Private profile persistence uses synthetic homes, never the operator's profile."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from authy_local import tui_profiles
from authy_local.errors import AppError


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.home = Path(self.scratch.name)
        self.path = self.home / ".config/authy-local/tui-profiles.json"
        self.profiles = {
            "onepassword": {"account": "a" * 26, "vault": "b" * 26},
            "pass-otp": {"store": "/private/store", "key_home": "/private/keys"},
            "totpm": {"config": "/private/totpm.conf"},
        }

    def rejected(self, operation, code):
        with self.assertRaises(AppError) as raised:
            operation()
        self.assertEqual(raised.exception.exit_code, code)
        self.assertNotIn("private", str(raised.exception))

    def test_absent_is_empty_without_writes(self):
        self.assertEqual(tui_profiles.load(self.home), {})
        self.assertFalse(self.path.parent.exists())

    def test_roundtrip_private_permissions_and_replace(self):
        tui_profiles.save(self.profiles, self.home)
        self.assertEqual(tui_profiles.load(self.home), self.profiles)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)
        tui_profiles.save({}, self.home)
        self.assertEqual(tui_profiles.load(self.home), {})
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_optional_tag_roundtrips_without_changing_legacy_scope(self):
        for tag in ("OTP", "Personal/OTP", "", "x" * 64):
            with self.subTest(tag=tag):
                profiles = {"onepassword": {**self.profiles["onepassword"], "tag": tag}}
                tui_profiles.save(profiles, self.home)
                self.assertEqual(tui_profiles.load(self.home), profiles)

    def test_tag_rejects_multiple_tags_controls_and_option_like_values(self):
        for tag in (None, 42, "OTP,Other", "-OTP", "OTP\n", "é", "x" * 65):
            with self.subTest(tag=tag):
                profiles = {"onepassword": {**self.profiles["onepassword"], "tag": tag}}
                self.rejected(lambda profiles=profiles: tui_profiles.save(profiles, self.home), 2)

    def test_unsafe_existing_modes_are_preserved(self):
        tui_profiles.save(self.profiles, self.home)
        self.path.chmod(0o644)
        self.rejected(lambda: tui_profiles.load(self.home), 3)
        self.rejected(lambda: tui_profiles.save({}, self.home), 3)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o644)
        self.path.chmod(0o600)
        self.path.parent.chmod(0o755)
        self.rejected(lambda: tui_profiles.load(self.home), 3)

    def test_symlinks_rejected_at_file_and_ancestors(self):
        target = self.home / "target"
        target.mkdir(mode=0o700)
        (self.home / ".config").symlink_to(target, target_is_directory=True)
        self.rejected(lambda: tui_profiles.load(self.home), 3)
        self.rejected(lambda: tui_profiles.save({}, self.home), 3)
        (self.home / ".config").unlink()
        tui_profiles.save({}, self.home)
        self.path.unlink()
        self.path.symlink_to(target / "absent")
        self.rejected(lambda: tui_profiles.load(self.home), 3)
        self.rejected(lambda: tui_profiles.save({}, self.home), 3)

    def test_rejects_secrets_unknown_keys_and_incomplete_scopes(self):
        for value in (
            [],
            {"unknown": {}},
            {"onepassword": {"account": "a" * 26}},
            {"totpm": {"config": "/safe", "secret": "private"}},
            {"onepassword": {"account": "é" * 26, "vault": "a" * 26}},
            {"totpm": {"config": "relative"}},
            {"totpm": {"config": "/safe/../private"}},
            {"totpm": {"config": "/safe\nprivate"}},
            {"totpm": {"config": "/" + "x" * 1024}},
        ):
            with self.subTest(value=value):
                self.rejected(lambda value=value: tui_profiles.save(value, self.home), 2)
        self.assertFalse(self.path.exists())

    def test_rejects_malformed_duplicate_and_oversized_files(self):
        tui_profiles.save({}, self.home)
        for content in (
            b"{",
            b"\xff",
            b" " * 8193,
            b'{"totpm":{},"totpm":{}}',
            b'{"secret":"private"}',
        ):
            self.path.write_bytes(content)
            self.rejected(lambda: tui_profiles.load(self.home), 2)

    def test_existing_config_directory_can_be_public_readable(self):
        (self.home / ".config").mkdir(mode=0o755)
        tui_profiles.save(self.profiles, self.home)
        self.assertEqual(tui_profiles.load(self.home), self.profiles)

    def test_wrong_owner_rejected(self):
        tui_profiles.save({}, self.home)
        with mock.patch("authy_local.tui_profiles.os.getuid", return_value=os.getuid() + 1):
            self.rejected(lambda: tui_profiles.load(self.home), 3)

    def test_default_home_is_resolved_only_when_requested(self):
        with mock.patch("authy_local.tui_profiles.Path.home", return_value=self.home):
            tui_profiles.save(self.profiles)
            self.assertEqual(tui_profiles.load(), self.profiles)

    def test_failed_replace_preserves_existing_file_and_cleans_temp(self):
        tui_profiles.save(self.profiles, self.home)
        with mock.patch("authy_local.tui_profiles.os.replace", side_effect=OSError):
            self.rejected(lambda: tui_profiles.save({}, self.home), 3)
        self.assertEqual(json.loads(self.path.read_text()), self.profiles)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_rejects_nonregular_file_without_blocking(self):
        tui_profiles.save({}, self.home)
        self.path.unlink()
        os.mkfifo(self.path, mode=0o600)
        self.rejected(lambda: tui_profiles.load(self.home), 3)

    def test_group_writable_config_is_refused_without_modification(self):
        config = self.home / ".config"
        config.mkdir(mode=0o700)
        config.chmod(0o770)
        self.rejected(lambda: tui_profiles.save({}, self.home), 3)
        self.assertFalse(self.path.parent.exists())

    def test_load_handles_io_failure_with_static_error(self):
        tui_profiles.save({}, self.home)
        with mock.patch("authy_local.tui_profiles.os.open", side_effect=PermissionError):
            self.rejected(lambda: tui_profiles.load(self.home), 3)

    def test_home_argument_must_be_existing_absolute_directory(self):
        for home in (Path("relative"), self.home / "absent"):
            with self.subTest(home=home):
                self.rejected(lambda home=home: tui_profiles.save({}, home), 3)

    def test_cleanup_failure_has_static_error(self):
        tui_profiles.save({}, self.home)
        with (
            mock.patch("authy_local.tui_profiles.os.replace", side_effect=OSError),
            mock.patch("authy_local.tui_profiles.Path.unlink", side_effect=PermissionError),
        ):
            self.rejected(lambda: tui_profiles.save({}, self.home), 3)

    def test_validate_rejects_non_string_values(self):
        for invalid_scope in (
            {"account": 12345, "vault": "b" * 26},
            {"account": "a" * 26, "vault": None},
            {"account": "a" * 26, "vault": True},
        ):
            with self.subTest(invalid_scope=invalid_scope):
                self.rejected(
                    lambda invalid_scope=invalid_scope: tui_profiles.save(
                        {"onepassword": invalid_scope}, self.home
                    ),
                    2,
                )

    def test_load_rejects_file_descriptor_with_bad_mode(self):
        tui_profiles.save(self.profiles, self.home)
        original_fstat = os.fstat

        def bad_fstat(fd):
            st = original_fstat(fd)

            class FakeStat:
                st_mode = (st.st_mode & ~0o777) | 0o644
                st_uid = st.st_uid
                st_size = st.st_size

            return FakeStat()

        with mock.patch("authy_local.tui_profiles.os.fstat", side_effect=bad_fstat):
            self.rejected(lambda: tui_profiles.load(self.home), 3)

    def test_save_rejects_oversized_payload(self):
        huge_profile = {"onepassword": {"account": "a" * 26, "vault": "b" * 26, "tag": "x" * 64}}
        with mock.patch("authy_local.tui_profiles.json.dumps", return_value="x" * 65537):
            self.rejected(lambda: tui_profiles.save(huge_profile, self.home), 2)

    def test_invalid_saved_profile_reports_static_startup_error(self):
        import io

        from authy_local import cli

        output, diagnostic = io.StringIO(), io.StringIO()
        output.isatty = lambda: True
        with (
            mock.patch.object(cli, "has_terminal", return_value=True),
            mock.patch("authy_local.tui_profiles.load", side_effect=AppError(2)),
        ):
            self.assertEqual(cli.main(["tui"], stdout=output, stderr=diagnostic), 2)
        self.assertIn("Invalid command or scope", diagnostic.getvalue())
