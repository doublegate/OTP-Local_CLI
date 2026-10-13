"""Adversarial Unit Tests for Milestone M2 (Packaging & Allowlist Validation).

Authored by Challenger 2 (Empirical Challenger) to verify:
1. Rejection of forbidden dependencies in wheel Requires-Dist (evil-package, requests, etc.).
2. Rejection of forbidden extras, environment markers, and URL references (textual; extra == "dev", etc.).
3. Allowance of exact textual and version specifications.
4. Fail-closed behavior during offline staging when wheelhouse is missing or corrupted.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from authy_local.installer import InstallError, _wheel, operate


def _make_mock_wheel(wheel_path: Path, requires_dist: list[str]) -> None:
    wheel_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel_path, "w") as z:
        z.writestr("authy_local/__init__.py", "__version__ = '1.0.0'\n")
        metadata_lines = [
            "Metadata-Version: 2.4",
            "Name: authy-local",
            "Version: 1.0.0",
            "Requires-Python: >=3.14,<3.15",
        ]
        for req in requires_dist:
            metadata_lines.append(f"Requires-Dist: {req}")
        z.writestr("authy_local-1.0.0.dist-info/METADATA", "\n".join(metadata_lines) + "\n")


class TestAdversarialAllowlistValidation(unittest.TestCase):
    """Adversarial tests challenging _wheel() dependency allowlist validation."""

    def test_forbidden_unrelated_packages_rejected(self):
        """Standard forbidden third-party packages must be rejected with InstallError."""
        with tempfile.TemporaryDirectory() as tmp:
            whl = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
            for pkg in ("evil-package", "requests", "urllib3", "textual-evil", "textual_evil"):
                with self.subTest(pkg=pkg):
                    _make_mock_wheel(whl, [pkg])
                    with self.assertRaises(InstallError):
                        _wheel(whl)

    def test_multiple_requirements_with_forbidden_package_rejected(self):
        """Wheels mixing textual with a forbidden package must be rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            whl = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
            _make_mock_wheel(whl, ["textual>=0.80.0", "requests"])
            with self.assertRaises(InstallError):
                _wheel(whl)

    def test_allowed_exact_textual_and_version_specifications(self):
        """Exact textual package names and standard version specifiers must pass."""
        with tempfile.TemporaryDirectory() as tmp:
            whl = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
            for spec in (
                [],
                ["textual"],
                ["textual>=0.80.0"],
                ["textual==8.2.8"],
                ["textual>0.80.0"],
                ["textual<=9.0.0"],
                ["textual~=0.80.0"],
                ["textual>=0.80.0,<1.0.0"],
            ):
                with self.subTest(spec=spec):
                    _make_mock_wheel(whl, spec)
                    path, digest = _wheel(whl)
                    self.assertEqual(path, whl)
                    self.assertEqual(len(digest), 64)

    def test_forbidden_extra_dev_rejected(self):
        """Requires-Dist: textual; extra == 'dev' must be rejected (Defect: currently accepted)."""
        with tempfile.TemporaryDirectory() as tmp:
            whl = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
            _make_mock_wheel(whl, ['textual; extra == "dev"'])
            with self.assertRaises(InstallError):
                _wheel(whl)

    def test_forbidden_extra_space_dev_rejected(self):
        """Requires-Dist: textual ; extra == 'dev' must be rejected (Defect: currently accepted)."""
        with tempfile.TemporaryDirectory() as tmp:
            whl = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
            _make_mock_wheel(whl, ['textual ; extra == "dev"'])
            with self.assertRaises(InstallError):
                _wheel(whl)

    def test_forbidden_platform_marker_rejected(self):
        """Requires-Dist: textual; sys_platform == 'win32' must be rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            whl = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
            _make_mock_wheel(whl, ['textual; sys_platform == "win32"'])
            with self.assertRaises(InstallError):
                _wheel(whl)

    def test_forbidden_whitespace_extra_syntax_rejected(self):
        """Requires-Dist: textual [syntax] must be rejected (Defect: currently accepted)."""
        with tempfile.TemporaryDirectory() as tmp:
            whl = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
            _make_mock_wheel(whl, ["textual [syntax]"])
            with self.assertRaises(InstallError):
                _wheel(whl)

    def test_forbidden_direct_url_reference_rejected(self):
        """Requires-Dist: textual @ https://... must be rejected (Defect: currently accepted)."""
        with tempfile.TemporaryDirectory() as tmp:
            whl = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
            _make_mock_wheel(whl, ["textual @ https://evil.com/wheel.whl"])
            with self.assertRaises(InstallError):
                _wheel(whl)


class TestAdversarialOfflineWheelhouse(unittest.TestCase):
    """Adversarial tests challenging offline wheelhouse staging and fail-closed contracts."""

    def test_corrupted_wheelhouse_wheel_fails_closed(self):
        """A corrupted wheel in wheelhouse must cause installation to fail closed."""
        repo_root = Path(__file__).resolve().parent.parent
        real_wheel = next((repo_root / "dist").glob("authy_local-*.whl"))

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            isolated_dir = Path(tmp) / "isolated"
            isolated_dir.mkdir()
            fake_wheel = isolated_dir / real_wheel.name
            shutil.copyfile(real_wheel, fake_wheel)

            wheels_dir = isolated_dir / "wheels"
            wheels_dir.mkdir()
            (wheels_dir / "textual-8.2.8-py3-none-any.whl").write_bytes(b"corrupted binary")

            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with self.assertRaises(InstallError):
                    operate("install", home, wheel=fake_wheel, apply=True, environment={})
            finally:
                os.chdir(old_cwd)

    def test_missing_transitive_dependency_fails_closed(self):
        """Missing transitive dependencies in wheelhouse must fail closed with InstallError."""
        repo_root = Path(__file__).resolve().parent.parent
        real_wheel = next((repo_root / "dist").glob("authy_local-*.whl"))

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            isolated_dir = Path(tmp) / "isolated"
            isolated_dir.mkdir()
            fake_wheel = isolated_dir / real_wheel.name
            shutil.copyfile(real_wheel, fake_wheel)

            wheels_dir = isolated_dir / "wheels"
            wheels_dir.mkdir()
            textual_whl = next((repo_root / "dist/wheels").glob("textual-*.whl"))
            shutil.copyfile(
                textual_whl,
                wheels_dir / textual_whl.name,
            )

            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with self.assertRaises(InstallError):
                    operate("install", home, wheel=fake_wheel, apply=True, environment={})
            finally:
                os.chdir(old_cwd)

    def test_missing_wheelhouse_fails_closed_without_no_deps_bypass(self):
        """Missing wheelhouse must fail closed rather than silently installing with --no-deps."""
        repo_root = Path(__file__).resolve().parent.parent
        real_wheel = next((repo_root / "dist").glob("authy_local-*.whl"))

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            isolated_dir = Path(tmp) / "isolated"
            isolated_dir.mkdir()
            fake_wheel = isolated_dir / real_wheel.name
            shutil.copyfile(real_wheel, fake_wheel)

            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with self.assertRaises(InstallError):
                    operate("install", home, wheel=fake_wheel, apply=True, environment={})
                # If it didn't fail, check if textual import fails at runtime
                releases = list((home / ".local/share/authy-local/releases").glob("*"))
                if releases:
                    env_python = releases[0] / "bin/python"
                    res = subprocess.run(
                        [str(env_python), "-c", "import authy_local.tui"],
                        capture_output=True,
                    )
                    self.assertEqual(res.returncode, 0, "Broken release missing textual installed!")
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
