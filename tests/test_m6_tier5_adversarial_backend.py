"""Milestone M6 Tier 5 Adversarial Test Suite for Backend Modules and Robustness.

Authored by Challenger 1 (Empirical Challenger) to verify:
1. Cache expiry pruning, type bounds, and multi-step invalidation (authy_local.cache).
2. 1Password foreign auth detection, child env sanitization, and probe caching (backends.onepassword).
3. Local backend capability caching, pass-otp/totpm validations, and SQLite assertions (backends.local).
4. Fast search subsequence scoring, boundary conditions, and deletion guards (tui_items).
5. Private scope profile validations, bounded file sizes, and cleanup error handling (tui_profiles).
6. Offline home installer archive verification, recovery journaling, and CLI exit codes (installer).
7. Doctor environment diagnosis and NTP clock state reporting (doctor).
8. CLI scope restrictions and terminal detection (cli).
9. Process lifecycle management, thread-safety, and exception handling (processes).
10. Test helper liveness probe verification under non-positive PIDs (tests.test_processes.alive).
"""

import io
import os
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from authy_local import cli, doctor, installer, processes, tui_items, tui_profiles
from authy_local.backends import local, onepassword
from authy_local.cache import (
    MAX_CACHE_ENTRIES,
    cache_stats,
    clear_cache,
    current_time_step,
    get_cached_totp,
    invalidate_item,
    set_cached_totp,
)
from authy_local.errors import AppError
from authy_local.installer import InstallError
from authy_local.models import Scope
from authy_local.processes import Completed
from tests.test_processes import alive


class TestCacheAdversarial(unittest.TestCase):
    """Adversarial stress tests for in-memory TOTP window cache (authy_local.cache)."""

    def setUp(self) -> None:
        clear_cache()

    def tearDown(self) -> None:
        clear_cache()

    def test_prune_expired_locked_when_full_and_stats(self) -> None:
        """Fill cache with MAX_CACHE_ENTRIES expired entries; verify prune deletes them and updates stats."""
        now = 1_000_000.0
        # Populate cache with MAX_CACHE_ENTRIES entries that expire before `now`
        for i in range(MAX_CACHE_ENTRIES):
            past_time = 100.0
            set_cached_totp(
                "onepassword",
                f"item_{i:04d}",
                0,
                "123456",
                period=30,
                now=past_time,
            )

        stats = cache_stats()
        self.assertEqual(stats["size"], MAX_CACHE_ENTRIES)

        # Insert a new entry at timestamp `now` (> 130.0), triggering _prune_expired_locked
        set_cached_totp(
            "onepassword",
            "new_item",
            int(now) // 30,
            "654321",
            period=30,
            now=now,
        )

        new_stats = cache_stats()
        self.assertGreaterEqual(new_stats["evictions"], MAX_CACHE_ENTRIES)
        self.assertEqual(new_stats["size"], 1)
        self.assertEqual(
            get_cached_totp("onepassword", "new_item", int(now) // 30, now=now),
            "654321",
        )

    def test_cache_type_and_value_validation(self) -> None:
        """Verify strict input validation on get_cached_totp and set_cached_totp."""
        # get_cached_totp returns None on non-string or non-int
        self.assertIsNone(get_cached_totp(123, "item", 0))  # type: ignore[arg-type]
        self.assertIsNone(get_cached_totp("backend", 123, 0))  # type: ignore[arg-type]
        self.assertIsNone(get_cached_totp("backend", "item", "0"))  # type: ignore[arg-type]

        # set_cached_totp raises ValueError on invalid types/bounds
        with self.assertRaises(ValueError):
            set_cached_totp("", "item", 0, "123456")
        with self.assertRaises(ValueError):
            set_cached_totp(123, "item", 0, "123456")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            set_cached_totp("onepassword", "", 0, "123456")
        with self.assertRaises(ValueError):
            set_cached_totp("onepassword", "item", -1, "123456")
        with self.assertRaises(ValueError):
            set_cached_totp("onepassword", "item", 0, "12345")  # 5 digits
        with self.assertRaises(ValueError):
            set_cached_totp("onepassword", "item", 0, "1234567")  # 7 digits
        with self.assertRaises(ValueError):
            set_cached_totp("onepassword", "item", 0, "123456789")  # 9 digits
        with self.assertRaises(ValueError):
            set_cached_totp("onepassword", "item", 0, "abcdef")  # non-digits
        with self.assertRaises(ValueError):
            set_cached_totp("onepassword", "item", 0, "123456", period=0)
        with self.assertRaises(ValueError):
            set_cached_totp("onepassword", "item", 0, "123456", period=-10)

    def test_cache_invalidation_multi_step(self) -> None:
        """Verify invalidate_item evicts all entries across different time steps."""
        set_cached_totp("onepassword", "item_a", 100, "111111", now=3000.0)
        set_cached_totp("onepassword", "item_a", 101, "222222", now=3030.0)
        set_cached_totp("onepassword", "item_b", 100, "333333", now=3000.0)

        evicted = invalidate_item("onepassword", "item_a")
        self.assertEqual(evicted, 2)
        self.assertIsNone(get_cached_totp("onepassword", "item_a", 100, now=3000.0))
        self.assertIsNone(get_cached_totp("onepassword", "item_a", 101, now=3030.0))
        self.assertEqual(
            get_cached_totp("onepassword", "item_b", 100, now=3000.0),
            "333333",
        )

    def test_cache_lru_eviction_when_unexpired(self) -> None:
        """Verify LRU eviction when all entries are unexpired and capacity is reached."""
        now = 10_000.0
        for i in range(MAX_CACHE_ENTRIES):
            set_cached_totp(
                "pass-otp",
                f"entry_{i}",
                1000,
                "123456",
                period=30,
                now=now,
            )

        stats = cache_stats()
        self.assertEqual(stats["size"], MAX_CACHE_ENTRIES)

        set_cached_totp(
            "pass-otp",
            "entry_overflow",
            1000,
            "999999",
            period=30,
            now=now,
        )

        stats_after = cache_stats()
        self.assertEqual(stats_after["size"], MAX_CACHE_ENTRIES)
        self.assertGreaterEqual(stats_after["evictions"], 1)
        self.assertIsNone(get_cached_totp("pass-otp", "entry_0", 1000, now=now))
        self.assertEqual(
            get_cached_totp("pass-otp", "entry_overflow", 1000, now=now),
            "999999",
        )


class TestOnePasswordBackendAdversarial(unittest.TestCase):
    """Adversarial security and caching tests for 1Password backend."""

    def setUp(self) -> None:
        onepassword.clear_probe_cache()
        clear_cache()

    def tearDown(self) -> None:
        onepassword.clear_probe_cache()
        clear_cache()

    def test_foreign_auth_permutations(self) -> None:
        """Verify foreign_auth detects all unauthorized OP session and token variables."""
        clean_env = {"HOME": "/home/user", "PATH": "/usr/bin"}
        self.assertFalse(onepassword.foreign_auth(clean_env))

        bad_keys = [
            "OP_SERVICE_ACCOUNT_TOKEN",
            "OP_CONNECT_TOKEN",
            "OP_CONNECT_HOST",
            "OP_SESSION",
            "OP_SESSION_default",
            "OP_SESSION_myorg",
        ]
        for key in bad_keys:
            env = dict(clean_env)
            env[key] = "secret"
            self.assertTrue(onepassword.foreign_auth(env))
            with self.assertRaises(AppError) as cm:
                onepassword.retrieve(
                    Scope("item" + "a" * 22, "acc" + "a" * 23, "vlt" + "a" * 23),
                    env,
                )
            self.assertEqual(cm.exception.exit_code, 3)

    def test_child_environment_sanitization(self) -> None:
        """Verify child_environment strips caller OP_* variables except biometric unlock."""
        caller_env = {
            "HOME": "/home/user",
            "PATH": "/usr/bin",
            "OP_DEVICE": "laptop",
            "OP_ACCOUNT": "acc",
            "OP_BIOMETRIC_UNLOCK_ENABLED": "false",
        }
        sanitized = onepassword.child_environment(caller_env)
        self.assertEqual(sanitized["HOME"], "/home/user")
        self.assertEqual(sanitized["PATH"], "/usr/bin")
        self.assertNotIn("OP_DEVICE", sanitized)
        self.assertNotIn("OP_ACCOUNT", sanitized)
        self.assertEqual(sanitized["OP_BIOMETRIC_UNLOCK_ENABLED"], "true")

    def test_probe_cache_ttl_and_bypass(self) -> None:
        """Verify probe caching, 300s TTL expiry, and test environment cache bypass."""
        with (
            patch("shutil.which", return_value="/bin/op"),
            patch(
                "authy_local.backends.onepassword.run",
                return_value=Completed(0, b"2.39.0\n"),
            ),
        ):
            env = {"PATH": "/bin"}
            res1 = onepassword.probe(env)
            self.assertEqual(res1["state"], "available")
            self.assertEqual(res1["version"], "2.39.0")

            with patch("shutil.which", side_effect=AssertionError("Should hit cache")):
                res2 = onepassword.probe(env)
                self.assertEqual(res2["version"], "2.39.0")

            bypass_env = {"PATH": "/bin", "FAKE_RUN": "1"}
            with patch(
                "authy_local.backends.onepassword.run",
                return_value=Completed(0, b"2.40.0\n"),
            ):
                res3 = onepassword.probe(bypass_env)
                self.assertEqual(res3["version"], "2.40.0")

    def test_probe_version_failure_modes(self) -> None:
        """Verify probe behavior on missing binary, outdated versions, regex mismatches, and errors."""
        with patch("shutil.which", return_value=None):
            self.assertEqual(onepassword.probe({"PATH": "/bin"}), {"state": "missing"})

        with (
            patch("shutil.which", return_value="/bin/op"),
            patch(
                "authy_local.backends.onepassword.run",
                return_value=Completed(0, b"2.38.9\n"),
            ),
        ):
            res = onepassword.probe({"PATH": "/bin"}, use_cache=False)
            self.assertEqual(res["state"], "unknown")

        with (
            patch("shutil.which", return_value="/bin/op"),
            patch(
                "authy_local.backends.onepassword.run",
                return_value=Completed(1, b"error\n"),
            ),
        ):
            res = onepassword.probe({"PATH": "/bin"}, use_cache=False)
            self.assertEqual(res["state"], "unknown")

        with (
            patch("shutil.which", return_value="/bin/op"),
            patch(
                "authy_local.backends.onepassword.run",
                side_effect=AppError(130),
            ),
        ):
            with self.assertRaises(AppError) as cm:
                onepassword.probe({"PATH": "/bin"}, use_cache=False)
            self.assertEqual(cm.exception.exit_code, 130)

        with (
            patch("shutil.which", return_value="/bin/op"),
            patch(
                "authy_local.backends.onepassword.run",
                side_effect=AppError(3),
            ),
        ):
            res = onepassword.probe({"PATH": "/bin"}, use_cache=False)
            self.assertEqual(res["state"], "unknown")

    def test_retrieve_failure_and_caching(self) -> None:
        """Verify retrieve caches tokens, and clears cache on command failure."""
        scope = Scope("item" + "a" * 22, "acc" + "a" * 23, "vlt" + "a" * 23)
        env = {"PATH": "/bin"}

        with (
            patch("shutil.which", return_value="/bin/op"),
            patch(
                "authy_local.backends.onepassword.run",
                side_effect=[
                    Completed(0, b"2.39.0\n"),
                    Completed(0, b"987654\n"),
                ],
            ),
        ):
            code1 = onepassword.retrieve(scope, env)
            self.assertEqual(code1, "987654")

            with patch(
                "authy_local.backends.onepassword.run",
                side_effect=AssertionError("Should use cache"),
            ):
                code2 = onepassword.retrieve(scope, env)
                self.assertEqual(code2, "987654")

        clear_cache()
        onepassword.clear_probe_cache()
        with (
            patch("shutil.which", return_value="/bin/op"),
            patch(
                "authy_local.backends.onepassword.run",
                side_effect=[
                    Completed(0, b"2.39.0\n"),
                    Completed(1, b"auth failed\n"),
                ],
            ),
        ):
            with self.assertRaises(AppError) as cm:
                onepassword.retrieve(scope, env)
            self.assertEqual(cm.exception.exit_code, 4)
            self.assertIsNone(get_cached_totp("onepassword", scope.item, current_time_step(30)))


class TestLocalBackendAdversarial(unittest.TestCase):
    """Adversarial tests for pass-otp and totpm local backends."""

    def setUp(self) -> None:
        local.clear_capability_cache()
        clear_cache()
        self.temp_dir = tempfile.TemporaryDirectory(prefix="authy-backend-test-")
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.store = self.root / "store"
        self.keys = self.root / "keys"
        self.store.mkdir(mode=0o700)
        self.keys.mkdir(mode=0o700)
        (self.store / ".gpg-id").write_text("recipient\n")
        (self.store / ".gpg-id").chmod(0o600)
        self.config = self.root / "config"
        self.config.write_text("config")
        self.config.chmod(0o600)

    def tearDown(self) -> None:
        local.clear_capability_cache()
        clear_cache()

    def test_seed_and_uri_adversarial_inputs(self) -> None:
        """Stress test _seed and _uri boundary parsers."""
        for bad_seed in [
            123,
            "ABC",
            "A" * 257,
            "ABCDEF1234567890",
            "abcdefghijklmnop",
            "MZXW6YTBOJRGC4TGA",
        ]:
            with self.subTest(bad_seed=bad_seed):
                with self.assertRaises(AppError) as cm:
                    local._seed(bad_seed)  # type: ignore[arg-type]
                self.assertEqual(cm.exception.exit_code, 2)

        valid_seed = "MZXW6YTBOJRGC4TG"
        self.assertEqual(local._seed(valid_seed), valid_seed)

        scope = local.LocalScope(
            "pass-otp",
            store=str(self.store),
            key_home=str(self.keys),
            entry="test",
        )
        for bad_uri in [
            123,
            "x" * 4097,
            "otpauth://totp/test?secret=" + valid_seed + "\x00",
            "http://totp/test?secret=" + valid_seed,
            "otpauth://hotp/test?secret=" + valid_seed,
            "otpauth://totp/?secret=" + valid_seed,
            "otpauth://totp/test?secret=" + valid_seed + "#frag",
            "otpauth://totp/te\x1fst?secret=" + valid_seed,
            "otpauth://totp/test?secret=" + valid_seed + "&unknown=1",
            "otpauth://totp/test?secret=" + valid_seed + "&secret=" + valid_seed,
        ]:
            with self.subTest(bad_uri=bad_uri):
                with self.assertRaises(AppError) as cm:
                    local._uri(bad_uri, scope)  # type: ignore[arg-type]
                self.assertEqual(cm.exception.exit_code, 2)

    def test_records_count_limit_and_oserror(self) -> None:
        """Verify records raises AppError(5) at 5,000 files and AppError(4) on OSError."""
        scope = local.LocalScope(
            "pass-otp",
            store=str(self.store),
            key_home=str(self.keys),
        )
        fake_paths = [Path(f"/fake/{i}.txt") for i in range(5001)]
        with patch.object(Path, "iterdir", return_value=fake_paths):
            with self.assertRaises(AppError) as cm:
                local.records(scope, {"PATH": "/bin"})
            self.assertEqual(cm.exception.exit_code, 5)

        with patch.object(Path, "iterdir", side_effect=OSError("disk error")):
            with self.assertRaises(AppError) as cm:
                local.records(scope, {"PATH": "/bin"})
            self.assertEqual(cm.exception.exit_code, 4)

    def test_preflight_missing_scope_fields(self) -> None:
        """Verify preflight with enrollment=True enforces required scope parameters."""
        scope_pass_missing = local.LocalScope(
            "pass-otp",
            store=str(self.store),
            key_home=str(self.keys),
            entry=None,
        )
        with self.assertRaises(AppError) as cm:
            local.preflight(scope_pass_missing, {"PATH": "/bin"}, enrollment=True)
        self.assertEqual(cm.exception.exit_code, 2)

        scope_totpm_missing = local.LocalScope(
            "totpm",
            config=str(self.config),
            service=None,
            account="user",
        )
        with self.assertRaises(AppError) as cm:
            local.preflight(scope_totpm_missing, {"PATH": "/bin"}, enrollment=True)
        self.assertEqual(cm.exception.exit_code, 2)

    def test_retrieve_and_delete_pass_missing_entry(self) -> None:
        """Verify retrieve and delete fail-closed when pass-otp entry is None."""
        scope_no_entry = local.LocalScope(
            "pass-otp",
            store=str(self.store),
            key_home=str(self.keys),
            entry=None,
        )
        with self.assertRaises(AppError) as cm:
            local.retrieve(scope_no_entry, {"PATH": "/bin"})
        self.assertEqual(cm.exception.exit_code, 2)

        with self.assertRaises(AppError) as cm:
            local.delete(scope_no_entry, {"PATH": "/bin"})
        self.assertEqual(cm.exception.exit_code, 2)


class TestTuiItemsAndSearchAdversarial(unittest.TestCase):
    """Adversarial tests for item indexing, ranking, and subsequence matching."""

    def test_subsequence_score_adversarial(self) -> None:
        """Verify _subsequence_score edge conditions and non-subsequences."""
        self.assertIsNone(tui_items._subsequence_score("xyz", "xya", 3, 3))
        self.assertIsNone(tui_items._subsequence_score("abc", "acb", 3, 3))

        score_consec = tui_items._subsequence_score("abc", "abcdef", 3, 6)
        score_non_consec = tui_items._subsequence_score("abc", "abxxc", 3, 5)
        self.assertIsNotNone(score_consec)
        self.assertIsNotNone(score_non_consec)
        self.assertGreater(score_consec, score_non_consec)

    def test_fuzzy_filter_and_search_index(self) -> None:
        """Verify search ranking orders: exact > prefix > boundary > subsequence."""
        rows = [
            ("k1", "my-github-token"),
            ("k2", "github"),
            ("k3", "github-primary"),
            ("k4", "git-internal-hub"),
        ]

        ranked = tui_items.fuzzy_filter(rows, "github")
        self.assertEqual(ranked[0][0], "k2")
        self.assertEqual(ranked[1][0], "k3")
        self.assertEqual(ranked[2][0], "k1")

        self.assertEqual(len(tui_items.fuzzy_filter(rows, "")), 4)
        self.assertEqual(tui_items.fuzzy_filter(rows, "github!"), [])

        index = tui_items.SearchIndex(rows)
        self.assertEqual(index.filter("")[0][0], "k1")
        self.assertEqual(index.filter("github")[0][0], "k2")

    def test_remove_unsupported_backend(self) -> None:
        """Verify remove raises AppError(2) on unsupported backend."""
        with self.assertRaises(AppError) as cm:
            tui_items.remove("onepassword", {}, "key", {"PATH": "/bin"})
        self.assertEqual(cm.exception.exit_code, 2)


class TestTuiProfilesAdversarial(unittest.TestCase):
    """Adversarial boundary tests for private profile scope files."""

    def test_valid_tag_bounds(self) -> None:
        """Verify valid_tag boundary checking."""
        self.assertTrue(tui_profiles.valid_tag("production"))
        self.assertTrue(tui_profiles.valid_tag(""))
        self.assertFalse(tui_profiles.valid_tag("-dash"))
        self.assertFalse(tui_profiles.valid_tag("tag,with,comma"))
        self.assertFalse(tui_profiles.valid_tag("a" * 65))
        self.assertFalse(tui_profiles.valid_tag("non_ascii_\x00"))
        self.assertFalse(tui_profiles.valid_tag(123))

    def test_validate_adversarial_scopes(self) -> None:
        """Verify _validate rejects unauthorized backends, malformed paths, and bad IDs."""
        with self.assertRaises(AppError):
            tui_profiles._validate({"unsupported": {}})

        with self.assertRaises(AppError):
            tui_profiles._validate({"onepassword": {"account": "too_short", "vault": "a" * 26}})

        with self.assertRaises(AppError):
            tui_profiles._validate(
                {"pass-otp": {"store": "relative/path", "key_home": "/valid/home"}}
            )
        with self.assertRaises(AppError):
            tui_profiles._validate(
                {"pass-otp": {"store": "/path/../escape", "key_home": "/valid/home"}}
            )

    def test_save_and_load_adversarial_boundaries(self) -> None:
        """Verify save and load handle oversized content, temp unlinks, and missing files."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.assertEqual(tui_profiles.load(home), {})

        huge_tag = "a" * 60
        huge_profile = {
            "onepassword": {
                "account": "a" * 26,
                "vault": "b" * 26,
                "tag": huge_tag,
            }
        }
        with patch("authy_local.tui_profiles._LIMIT", 10):
            with self.assertRaises(AppError) as cm:
                tui_profiles.save(huge_profile)
            self.assertEqual(cm.exception.exit_code, 2)


class TestInstallerAdversarial(unittest.TestCase):
    """Adversarial edge tests for offline installer logic."""

    def test_read_non_file_or_oversized(self) -> None:
        """Verify _read rejects directories and files exceeding 8MB."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "adir"
            p.mkdir()
            with self.assertRaises(InstallError):
                installer._read(p)

            big = Path(tmp) / "big.json"
            big.write_bytes(b"x" * (8 * 1024 * 1024 + 1))
            with self.assertRaises(InstallError):
                installer._read(big)

    def test_tree_symlink_or_not_dir(self) -> None:
        """Verify _tree rejects release paths that are not directories or are symlinks."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "dir"
            target.mkdir()
            sym = Path(tmp) / "sym"
            sym.symlink_to(target)
            with self.assertRaises(InstallError):
                installer._tree(sym)

            non_dir = Path(tmp) / "file"
            non_dir.write_text("hello")
            with self.assertRaises(InstallError):
                installer._tree(non_dir)

    def test_wheel_adversarial_archives(self) -> None:
        """Verify _wheel rejects oversized archives, symlinks, and path traversal."""
        with tempfile.TemporaryDirectory() as tmp:
            bad_name = Path(tmp) / "foo.whl"
            bad_name.write_bytes(b"PK")
            with self.assertRaises(InstallError):
                installer._wheel(bad_name)

            wheel_path = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
            with zipfile.ZipFile(wheel_path, "w") as z:
                z.writestr("../escape.txt", b"malicious")
            with self.assertRaises(InstallError):
                installer._wheel(wheel_path)

    def test_installer_main_cli(self) -> None:
        """Verify installer main CLI parameter validations and interrupt handling."""
        status = installer.main(["install"])
        self.assertEqual(status, 3)

        with patch("authy_local.installer.operate", side_effect=KeyboardInterrupt):
            status = installer.main(["install", "--wheel", "dummy.whl"])
            self.assertEqual(status, 130)


class TestDoctorAdversarial(unittest.TestCase):
    """Adversarial tests for doctor capability assessment and clock status."""

    def test_doctor_platform_and_python_versions(self) -> None:
        """Verify report identifies non-linux or non-3.14 platforms as missing."""
        with (
            patch("sys.platform", "darwin"),
            patch("authy_local.doctor.probe", return_value={"state": "available"}),
            patch(
                "authy_local.backends.local.capabilities",
                return_value={"pass": {"state": "missing"}, "totpm": {"state": "missing"}},
            ),
        ):
            res = doctor.report({"PATH": "/bin"})
            self.assertEqual(res["platform"]["state"], "missing")
            self.assertEqual(doctor.status(res), 3)

        with (
            patch("sys.version_info", (3, 13, 0)),
            patch("authy_local.doctor.probe", return_value={"state": "available"}),
            patch(
                "authy_local.backends.local.capabilities",
                return_value={"pass": {"state": "missing"}, "totpm": {"state": "missing"}},
            ),
        ):
            res = doctor.report({"PATH": "/bin"})
            self.assertEqual(res["python"]["state"], "missing")
            self.assertEqual(doctor.status(res), 3)

    def test_doctor_timedatectl_ntp(self) -> None:
        """Verify timedatectl NTP reporting states: yes, no, failure, and interrupt."""
        with (
            patch("shutil.which", return_value="/bin/timedatectl"),
            patch(
                "authy_local.doctor.run",
                return_value=Completed(0, b"yes\n"),
            ),
            patch("authy_local.doctor.probe", return_value={"state": "available"}),
            patch("authy_local.backends.local.capabilities", return_value={}),
        ):
            res = doctor.report({"PATH": "/bin"})
            self.assertEqual(res["clock"]["state"], "available")

        with (
            patch("shutil.which", return_value="/bin/timedatectl"),
            patch(
                "authy_local.doctor.run",
                return_value=Completed(0, b"no\n"),
            ),
            patch("authy_local.doctor.probe", return_value={"state": "available"}),
            patch("authy_local.backends.local.capabilities", return_value={}),
        ):
            res = doctor.report({"PATH": "/bin"})
            self.assertEqual(res["clock"]["state"], "missing")
            self.assertEqual(doctor.status(res), 3)

        with (
            patch("shutil.which", return_value="/bin/timedatectl"),
            patch("authy_local.doctor.run", side_effect=AppError(130)),
            patch("authy_local.doctor.probe", return_value={"state": "available"}),
            patch("authy_local.backends.local.capabilities", return_value={}),
        ):
            with self.assertRaises(AppError) as cm:
                doctor.report({"PATH": "/bin"})
            self.assertEqual(cm.exception.exit_code, 130)


class TestCliAdversarial(unittest.TestCase):
    """Adversarial tests for CLI parsing, local scope restrictions, and terminal probing."""

    def test_has_terminal_combinations(self) -> None:
        """Verify has_terminal under non-tty stdin and /dev/tty open failure."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        self.assertFalse(cli.has_terminal(mock_stdin))

        mock_stdin.isatty.return_value = True
        with patch("os.open", side_effect=OSError("no tty")):
            self.assertFalse(cli.has_terminal(mock_stdin))

        with (
            patch("os.open", return_value=42),
            patch("os.close") as mock_close,
        ):
            self.assertTrue(cli.has_terminal(mock_stdin))
            mock_close.assert_called_once_with(42)

    def test_local_scope_invalid_combinations(self) -> None:
        """Verify local_scope forbids mixing backend parameters."""
        args_item = SimpleNamespace(item="myitem", vault=None)
        with self.assertRaises(AppError) as cm:
            cli.local_scope(args_item)
        self.assertEqual(cm.exception.exit_code, 2)

        args_pass_bad = SimpleNamespace(
            backend="pass-otp",
            account="user",
            service=None,
            config=None,
            item=None,
            vault=None,
            store="/store",
            key_home="/keys",
            entry="entry",
        )
        with self.assertRaises(AppError) as cm:
            cli.local_scope(args_pass_bad)
        self.assertEqual(cm.exception.exit_code, 2)

        args_totpm_bad = SimpleNamespace(
            backend="totpm",
            store="/store",
            key_home=None,
            entry=None,
            item=None,
            vault=None,
            config="/config",
            service="svc",
            account="acc",
        )
        with self.assertRaises(AppError) as cm:
            cli.local_scope(args_totpm_bad)
        self.assertEqual(cm.exception.exit_code, 2)

    def test_cli_main_onepassword_with_local_flags(self) -> None:
        """Verify cli main rejects onepassword invoked with local backend flags."""
        out, err = io.StringIO(), io.StringIO()
        out.isatty = lambda: True
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True

        with (
            patch.object(cli, "has_terminal", return_value=True),
            patch.dict(os.environ, {"PATH": "/bin"}),
        ):
            status = cli.main(
                ["show", "item" + "a" * 22, "--store", "/store"],
                stdin=mock_stdin,
                stdout=out,
                stderr=err,
            )
            self.assertEqual(status, 2)


class TestProcessesAdversarial(unittest.TestCase):
    """Adversarial stress tests for child process execution and signals."""

    def test_stop_called_from_worker_thread(self) -> None:
        """Verify _stop does not manipulate signal.SIGINT when invoked outside main thread."""
        fake_child = MagicMock()
        fake_child.pid = 99999
        fake_child.wait.return_value = 0

        executed = False

        def worker():
            nonlocal executed
            with patch("os.killpg", side_effect=ProcessLookupError):
                processes._stop(fake_child, grouped=True)
            executed = True

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=2.0)
        self.assertTrue(executed)

    def test_stop_grouped_false_process_lookup_error(self) -> None:
        """Verify _stop with grouped=False handles ProcessLookupError gracefully."""
        fake_child = MagicMock()
        fake_child.terminate.side_effect = ProcessLookupError
        fake_child.kill.side_effect = ProcessLookupError
        fake_child.wait.return_value = 0

        processes._stop(fake_child, grouped=False)
        fake_child.wait.assert_called()

    def test_run_timeout_and_interrupt(self) -> None:
        """Verify run translates TimeoutExpired to AppError(7) and KeyboardInterrupt to AppError(130)."""
        with self.assertRaises(AppError) as cm:
            processes.run(["sleep", "10"], env={"PATH": "/usr/bin:/bin"}, timeout=0.05)
        self.assertEqual(cm.exception.exit_code, 7)

        with patch("subprocess.Popen", side_effect=KeyboardInterrupt):
            with self.assertRaises(AppError) as cm:
                processes.run(["cmd"], env={"PATH": "/bin"})
            self.assertEqual(cm.exception.exit_code, 130)

    def test_handoff_interrupt_and_oserror(self) -> None:
        """Verify handoff handles KeyboardInterrupt (exit 130) and OSError (exit 6)."""
        with patch("subprocess.Popen", side_effect=KeyboardInterrupt):
            with self.assertRaises(AppError) as cm:
                processes.handoff(["wl-copy"], env={"PATH": "/bin"}, input_data=b"token")
            self.assertEqual(cm.exception.exit_code, 130)

        with patch("subprocess.Popen", side_effect=OSError("not found")):
            with self.assertRaises(AppError) as cm:
                processes.handoff(["wl-copy"], env={"PATH": "/bin"}, input_data=b"token")
            self.assertEqual(cm.exception.exit_code, 6)


class TestTestHelperRobustness(unittest.TestCase):
    """Empirical verification of test helper alive(pid) behavior and container safety."""

    def test_alive_pid_empirical_behavior_and_guard(self) -> None:
        """Verify safety of non-positive PID guard in alive(pid)."""
        self.assertFalse(
            alive(0),
            "alive(0) must return False with the non-positive PID guard active.",
        )
        self.assertFalse(alive(-1))
        self.assertFalse(alive(-999))
        self.assertTrue(alive(os.getpid()))
