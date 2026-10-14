"""Installer contracts using isolated homes and local wheel artifacts only."""

import contextlib
import copy
import fcntl
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


class InstallerTests(unittest.TestCase):
    def test_default_preview_creates_nothing(self):
        from authy_local.installer import operate

        with tempfile.TemporaryDirectory(
            prefix="installer-", dir="/tmp/Authy-to-1Password_Local"
        ) as tmp:
            home = Path(tmp) / "home"
            wheel = next(Path("dist").glob("*.whl"))
            plan = operate("install", home, wheel=wheel, environment={})
            self.assertFalse(home.exists())
            self.assertTrue(any("otp-local" in row for row in plan))

    def test_broken_symlink_refused_without_following(self):
        from authy_local.installer import InstallError, operate

        with tempfile.TemporaryDirectory(
            prefix="installer-", dir="/tmp/Authy-to-1Password_Local"
        ) as tmp:
            home = Path(tmp)
            (home / ".local").symlink_to(home / "missing")
            with self.assertRaises(InstallError):
                operate("install", home, wheel=next(Path("dist").glob("*.whl")), environment={})

    def test_install_repeat_rollback_uninstall_preserve_modified(self):
        from authy_local.installer import InstallError, operate

        with tempfile.TemporaryDirectory(
            prefix="installer-", dir="/tmp/Authy-to-1Password_Local"
        ) as tmp:
            home = Path(tmp)
            wheel = next(Path("dist").glob("*.whl"))
            operate("install", home, wheel=wheel, apply=True, environment={})
            launcher = home / ".local/bin/otp-local"
            original = launcher.read_bytes()
            operate("install", home, wheel=wheel, apply=True, environment={})
            self.assertEqual(launcher.read_bytes(), original)
            with self.assertRaises(InstallError):
                operate("rollback", home, apply=True, environment={})
            launcher.write_text("user edit")
            with self.assertRaises(InstallError):
                operate("install", home, wheel=wheel, apply=True, environment={})
            result = operate("uninstall", home, apply=True, environment={})
            self.assertIn("preserved modified", " ".join(result))
            self.assertEqual(launcher.read_text(), "user edit")
            launcher.write_bytes(original)
            launcher.chmod(0o755)
            with self.assertRaises(InstallError):
                operate("install", home, wheel=wheel, apply=True, environment={})
            operate("uninstall", home, apply=True, environment={})
            self.assertFalse(launcher.exists())

    def test_unowned_release_preview_refused(self):
        from authy_local.installer import InstallError, _wheel, operate

        with tempfile.TemporaryDirectory(
            prefix="installer-", dir="/tmp/Authy-to-1Password_Local"
        ) as tmp:
            home = Path(tmp)
            wheel = next(Path("dist").glob("*.whl"))
            _, digest = _wheel(wheel)
            (home / ".local/share/authy-local/releases" / digest).mkdir(parents=True)
            with self.assertRaises(InstallError):
                operate("install", home, wheel=wheel, environment={})

    def test_invalid_paths_options_and_lock(self):
        from authy_local.installer import InstallError, operate

        with tempfile.TemporaryDirectory(
            prefix="installer-", dir="/tmp/Authy-to-1Password_Local"
        ) as tmp:
            home = Path(tmp)
            wheel = next(Path("dist").glob("*.whl"))
            for action, options in (
                ("unknown", {}),
                ("uninstall", {"alias": True}),
                ("install", {"wheel": wheel, "environment": {"XDG_CONFIG_HOME": "relative"}}),
                ("install", {"wheel": wheel, "backup": [str(home / "unrelated")]}),
                (
                    "install",
                    {"wheel": wheel, "backup": [str(home / ".config/fish/functions/otp.fish")]},
                ),
            ):
                with self.subTest(action=action, options=options), self.assertRaises(InstallError):
                    operate(action, home, **dict({"environment": {}}, **options))
            state = home / ".local/state/authy-local"
            state.mkdir(parents=True, mode=0o700)
            with (state / "lock").open("w") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                with self.assertRaises(InstallError):
                    operate("install", home, wheel=wheel, apply=True, environment={})
            state.chmod(0o755)
            with self.assertRaises(InstallError):
                operate("install", home, wheel=wheel, apply=True, environment={})

    def test_actual_journal_recovery_and_conflict(self):
        from authy_local.installer import InstallError, _json_write, _snapshot, operate

        with tempfile.TemporaryDirectory(
            prefix="installer-", dir="/tmp/Authy-to-1Password_Local"
        ) as tmp:
            home = Path(tmp)
            state = home / ".local/state/authy-local"
            state.mkdir(parents=True, mode=0o700)
            target = home / ".local/bin/otp-local"
            target.parent.mkdir(parents=True)
            target.write_text("intended")
            intended = _snapshot(target)
            journal = {
                "schema": 1,
                "changes": {str(target): {"before": None, "after": intended}},
                "manifest": None,
                "previous": None,
            }
            _json_write(state / "journal.json", journal)
            with self.assertRaises(InstallError):
                operate("uninstall", home, environment={})
            target.write_text("concurrent edit")
            with self.assertRaises(InstallError):
                operate("uninstall", home, apply=True, environment={})
            self.assertEqual(target.read_text(), "concurrent edit")
            target.write_text("intended")
            self.assertEqual(
                operate("uninstall", home, apply=True, environment={}), ["nothing installed"]
            )
            self.assertFalse(target.exists())

    def test_cli_preview_and_static_error(self):
        from authy_local.installer import main

        with tempfile.TemporaryDirectory(
            prefix="installer-", dir="/tmp/Authy-to-1Password_Local"
        ) as tmp:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["uninstall", "--home", tmp]), 0)
            self.assertIn("PREVIEW", output.getvalue())
            with contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertEqual(main(["install", "--home", tmp]), 3)
            self.assertNotIn(tmp, output.getvalue())

    def test_invalid_artifacts_and_state(self):
        from authy_local.installer import InstallError, operate

        with tempfile.TemporaryDirectory(
            prefix="installer-", dir="/tmp/Authy-to-1Password_Local"
        ) as tmp:
            root = Path(tmp)
            artifact = root / "authy_local-0.0.0-py3-none-any.whl"
            for content in (b"not zip", b"PK\x03\x04"):
                artifact.write_bytes(content)
                with self.assertRaises(InstallError):
                    operate("install", root / "home", wheel=artifact, environment={})
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("../escape", "bad")
            with self.assertRaises(InstallError):
                operate("install", root / "home", wheel=artifact, environment={})
            state = root / "home/.local/state/authy-local"
            state.mkdir(mode=0o700, parents=True)
            for value in ("not json", json.dumps({"schema": 1, "changes": {"/escape": {}}})):
                (state / "journal.json").write_text(value)
                with self.assertRaises(InstallError):
                    operate("uninstall", root / "home", apply=True, environment={})

    def test_collision_backup_and_restore(self):
        from authy_local.installer import InstallError, operate

        with tempfile.TemporaryDirectory(
            prefix="installer-", dir="/tmp/Authy-to-1Password_Local"
        ) as tmp:
            home = Path(tmp)
            target = home / ".config/fish/functions/otp1p.fish"
            target.parent.mkdir(parents=True)
            target.write_text("existing function")
            wheel = next(Path("dist").glob("*.whl"))
            with self.assertRaises(InstallError):
                operate("install", home, wheel=wheel, environment={})
            operate("install", home, wheel=wheel, apply=True, backup=[str(target)], environment={})
            operate("uninstall", home, apply=True, environment={})
            self.assertEqual(target.read_text(), "existing function")

    def test_failure_restores_session_writes(self):
        from authy_local.installer import InstallError, operate

        with tempfile.TemporaryDirectory(
            prefix="installer-", dir="/tmp/Authy-to-1Password_Local"
        ) as tmp:
            home = Path(tmp)
            wheel = next(Path("dist").glob("*.whl"))
            with patch("authy_local.installer._activate", side_effect=InstallError("injected")):
                with self.assertRaises(InstallError):
                    operate("install", home, wheel=wheel, apply=True, environment={})
            self.assertFalse((home / ".config/fish/functions/otp1p.fish").exists())
            self.assertFalse((home / ".local/bin/otp-local").exists())

    def test_xdg_escape_and_tampered_manifest_refused(self):
        from authy_local.installer import InstallError, operate

        with tempfile.TemporaryDirectory(
            prefix="installer-", dir="/tmp/Authy-to-1Password_Local"
        ) as tmp:
            home = Path(tmp)
            wheel = next(Path("dist").glob("*.whl"))
            with self.assertRaises(InstallError):
                operate("install", home, wheel=wheel, environment={"XDG_CONFIG_HOME": "/elsewhere"})
            state = home / ".local/state/authy-local"
            state.mkdir(parents=True)
            (state / "manifest.json").write_text('{"schema": 999}')
            with self.assertRaises(InstallError):
                operate("uninstall", home, environment={})

    def test_upgrade_previous_release_and_retry_after_failure(self):
        from authy_local.installer import InstallError, operate

        with tempfile.TemporaryDirectory(
            prefix="installer-", dir="/tmp/Authy-to-1Password_Local"
        ) as tmp:
            home = Path(tmp) / "home"
            wheel = next(Path("dist").glob("*.whl"))
            newer = Path(tmp) / wheel.name
            newer.write_bytes(wheel.read_bytes())
            with zipfile.ZipFile(newer, "a") as archive:
                archive.comment = b"synthetic upgrade artifact"
            operate("install", home, wheel=wheel, apply=True, environment={})
            launcher = home / ".local/bin/otp-local"
            original = launcher.read_bytes()
            with patch("authy_local.installer._activate", side_effect=InstallError("injected")):
                with self.assertRaises(InstallError):
                    operate("install", home, wheel=newer, apply=True, environment={})
            self.assertEqual(launcher.read_bytes(), original)
            operate("install", home, wheel=newer, apply=True, environment={})
            self.assertNotEqual(launcher.read_bytes(), original)
            operate("rollback", home, apply=True, environment={})
            self.assertEqual(launcher.read_bytes(), original)

    def test_xdg_alias_and_manifest_boundary_mutations(self):
        from authy_local.installer import InstallError, operate

        with tempfile.TemporaryDirectory(
            prefix="installer-", dir="/tmp/Authy-to-1Password_Local"
        ) as tmp:
            home = Path(tmp)
            wheel = next(Path("dist").glob("*.whl"))
            environment = {
                f"XDG_{name}_HOME": str(home / name.lower()) for name in ("DATA", "STATE", "CONFIG")
            }
            operate("install", home, wheel=wheel, apply=True, alias=True, environment=environment)
            self.assertTrue((home / "config/fish/functions/otp.fish").is_file())
            self.assertEqual((home / "state/authy-local").stat().st_mode & 0o777, 0o700)
            with self.assertRaises(InstallError):
                operate("install", home, wheel=wheel, environment=environment)
            manifest = home / "state/authy-local/manifest.json"
            original = json.loads(manifest.read_bytes())
            values = []
            for key, value in (
                ("release", "invalid"),
                ("files", {}),
                ("tree", {}),
                ("tree", {"../escape": "0" * 64}),
                ("tree", {"bin/python": "bad"}),
            ):
                values.append(dict(original, **{key: value}))
            raw = next(iter(original["files"]))
            for entry in (
                {"installed": None, "original": None},
                {"installed": {"data": "!", "mode": 0o600, "hash": "bad"}, "original": None},
                {"installed": {"data": "", "mode": 0o600, "hash": "bad"}, "original": None},
                {},
            ):
                mutated = copy.deepcopy(original)
                mutated["files"][raw] = entry
                values.append(mutated)
            mutated = copy.deepcopy(original)
            mutated["files"][str(home / "unrelated")] = mutated["files"].pop(raw)
            values.append(mutated)
            for value in values:
                manifest.write_text(json.dumps(value))
                with self.subTest(value=value), self.assertRaises(InstallError):
                    operate("uninstall", home, environment=environment)
            manifest.write_text(json.dumps(original))
            release = home / "data/authy-local/releases" / original["release"]
            (release / "unowned").write_text("changed")
            with self.assertRaises(InstallError):
                operate("uninstall", home, environment=environment)
            (release / "unowned").unlink()
            (release / "unexpected-link").symlink_to(home)
            with self.assertRaises(InstallError):
                operate("uninstall", home, environment=environment)
            (release / "unexpected-link").unlink()
            operate("uninstall", home, apply=True, environment=environment)
            self.assertFalse((home / "config/fish/functions/otp.fish").exists())

    def test_invalid_wheel_metadata_and_named_target_shapes(self):
        from authy_local.installer import InstallError, operate

        with tempfile.TemporaryDirectory(
            prefix="installer-", dir="/tmp/Authy-to-1Password_Local"
        ) as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            artifact = Path(tmp) / "authy_local-0.0.0-py3-none-any.whl"
            for metadata in (
                None,
                "Name: other\n",
                "\nName: authy-local\nRequires-Dist: external\n",
                "Metadata-Version: 2.4\nName: authy-local\nrequires-dist: external\n",
                "Metadata-Version: 2.4\nName: other\nName: authy-local\n",
            ):
                with zipfile.ZipFile(artifact, "w") as archive:
                    archive.writestr("authy_local/__init__.py", "")
                    if metadata is not None:
                        archive.writestr("authy_local-0.0.0.dist-info/METADATA", metadata)
                with self.assertRaises(InstallError):
                    operate("install", home, wheel=artifact, environment={})
            with zipfile.ZipFile(artifact, "w") as archive:
                entry = zipfile.ZipInfo("link")
                entry.external_attr = 0o120777 << 16
                archive.writestr(entry, "outside")
            with self.assertRaises(InstallError):
                operate("install", home, wheel=artifact, environment={})
            for wheel in (home / "absent.whl", artifact.with_suffix(".txt")):
                wheel.write_bytes(b"invalid")
                with self.assertRaises(InstallError):
                    operate("install", home, wheel=wheel, environment={})
            real = next(Path("dist").glob("*.whl"))
            (home / ".local").write_text("not a directory")
            with self.assertRaises(InstallError):
                operate("install", home, wheel=real, environment={})
            (home / ".local").unlink()
            (home / ".local/bin/otp-local").mkdir(parents=True)
            with self.assertRaises(InstallError):
                operate("install", home, wheel=real, environment={})

    def test_wheel_v2_dependencies_accepted(self):
        from authy_local.installer import _wheel

        with tempfile.TemporaryDirectory(
            prefix="installer-", dir="/tmp/Authy-to-1Password_Local"
        ) as tmp:
            artifact = Path(tmp) / "authy_local-2.0.0-py3-none-any.whl"
            metadata = (
                "Metadata-Version: 2.4\n"
                "Name: authy-local\n"
                "Version: 2.0.0\n"
                "Requires-Python: >=3.14,<3.15\n"
                "Requires-Dist: textual>=0.80.0\n"
                "Requires-Dist: fido2>=2.0.0\n"
                "Requires-Dist: pluggy>=1.0.0\n"
            )
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("authy_local/__init__.py", "__version__ = '2.0.0'\n")
                archive.writestr("authy_local-2.0.0.dist-info/METADATA", metadata)
            path, digest = _wheel(artifact)
            self.assertEqual(path, artifact)
            self.assertEqual(len(digest), 64)

    def test_onepassword_enroll_fallback_malformed_json(self):
        from unittest.mock import MagicMock, patch

        from authy_local.backends import onepassword

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"invalid json"
        with patch(
            "authy_local.backends.onepassword.probe",
            return_value={"state": "available", "path": "/usr/bin/op"},
        ):
            with patch("authy_local.backends.onepassword.run", return_value=mock_result):
                res = onepassword.enroll(
                    "a" * 26, "a" * 26, "title", "otpauth://totp/x", {"PATH": "/bin"}
                )
                self.assertEqual(res, "title")

    def test_concurrent_target_edit_is_preserved_during_activation(self):
        from authy_local import installer

        with tempfile.TemporaryDirectory(
            prefix="installer-", dir="/tmp/Authy-to-1Password_Local"
        ) as tmp:
            home = Path(tmp)
            wheel = next(Path("dist").glob("*.whl"))
            first = home / ".config/fish/functions/otp1p.fish"
            following = home / ".config/fish/functions/otp1pc.fish"
            original_put = installer._put

            def concurrent_edit(path, snapshot):
                original_put(path, snapshot)
                if path == first and snapshot is not None:
                    following.write_text("operator concurrent change")

            with patch("authy_local.installer._put", side_effect=concurrent_edit):
                with self.assertRaises(installer.InstallError):
                    installer.operate("install", home, wheel=wheel, apply=True, environment={})
            self.assertEqual(following.read_text(), "operator concurrent change")
            self.assertFalse(first.exists())
            self.assertFalse((home / ".local/bin/otp-local").exists())
