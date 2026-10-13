"""Preview-only optional setup contracts; no host keys or TPM operations."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from authy_local import optional_setup

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_optional.py"
SOURCE = Path(__file__).resolve().parents[1] / "src" / "authy_local" / "optional_setup.py"


class OptionalSetupTests(unittest.TestCase):
    def test_hardened_native_extension_never_places_seed_in_argv(self):
        from authy_local.optional_setup import hardened_extension

        upstream = (SOURCE.parents[2] / "tests/fixtures/pass-otp-upstream.bash").read_bytes()
        extension = hardened_extension(upstream)
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            executable = root / "otp.bash"
            executable.write_bytes(extension)
            token = root / "pilot.gpg"
            token.write_bytes(b"synthetic ciphertext sentinel")
            oathtool = root / "oathtool"
            oathtool.write_text(
                "#!/usr/bin/python3\nimport os,sys,json\n"
                'if sys.argv[1:] == ["--version"]:\n'
                ' print("oathtool (OATH Toolkit) " + os.environ["TEST_VERSION"])\n'
                "else:\n"
                ' open(os.environ["TEST_CAPTURE"],"w").write(json.dumps(sys.argv[1:]))\n'
                ' assert sys.stdin.read().strip() == "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"\n'
                ' print("123456")\n'
            )
            oathtool.chmod(0o700)
            gpg = root / "fake-gpg"
            gpg.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_URI"\n')
            gpg.chmod(0o700)
            harness = (
                'die() { printf "%s\\n" "$*" >&2; exit 1; }; '
                "check_sneaky_paths() { :; }; "
                "otp_insert() { echo unexpected-write >&2; exit 1; }; "
                'GPG="$TEST_GPG"; PREFIX="$TEST_ROOT"; GETOPT=/usr/bin/getopt; '
                'source "$TEST_EXTENSION" code pilot'
            )
            for version, kind in (
                ("2.6.14", "totp"),
                ("2.10.0", "totp"),
                ("2.6.14", "hotp"),
                ("2.6.4", "totp"),
            ):
                capture = root / (version + kind + ".json")
                env = {
                    "PATH": str(root) + ":/usr/bin:/bin",
                    "TEST_VERSION": version,
                    "TEST_CAPTURE": str(capture),
                    "TEST_GPG": str(gpg),
                    "TEST_ROOT": str(root),
                    "TEST_EXTENSION": str(executable),
                    "OATH_SAFE": "inherited-must-not-control-branch",
                    "TEST_URI": "otpauth://" + kind + "/pilot?secret="
                    "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&counter=0",
                }
                result = subprocess.run(
                    ["/bin/bash", "--noprofile", "--norc", "-c", harness],
                    env=env,
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
                if kind == "totp" and version != "2.6.4":
                    self.assertEqual(result.returncode, 0, result.stderr)
                    argv = json.loads(capture.read_text())
                    self.assertEqual(argv[-1], "-")
                    self.assertFalse(
                        any("GEZDGNBV" in value or "otpauth:" in value for value in argv)
                    )
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(capture.exists())
                    self.assertNotIn(b"unexpected-write", result.stderr)
                self.assertEqual(token.read_bytes(), b"synthetic ciphertext sentinel")

    def runtime_fixture(self, scratch):
        old_umask = os.umask(0o022)
        self.addCleanup(os.umask, old_umask)
        module = optional_setup
        home = Path(scratch) / "home"
        source = Path(scratch) / "source"
        source.mkdir()
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
            patcher = mock.patch.object(module, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        return module, home, source, binary

    def test_runtime_owned_apply_is_private_and_idempotent(self):
        with tempfile.TemporaryDirectory() as scratch:
            module, home, source, binary = self.runtime_fixture(scratch)
            self.assertEqual(module.apply_runtime(home, source, binary), "installed")
            target = home / ".local/share/authy-local/optional/bin/totpm"
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            license_path = target.parents[1] / "pass-store/.extensions/pass-otp-LICENSE"
            self.assertEqual(license_path.read_bytes(), b"synthetic license")
            self.assertEqual(license_path.stat().st_mode & 0o777, 0o600)
            native_license = target.parent / "totpm-LICENSE"
            self.assertEqual(native_license.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                hashlib.sha256(native_license.read_bytes()).hexdigest(),
                "94a10fc212f0c58a58cef3f8914cb43a20cce7c98a689016c94090bd39f5c55b",
            )
            self.assertEqual(module.apply_runtime(home, source, binary), "unchanged")
            manifest = home / ".local/state/authy-local/optional-runtime.json"
            self.assertEqual(manifest.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(manifest.read_text())["status"], "complete")
            target.write_bytes(b"operator modification")
            with self.assertRaises(ValueError):
                module.apply_runtime(home, source, binary)
            self.assertEqual(target.read_bytes(), b"operator modification")

    def test_shared_application_parent_allows_0755_without_chmod(self):
        with tempfile.TemporaryDirectory() as scratch:
            module, home, source, binary = self.runtime_fixture(scratch)
            shared = home / ".local/share/authy-local"
            shared.mkdir(parents=True, mode=0o755)
            self.assertEqual(module.apply_runtime(home, source, binary), "installed")
            self.assertEqual(shared.stat().st_mode & 0o777, 0o755)
            self.assertEqual((shared / "optional").stat().st_mode & 0o777, 0o700)

    def test_unsafe_shared_or_optional_parent_refuses_before_writes(self):
        with tempfile.TemporaryDirectory() as scratch:
            module, home, source, binary = self.runtime_fixture(scratch)
            shared = home / ".local/share/authy-local"
            shared.mkdir(parents=True, mode=0o775)
            shared.chmod(0o775)
            with self.assertRaises(ValueError):
                module.apply_runtime(home, source, binary)
            shared.chmod(0o755)
            optional = shared / "optional"
            optional.mkdir(mode=0o755)
            with self.assertRaises(ValueError):
                module.apply_runtime(home, source, binary)
            self.assertFalse((optional / "bin").exists())
            self.assertFalse((home / ".local/state/authy-local/optional-runtime.json").exists())

    def test_runtime_refuses_hash_collision_and_symlink(self):
        with tempfile.TemporaryDirectory() as scratch:
            module, home, source, binary = self.runtime_fixture(scratch)
            binary.write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                module.apply_runtime(home, source, binary)
            self.assertFalse(home.exists())
            binary.write_bytes(b"synthetic binary")
            target = home / ".local/share/authy-local/optional/bin/totpm"
            module._directory(target.parent, home, create=True)
            target.write_bytes(b"synthetic binary")
            with self.assertRaises(ValueError):
                module.apply_runtime(home, source, binary)
            target.unlink()
            target.symlink_to(binary)
            with self.assertRaises(ValueError):
                module.apply_runtime(home, source, binary)
            self.assertTrue(target.is_symlink())

    def test_pending_install_resumes_and_unsafe_directories_refuse(self):
        with tempfile.TemporaryDirectory() as scratch:
            module, home, source, binary = self.runtime_fixture(scratch)
            atomic = module._atomic
            calls = 0

            def interrupted(path, data, mode):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise OSError("synthetic interruption")
                atomic(path, data, mode)

            with mock.patch.object(module, "_atomic", side_effect=interrupted):
                with self.assertRaises(OSError):
                    module.apply_runtime(home, source, binary)
            manifest = home / ".local/state/authy-local/optional-runtime.json"
            self.assertEqual(json.loads(manifest.read_text())["status"], "pending")
            self.assertEqual(module.apply_runtime(home, source, binary), "installed")
            root = home / ".local/share/authy-local/optional"
            root.chmod(0o755)
            with self.assertRaises(ValueError):
                module.apply_runtime(home, source, binary)
            root.chmod(0o700)
            manifest.write_text("[]")
            with self.assertRaises(ValueError):
                module.apply_runtime(home, source, binary)

    def test_apply_cli_is_explicit_and_static_on_failure(self):
        with tempfile.TemporaryDirectory() as scratch:
            module, home, source, binary = self.runtime_fixture(scratch)
            with mock.patch("builtins.print") as output:
                self.assertEqual(
                    module.main(
                        [
                            "--home",
                            str(home),
                            "--apply-runtime",
                            "--pass-source",
                            str(source),
                            "--totpm-binary",
                            str(binary),
                        ]
                    ),
                    0,
                )
                self.assertIn("installed", output.call_args.args[0])
                binary.write_bytes(b"tampered")
                self.assertEqual(
                    module.main(
                        [
                            "--home",
                            str(home),
                            "--apply-runtime",
                            "--pass-source",
                            str(source),
                            "--totpm-binary",
                            str(binary),
                        ]
                    ),
                    1,
                )
                self.assertNotIn(str(binary), output.call_args.args[0])

    def test_preview_does_not_create_selected_home(self):
        with tempfile.TemporaryDirectory() as scratch:
            home = Path(scratch) / "not-created"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--home", str(home)],
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertFalse(home.exists())
            self.assertEqual(data["mode"], "preview-only")
            self.assertIn("--no-default-features", data["totpm"]["build_argv"])
            self.assertIn("--locked", data["totpm"]["build_argv"])
            self.assertEqual(data["totpm"]["build_argv"][-2:], ["--features", "install"])
            self.assertTrue(all(item["mode"] == "0700" for item in data["directories"]))

    def test_rejects_apply_and_relative_home(self):
        for arguments in (["--apply"], ["--home", "relative"], ["--home", "/"]):
            result = subprocess.run(
                [sys.executable, str(SCRIPT), *arguments], capture_output=True, check=False
            )
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(b"Traceback", result.stderr)

    def test_source_verification_is_exact_and_bounded(self):
        module = optional_setup
        with tempfile.TemporaryDirectory() as scratch:
            source = Path(scratch)
            (source / "otp.bash").write_bytes(b"incorrect source")
            self.assertFalse(module.verify_source("pass-otp", source))
            (source / "Cargo.lock").write_bytes(b"incorrect lock")
            self.assertFalse(module.verify_source("totpm", source))
            (source / "otp.bash").unlink()
            (source / "otp.bash").symlink_to(source / "Cargo.lock")
            self.assertFalse(module.verify_source("pass-otp", source))

    def test_manifest_direct_call(self):
        with tempfile.TemporaryDirectory() as scratch:
            data = optional_setup.manifest(Path(scratch))
            self.assertEqual(data["mode"], "preview-only")
            self.assertIn("pass_otp", data)
            self.assertIn("totpm", data)

    def test_hardened_extension_errors(self):
        with self.assertRaises(ValueError):
            optional_setup.hardened_extension(b"tampered")

    def test_read_bounds_and_directory_errors(self):
        with tempfile.TemporaryDirectory() as scratch:
            p = Path(scratch) / "testdir"
            p.mkdir()
            with self.assertRaises((ValueError, OSError)):
                optional_setup._read(p)
            big = Path(scratch) / "big.bin"
            big.write_bytes(b"x" * 100)
            with self.assertRaises(ValueError):
                optional_setup._read(big, limit=50)

    def test_main_cli_argument_combinations(self):
        with tempfile.TemporaryDirectory() as scratch:
            home = Path(scratch) / "home"
            home.mkdir()
            # 1. Traversal in home
            with self.assertRaises(SystemExit):
                optional_setup.main(["--home", f"{home}/../escaped"])
            # 2. verify_kind without source
            with self.assertRaises(SystemExit):
                optional_setup.main(["--home", str(home), "--verify-kind", "pass-otp"])
            # 3. source without verify_kind
            with self.assertRaises(SystemExit):
                optional_setup.main(["--home", str(home), "--source", str(home)])
            # 4. pass_source without apply_runtime
            with self.assertRaises(SystemExit):
                optional_setup.main(["--home", str(home), "--pass-source", str(home)])
            # 5. apply_runtime without pass_source or totpm_binary
            with self.assertRaises(SystemExit):
                optional_setup.main(["--home", str(home), "--apply-runtime"])
            # 6. verify_source reporting
            src = Path(scratch) / "src"
            src.mkdir()
            (src / "otp.bash").write_bytes(b"invalid")
            with mock.patch("builtins.print") as mock_print:
                code = optional_setup.main(
                    ["--home", str(home), "--verify-kind", "pass-otp", "--source", str(src)]
                )
                self.assertEqual(code, 1)
                self.assertIn("FAIL", mock_print.call_args.args[0])
            # 7. manifest dump
            with mock.patch("builtins.print") as mock_print:
                code = optional_setup.main(["--home", str(home)])
                self.assertEqual(code, 0)

    def test_apply_runtime_validation_branches(self):
        with tempfile.TemporaryDirectory() as scratch:
            module, home, source, binary = self.runtime_fixture(scratch)
            # 1. Invalid root home
            with self.assertRaises(ValueError):
                module.apply_runtime(Path("/"), source, binary)
            # 2. Path escapes home
            with self.assertRaises(ValueError):
                module._directory(Path("/etc/test"), home, create=False)
            # 3. Not directory
            home.mkdir(parents=True, exist_ok=True)
            f = home / "file.txt"
            f.write_text("content")
            with self.assertRaises(ValueError):
                module._directory(f, home, create=False)
            # 4. Manifest with unsafe mode
            state = home / ".local/state/authy-local/optional-runtime.json"
            module.apply_runtime(home, source, binary)
            state.chmod(0o666)
            with self.assertRaises(ValueError):
                module.apply_runtime(home, source, binary)
            # 5. Manifest with invalid json
            state.chmod(0o600)
            state.write_text("not json")
            with self.assertRaises(ValueError):
                module.apply_runtime(home, source, binary)
            # 6. Manifest with invalid status
            state.write_text(json.dumps({"version": 1, "status": "bad_status", "entries": {}}))
            with self.assertRaises(ValueError):
                module.apply_runtime(home, source, binary)


if __name__ == "__main__":
    unittest.main()
