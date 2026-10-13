"""Unit tests for capability probe caching across backends."""

import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from authy_local.backends import (
    clear_capability_caches,
    clear_local_cache,
    clear_onepassword_cache,
    local,
    onepassword,
)
from authy_local.cache import clear_cache
from authy_local.errors import AppError
from authy_local.models import Scope
from authy_local.processes import Completed


class TestCapabilityCache(unittest.TestCase):
    def setUp(self):
        clear_capability_caches()
        clear_cache()

    def tearDown(self):
        clear_capability_caches()
        clear_cache()

    @patch("shutil.which", return_value="/usr/bin/op")
    @patch("authy_local.backends.onepassword.run")
    def test_onepassword_probe_cached(self, mock_run, mock_which):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout=b"2.39.0\n")
        env = {"PATH": "/usr/bin"}

        res1 = onepassword.probe(env)
        self.assertEqual(res1["state"], "available")
        self.assertEqual(mock_run.call_count, 1)

        # Second call should use cache
        res2 = onepassword.probe(env)
        self.assertEqual(res2["state"], "available")
        self.assertEqual(mock_run.call_count, 1)

    @patch("shutil.which", return_value="/usr/bin/op")
    @patch("authy_local.backends.onepassword.run")
    def test_onepassword_probe_ttl_expiration(self, mock_run, mock_which):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout=b"2.39.0\n")
        env = {"PATH": "/usr/bin"}

        with patch("time.monotonic", return_value=1000.0):
            res1 = onepassword.probe(env)
            self.assertEqual(res1["state"], "available")
            self.assertEqual(mock_run.call_count, 1)

        # Monotonic time advances past TTL (300s)
        with patch("time.monotonic", return_value=1301.0):
            res2 = onepassword.probe(env)
            self.assertEqual(res2["state"], "available")
            self.assertEqual(mock_run.call_count, 2)

    @patch("shutil.which", return_value="/usr/bin/op")
    @patch("authy_local.backends.onepassword.run")
    def test_onepassword_retrieve_clears_cache_on_error(self, mock_run, mock_which):
        # First call is probe: succeeds
        # Second call is item get: fails with returncode 1
        mock_run.side_effect = [
            SimpleNamespace(returncode=0, stdout=b"2.39.0\n"),
            SimpleNamespace(returncode=1, stdout=b""),
        ]
        env = {"PATH": "/usr/bin"}
        scope = Scope("i" * 26, "a" * 26, "v" * 26)

        with self.assertRaises(AppError):
            onepassword.retrieve(scope, env)

        # Cache should have been cleared on error; next probe must re-run
        mock_run.side_effect = [SimpleNamespace(returncode=0, stdout=b"2.39.0\n")]
        res = onepassword.probe(env)
        self.assertEqual(res["state"], "available")
        # 2 from retrieve + 1 from probe = 3 calls
        self.assertEqual(mock_run.call_count, 3)

    @patch("shutil.which", return_value="/usr/bin/op")
    @patch("authy_local.backends.onepassword.run")
    def test_doctor_bypass_cache(self, mock_run, mock_which):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout=b"2.39.0\n")
        env = {"PATH": "/usr/bin"}

        res1 = onepassword.probe(env)
        self.assertEqual(res1["state"], "available")
        self.assertEqual(mock_run.call_count, 1)

        # probe with use_cache=False must bypass cache
        res2 = onepassword.probe(env, use_cache=False)
        self.assertEqual(res2["state"], "available")
        self.assertEqual(mock_run.call_count, 2)

    def test_pass_ready_caching(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = root / "store"
            keys = root / "keys"
            store.mkdir(mode=0o700)
            keys.mkdir(mode=0o700)
            (store / ".gpg-id").write_text("recipient\n")
            (store / ".gpg-id").chmod(0o600)

            ext_dir = store / ".extensions"
            ext_dir.mkdir(mode=0o700)
            ext_file = ext_dir / "otp.bash"
            ext_file.write_bytes(b"synthetic")
            ext_file.chmod(0o700)

            scope = local.LocalScope("pass-otp", store=str(store), key_home=str(keys))
            env = {"PATH": "/bin"}

            with (
                patch.object(local, "_tool", side_effect=lambda name, env: f"/usr/bin/{name}"),
                patch("hashlib.sha256") as mock_hash,
                patch.object(local, "run") as mock_run,
            ):
                mock_hash.return_value.hexdigest.return_value = local.PASS_EXTENSION_SHA256
                mock_run.return_value = Completed(0, b"oathtool (GNU oath-toolkit) 2.6.7\n")

                p1 = local._pass_ready(scope, env)
                self.assertEqual(p1, "/usr/bin/pass")
                self.assertEqual(mock_run.call_count, 1)

                # Second call should hit capability cache and avoid running oathtool
                p2 = local._pass_ready(scope, env)
                self.assertEqual(p2, "/usr/bin/pass")
                self.assertEqual(mock_run.call_count, 1)

    def test_totpm_ready_caching(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Path(temp_dir) / "totpm.conf"
            config.write_text("dummy")
            config.chmod(0o600)
            scope = local.LocalScope("totpm", config=str(config))
            env = {"PATH": "/bin", "HOME": "/home/user"}

            with (
                patch.object(local, "_tool", return_value="/usr/bin/totpm"),
                patch.object(local, "run") as mock_run,
            ):
                mock_run.return_value = Completed(0, b"totpm 0.1.2\n")

                t1 = local._totpm_ready(scope, env)
                self.assertEqual(t1, "/usr/bin/totpm")
                self.assertEqual(mock_run.call_count, 1)

                # Second call should hit capability cache
                t2 = local._totpm_ready(scope, env)
                self.assertEqual(t2, "/usr/bin/totpm")
                self.assertEqual(mock_run.call_count, 1)

    def test_clear_capability_caches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Path(temp_dir) / "totpm.conf"
            config.write_text("dummy")
            config.chmod(0o600)
            scope = local.LocalScope("totpm", config=str(config))
            env = {"PATH": "/bin", "HOME": "/home/user"}

            with (
                patch("shutil.which", return_value="/usr/bin/op"),
                patch(
                    "authy_local.backends.onepassword.run",
                    return_value=SimpleNamespace(returncode=0, stdout=b"2.39.0\n"),
                ) as mock_op_run,
                patch.object(local, "_tool", return_value="/usr/bin/totpm"),
                patch.object(
                    local, "run", return_value=Completed(0, b"totpm 0.1.2\n")
                ) as mock_totpm_run,
            ):
                onepassword.probe(env)
                local._totpm_ready(scope, env)
                self.assertEqual(mock_op_run.call_count, 1)
                self.assertEqual(mock_totpm_run.call_count, 1)

                # Clear all capability caches
                clear_capability_caches()

                onepassword.probe(env)
                local._totpm_ready(scope, env)
                self.assertEqual(mock_op_run.call_count, 2)
                self.assertEqual(mock_totpm_run.call_count, 2)

                # Clear individually
                clear_onepassword_cache()
                onepassword.probe(env)
                self.assertEqual(mock_op_run.call_count, 3)

                clear_local_cache()
                local._totpm_ready(scope, env)
                self.assertEqual(mock_totpm_run.call_count, 3)

    def test_thread_safety(self):
        with (
            patch("shutil.which", return_value="/usr/bin/op"),
            patch(
                "authy_local.backends.onepassword.run",
                return_value=SimpleNamespace(returncode=0, stdout=b"2.39.0\n"),
            ),
        ):
            env = {"PATH": "/usr/bin"}
            errors = []

            def worker():
                try:
                    for _ in range(50):
                        res = onepassword.probe(env)
                        if res.get("state") != "available":
                            errors.append(f"Unexpected state: {res}")
                except Exception as e:
                    errors.append(str(e))

            threads = [threading.Thread(target=worker) for _ in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
