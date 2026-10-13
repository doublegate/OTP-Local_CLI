"""Synthetic boundary checks; never invoke an existing keyring or TPM."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from authy_local.backends import local
from authy_local.errors import AppError
from authy_local.processes import Completed


class LocalBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="authy-local-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / "store"
        self.keys = self.root / "keys"
        self.store.mkdir(mode=0o700)
        self.keys.mkdir(mode=0o700)
        (self.store / ".gpg-id").write_text("synthetic-recipient\n")
        (self.store / ".gpg-id").chmod(0o600)
        self.config = self.root / "config"
        self.config.write_text("synthetic config")
        self.config.chmod(0o600)
        self.env = {
            "PATH": "/synthetic",
            "PASSWORD_STORE_GPG_OPTS": "--leak",
            "BASH_ENV": "/unsafe",
            "OP_SESSION_x": "private",
        }

    def scope(self, backend="pass-otp", **kwargs):
        if backend == "pass-otp":
            return local.LocalScope(
                backend, store=str(self.store), key_home=str(self.keys), **kwargs
            )
        return local.LocalScope(backend, config=str(self.config), **kwargs)

    def test_scope_rejects_cross_backend_flags_and_unsafe_labels(self):
        for name in ("../entry", "-option", ".", "..", "name\n", "name:other"):
            with self.subTest(name=name), self.assertRaises(AppError):
                self.scope(entry=name)
        with self.assertRaises(AppError):
            self.scope(service="service")
        with self.assertRaises(AppError):
            self.scope("totpm", entry="entry")
        with self.assertRaises(AppError):
            self.scope("totpm", digits=7)
        self.assertNotIn(str(self.store), repr(self.scope()))

    def test_paths_reject_symlinks_public_permissions_and_relative_paths(self):
        linked = self.root / "linked"
        linked.symlink_to(self.store, target_is_directory=True)
        for candidate in (str(linked), "relative", str(self.root / ".." / "bad")):
            with self.assertRaises(AppError):
                local.LocalScope("pass-otp", store=candidate, key_home=str(self.keys))
        self.store.chmod(0o755)
        with self.assertRaises(AppError):
            self.scope()

    def test_pass_inventory_is_bounded_flat_and_refuses_unsafe_files(self):
        (self.store / "pilot.gpg").write_bytes(b"encrypted synthetic fixture")
        (self.store / "pilot.gpg").chmod(0o600)
        self.assertEqual(local.records(self.scope(), self.env), [("pilot", "pilot")])
        (self.store / "other.gpg").symlink_to(self.store / "pilot.gpg")
        with self.assertRaises(AppError):
            local.records(self.scope(), self.env)

    @patch.object(local, "_pass_ready", return_value="/tools/pass")
    @patch.object(local, "run", return_value=Completed(0, b"123456\n"))
    def test_pass_retrieval_sanitizes_environment_and_never_uses_native_clipboard(self, run, ready):
        (self.store / "pilot.gpg").write_bytes(b"encrypted")
        (self.store / "pilot.gpg").chmod(0o600)
        self.assertEqual(local.retrieve(self.scope(entry="pilot"), self.env), "123456")
        args, kw = run.call_args
        self.assertEqual(args[0], ["/tools/pass", "otp", "code", "pilot"])
        self.assertNotIn("BASH_ENV", kw["env"])
        self.assertNotIn("PASSWORD_STORE_GPG_OPTS", kw["env"])
        self.assertEqual(kw["env"]["GNUPGHOME"], str(self.keys))
        self.assertTrue(kw["preserve_session"])

    @patch.object(local, "_totpm_ready", return_value="/tools/totpm")
    @patch.object(local, "run")
    def test_totpm_exact_match_required_before_generation(self, run, ready):
        run.side_effect = [Completed(0, b"svc (user)\nsvc2 (user)\n")]
        with self.assertRaises(AppError):
            local.retrieve(self.scope("totpm", service="svc", account="user"), self.env)
        self.assertEqual(run.call_count, 1)
        run.reset_mock()
        run.side_effect = [Completed(0, b"svc (user)\n"), Completed(0, b"00123456\n")]
        self.assertEqual(
            local.retrieve(self.scope("totpm", service="svc", account="user"), self.env), "00123456"
        )
        self.assertEqual(run.call_args.args[0][-3:], ["gen", "svc", "user"])

    @patch.object(local, "_totpm_ready", return_value="/tools/totpm")
    @patch.object(local, "run")
    def test_totpm_inventory_rejects_duplicates_hostile_and_invalid_encoding(self, run, ready):
        for data in (b"svc (user)\nsvc (user)\n", b"bad\x1b (user)\n", b"\xff\n"):
            run.return_value = Completed(0, data)
            with self.assertRaises(AppError):
                local.records(self.scope("totpm"), self.env)
        run.return_value = Completed(0, b"svc (user)\n")
        self.assertEqual(local.records(self.scope("totpm"), self.env), [("svc:user", "svc (user)")])

    def test_enrollment_rejects_hotp_duplicate_params_and_invalid_secret(self):
        for secret in (
            "not a seed",
            "otpauth://hotp/x?secret=JBSWY3DPEHPK3PXP&counter=0",
            "otpauth://totp/x?secret=JBSWY3DPEHPK3PXP&secret=JBSWY3DPEHPK3PXP",
            "otpauth://totp/x?secret=JBSWY3DPEHPK3PXP&algorithm=MD5",
        ):
            with self.subTest(secret=secret), self.assertRaises(AppError):
                local.enroll(self.scope(entry="pilot"), self.env, secret)

    @patch.object(local, "_pass_ready", return_value="/tools/pass")
    @patch.object(local, "run", return_value=Completed(0, b""))
    def test_pass_enrollment_secret_only_on_stdin_and_refuses_overwrite(self, run, ready):
        uri = "otpauth://totp/pilot?secret=JBSWY3DPEHPK3PXP"
        local.enroll(self.scope(entry="pilot"), self.env, uri)
        self.assertEqual(run.call_args.args[0], ["/tools/pass", "otp", "insert", "pilot"])
        self.assertIn(b"secret=JBSWY3DPEHPK3PXP", run.call_args.kwargs["input_data"])
        self.assertNotIn(uri, repr(run.call_args.args[0]))
        (self.store / "pilot.gpg").write_bytes(b"encrypted")
        with self.assertRaises(AppError):
            local.enroll(self.scope(entry="pilot"), self.env, uri)

    @patch.object(local, "_totpm_ready", return_value="/tools/totpm")
    @patch.object(local, "run")
    def test_totpm_enrollment_requires_absent_match_and_stdin_secret(self, run, ready):
        run.side_effect = [Completed(0, b""), Completed(0, b"success\n")]
        local.enroll(
            self.scope("totpm", service="svc", account="user", digits=8, period=60),
            self.env,
            "JBSWY3DPEHPK3PXP",
        )
        self.assertEqual(
            run.call_args.args[0][-7:],
            ["svc", "user", "--digits", "8", "--interval", "60", "--secret-on-stdin"],
        )
        self.assertEqual(run.call_args.kwargs["input_data"], b"JBSWY3DPEHPK3PXP\n")
        run.side_effect = [Completed(0, b"svc (user)\n")]
        with self.assertRaises(AppError):
            local.enroll(
                self.scope("totpm", service="svc", account="user"), self.env, "JBSWY3DPEHPK3PXP"
            )

    def test_invalid_scope_variants_and_store_repository(self):
        for kwargs in ({"digits": True}, {"period": 0}, {"period": 86401}, {"period": "30"}):
            with self.assertRaises(AppError):
                self.scope(**kwargs)
        with self.assertRaises(AppError):
            local.LocalScope("unknown")
        with self.assertRaises(AppError):
            local.LocalScope("pass-otp", store=None)
        (self.store / ".git").mkdir()
        with self.assertRaises(AppError):
            self.scope()

    def test_path_types_and_owner_checked(self):
        with self.assertRaises(AppError):
            local.LocalScope("totpm", config=str(self.store))
        with self.assertRaises(AppError):
            local.LocalScope("totpm", config=str(self.root / "missing"))
        with patch.object(local.os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaises(AppError):
                self.scope("totpm")
        with self.assertRaises(AppError):
            self.scope(entry=123)

    @patch.object(local.shutil, "which", return_value=None)
    def test_capability_presence_is_non_authenticating_and_missing_tool_refused(self, which):
        self.assertTrue(all(item["state"] == "missing" for item in local.capabilities({}).values()))
        with self.assertRaises(AppError) as caught:
            local._totpm_ready(self.scope("totpm"), {})
        self.assertEqual(caught.exception.exit_code, 3)

    @patch.object(local.shutil, "which", side_effect=lambda name, **kwargs: "/tools/" + name)
    @patch.object(local, "run")
    def test_pinned_pass_extension_and_safe_oath_version_required(self, run, which):
        extensions = self.store / ".extensions"
        extensions.mkdir(mode=0o700)
        extension = extensions / "otp.bash"
        extension.write_bytes(b"reviewed synthetic extension")
        extension.chmod(0o700)
        with self.assertRaises(AppError):
            local._pass_ready(self.scope(), self.env)
        from hashlib import sha256

        with patch.object(
            local, "PASS_EXTENSION_SHA256", sha256(extension.read_bytes()).hexdigest()
        ):
            for version in (
                b"oathtool (OATH Toolkit) 2.6.4\n",
                b"oathtool (OATH Toolkit) 2.10.0\n",
                b"wrong\n",
            ):
                run.return_value = Completed(0, version)
                with self.assertRaises(AppError):
                    local._pass_ready(self.scope(), self.env)
            run.return_value = Completed(0, b"oathtool (OATH Toolkit) 2.6.13\nCopyright notice\n")
            self.assertEqual(local._pass_ready(self.scope(), self.env), "/tools/pass")

    @patch.object(local.shutil, "which", return_value="/tools/totpm")
    @patch.object(local, "run")
    def test_totpm_version_rejects_drift_and_failures(self, run, which):
        for result in (Completed(1, b"totpm 0.1.2\n"), Completed(0, b"totpm 0.2.0\n")):
            run.return_value = result
            with self.assertRaises(AppError):
                local._totpm_ready(self.scope("totpm"), self.env)
        run.return_value = Completed(0, b"totpm 0.1.2\n")
        self.assertEqual(local._totpm_ready(self.scope("totpm"), self.env), "/tools/totpm")

    @patch.object(local, "_totpm_ready", return_value="/tools/totpm")
    @patch.object(local, "run")
    def test_failed_inventory_and_missing_generation_scope(self, run, ready):
        run.return_value = Completed(1, b"sensitive diagnostic")
        with self.assertRaises(AppError) as caught:
            local.records(self.scope("totpm"), self.env)
        self.assertEqual(caught.exception.exit_code, 4)
        run.return_value = Completed(0, b"svc (user)\n" * 5001)
        with self.assertRaises(AppError):
            local.records(self.scope("totpm"), self.env)
        for scope in (self.scope(), self.scope("totpm")):
            with self.assertRaises(AppError):
                local.retrieve(scope, self.env)

    @patch.object(local, "_pass_ready", return_value="/tools/pass")
    @patch.object(local, "run")
    def test_code_failures_and_success_noise_rejected(self, run, ready):
        entry = self.store / "pilot.gpg"
        entry.write_bytes(b"encrypted")
        entry.chmod(0o600)
        for result, code in ((Completed(1, b"private"), 4), (Completed(0, b"123456\nnoise\n"), 5)):
            run.return_value = result
            with self.assertRaises(AppError) as caught:
                local.retrieve(self.scope(entry="pilot"), self.env)
            self.assertEqual(caught.exception.exit_code, code)

    @patch.object(local, "_pass_ready", return_value="/tools/pass")
    @patch.object(local, "run", return_value=Completed(1, b"sensitive"))
    def test_enrollment_errors_are_static_and_secret_validation_strict(self, run, ready):
        uri = "otpauth://totp/pilot?secret=JBSWY3DPEHPK3PXP"
        with self.assertRaises(AppError) as caught:
            local.enroll(self.scope(entry="pilot"), self.env, uri)
        self.assertEqual(caught.exception.exit_code, 4)
        for suffix in (
            "&digits=7",
            "&period=0",
            "&period=99999",
            "&issuer=bad%0A",
            "&unknown=x",
            "#fragment",
        ):
            with self.assertRaises(AppError):
                local.enroll(self.scope(entry="pilot"), self.env, uri + suffix)
        for seed in ("A" * 17, "A" * 15 + "B", "a" * 16):
            with self.assertRaises(AppError):
                local.enroll(self.scope("totpm", service="svc", account="user"), self.env, seed)
        for scope in (self.scope(), self.scope("totpm")):
            with self.assertRaises(AppError):
                local.enroll(
                    scope, self.env, uri if scope.backend == "pass-otp" else "JBSWY3DPEHPK3PXP"
                )

    @patch.object(local, "_pass_ready", return_value="/tools/pass")
    @patch.object(local, "run", return_value=Completed(0, b""))
    def test_normal_provider_uri_uses_opaque_label_and_original_parameters(self, run, ready):
        local.enroll(
            self.scope(entry="pilot"),
            self.env,
            "otpauth://totp/Example%20Inc:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=Example%20Inc&digits=8&period=60&algorithm=SHA256",
        )
        data = run.call_args.kwargs["input_data"]
        self.assertTrue(data.startswith(b"otpauth://totp/pilot?"))
        self.assertIn(b"issuer=pilot", data)
        self.assertIn(b"digits=8", data)
        self.assertNotIn(b"example.com", data)

    @patch.object(local, "_pass_ready", return_value="/tools/pass")
    def test_preflight_requires_enrollment_fields_before_secret_input(self, ready):
        local.preflight(self.scope(), self.env)
        with self.assertRaises(AppError):
            local.preflight(self.scope(), self.env, enrollment=True)
        local.preflight(self.scope(entry="pilot"), self.env, enrollment=True)

    def test_totpm_owned_fallback_without_path_changes(self):
        binary = self.root / ".local/share/authy-local/optional/bin/totpm"
        binary.parent.mkdir(parents=True, mode=0o700)
        binary.parent.parent.chmod(0o700)
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o700)
        env = {"HOME": str(self.root), "PATH": ""}
        self.root.chmod(0o755)
        self.assertEqual(local._tool("totpm", env), str(binary))
        with patch.object(local, "run", side_effect=AssertionError("doctor must not execute")):
            self.assertEqual(local.capabilities(env)["totpm"]["state"], "available")

    def test_totpm_owned_fallback_refuses_insecure_missing_and_symlink(self):
        binary = self.root / ".local/share/authy-local/optional/bin/totpm"
        binary.parent.mkdir(parents=True, mode=0o700)
        binary.parent.parent.chmod(0o700)
        env = {"HOME": str(self.root), "PATH": ""}
        for mode in (0o600, 0o755):
            binary.write_text("synthetic binary")
            binary.chmod(mode)
            with self.assertRaises(AppError):
                local._tool("totpm", env)
            self.assertEqual(local.capabilities(env)["totpm"]["state"], "missing")
        binary.unlink()
        binary.symlink_to(self.config)
        with self.assertRaises(AppError):
            local._tool("totpm", env)
        for badenv in (
            {"PATH": ""},
            {"HOME": "relative", "PATH": ""},
            {"HOME": str(self.root / "absent"), "PATH": ""},
        ):
            with self.assertRaises(AppError):
                local._tool("totpm", badenv)
        self.root.chmod(0o777)
        with self.assertRaises(AppError):
            local._tool("totpm", env)


if __name__ == "__main__":
    unittest.main()
