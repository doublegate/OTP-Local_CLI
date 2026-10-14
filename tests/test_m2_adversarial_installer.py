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
            for pkg in (
                "evil-package",
                "requests",
                "urllib3",
                "textual-evil",
                "textual_evil",
                "fido2-evil",
                "fido2_evil",
                "pluggy-evil",
                "pluggy_evil",
                "fido",
                "plug",
            ):
                with self.subTest(pkg=pkg):
                    _make_mock_wheel(whl, [pkg])
                    with self.assertRaises(InstallError):
                        _wheel(whl)

    def test_multiple_requirements_with_forbidden_package_rejected(self):
        """Wheels mixing allowed packages with a forbidden package must be rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            whl = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
            for reqs in (
                ["textual>=0.80.0", "requests"],
                ["textual>=0.80.0", "fido2>=2.0.0", "pluggy>=1.0.0", "requests"],
                ["fido2>=2.0.0", "evil-package"],
                ["pluggy>=1.0.0", "urllib3"],
            ):
                with self.subTest(reqs=reqs):
                    _make_mock_wheel(whl, reqs)
                    with self.assertRaises(InstallError):
                        _wheel(whl)

    def test_allowed_exact_dependencies_and_version_specifications(self):
        """Exact allowed package names (textual, fido2, pluggy) and standard version specifiers must pass."""
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
                ["fido2"],
                ["fido2>=2.0.0"],
                ["fido2==2.2.1"],
                ["fido2>=2.0.0,<3.0.0"],
                ["pluggy"],
                ["pluggy>=1.0.0"],
                ["pluggy==1.6.0"],
                ["pluggy>=1.0.0,<2.0.0"],
                ["textual>=0.80.0", "fido2>=2.0.0", "pluggy>=1.0.0"],
            ):
                with self.subTest(spec=spec):
                    _make_mock_wheel(whl, spec)
                    path, digest = _wheel(whl)
                    self.assertEqual(path, whl)
                    self.assertEqual(len(digest), 64)

    def test_forbidden_extra_dev_rejected(self):
        """Requires-Dist with extra == 'dev' must be rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            whl = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
            for req in (
                'textual; extra == "dev"',
                'fido2; extra == "dev"',
                'pluggy; extra == "dev"',
            ):
                with self.subTest(req=req):
                    _make_mock_wheel(whl, [req])
                    with self.assertRaises(InstallError):
                        _wheel(whl)

    def test_forbidden_extra_space_dev_rejected(self):
        """Requires-Dist with ' ; extra == dev' must be rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            whl = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
            for req in (
                'textual ; extra == "dev"',
                'fido2 ; extra == "dev"',
                'pluggy ; extra == "dev"',
            ):
                with self.subTest(req=req):
                    _make_mock_wheel(whl, [req])
                    with self.assertRaises(InstallError):
                        _wheel(whl)

    def test_forbidden_platform_marker_rejected(self):
        """Requires-Dist with environment markers must be rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            whl = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
            for req in (
                'textual; sys_platform == "win32"',
                'fido2; sys_platform == "linux"',
                'pluggy; python_version >= "3.14"',
            ):
                with self.subTest(req=req):
                    _make_mock_wheel(whl, [req])
                    with self.assertRaises(InstallError):
                        _wheel(whl)

    def test_forbidden_whitespace_extra_syntax_rejected(self):
        """Requires-Dist with extras syntax [syntax] must be rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            whl = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
            for req in ("textual [syntax]", "fido2 [extra]", "pluggy [testing]"):
                with self.subTest(req=req):
                    _make_mock_wheel(whl, [req])
                    with self.assertRaises(InstallError):
                        _wheel(whl)

    def test_forbidden_direct_url_reference_rejected(self):
        """Requires-Dist with @ direct URL must be rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            whl = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
            for req in (
                "textual @ https://evil.com/wheel.whl",
                "fido2 @ https://evil.com/fido2.whl",
                "pluggy @ https://evil.com/pluggy.whl",
            ):
                with self.subTest(req=req):
                    _make_mock_wheel(whl, [req])
                    with self.assertRaises(InstallError):
                        _wheel(whl)

    def test_forbidden_non_ascii_homoglyph_header_rejected(self):
        """Non-ASCII / Cyrillic homoglyph Requires-Dist headers returning Header objects must fail closed with InstallError."""
        with tempfile.TemporaryDirectory() as tmp:
            whl = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
            for req in (
                "t\u0435xtual",  # Cyrillic small letter ie (\u0435)
                "t\u0435xtual>=0.80.0",  # Cyrillic homoglyph with version
                "f\u0456do2",  # Cyrillic small letter byelorussian-ukrainian i (\u0456)
                "f\u0456do2>=2.0.0",  # Cyrillic homoglyph with version
                "\u0440luggy",  # Cyrillic small letter er (\u0440)
                "\u0440luggy>=1.0.0",  # Cyrillic homoglyph with version
                "textual\uff01",  # Fullwidth exclamation mark (\uff01)
            ):
                with self.subTest(req=req):
                    _make_mock_wheel(whl, [req])
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
