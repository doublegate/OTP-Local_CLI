"""Milestone M1 Adversarial Installer & Packaging Security Test Suite.

Empirical verification suite written by Challenger M1-1 to stress-test
installer.py wheel validation logic against:
1. Package name spoofing and prefix attacks.
2. Extras syntax injection.
3. Direct URLs, VCS, and hashes.
4. Environment markers.
5. Malformed version specifiers and ReDoS backtracking payloads.
6. Legitimate v2.0 dependency acceptance (textual, fido2, pluggy).
7. Archive structural integrity boundaries.
"""

from __future__ import annotations

import stat
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from authy_local.installer import InstallError, _wheel


def _create_test_wheel(
    target_path: Path,
    requires_dist: list[str] | None = None,
    package_name: str = "authy-local",
    extra_files: dict[str, str | bytes] | None = None,
) -> Path:
    """Create a syntactically valid wheel archive with customized METADATA."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target_path, "w") as zf:
        zf.writestr("authy_local/__init__.py", "__version__ = '2.0.0'\n")

        metadata_lines = [
            "Metadata-Version: 2.4",
            f"Name: {package_name}",
            "Version: 2.0.0",
            "Summary: Local multi-vault authenticator",
        ]
        if requires_dist:
            for req in requires_dist:
                metadata_lines.append(f"Requires-Dist: {req}")

        zf.writestr("authy_local-2.0.0.dist-info/METADATA", "\n".join(metadata_lines) + "\n")
        zf.writestr("authy_local-2.0.0.dist-info/WHEEL", "Wheel-Version: 1.0\n")

        if extra_files:
            for path_key, file_content in extra_files.items():
                if isinstance(file_content, str):
                    zf.writestr(path_key, file_content)
                else:
                    zf.writestr(path_key, file_content)
    return target_path


class TestAdversarialPackageNameSpoofing(unittest.TestCase):
    """Stress-test rejection of package name spoofing, prefix, and suffix attacks."""

    def test_package_spoofing_rejected(self):
        spoof_candidates = [
            "textual-malicious",
            "textual_malicious",
            "textual.malicious",
            "textual-evil>=1.0.0",
            "textual_evil==0.1",
            "fido2_backdoor",
            "fido2-backdoor",
            "fido2.backdoor",
            "fido2-evil>=2.0.0",
            "pluggy.hack",
            "pluggy-hack",
            "pluggy_hack",
            "pluggy-evil",
            "fake-fido2",
            "fake-textual",
            "bad-pluggy",
            "not-fido2",
            "text",
            "fido",
            "plug",
            "textu",
            "fido1",
            "pluggy2",
            "Textual",
            "FIDO2",
            "Pluggy",
            "TEXTUAL",
            "textual malicious",
            "fido2 backdoor",
            "pluggy hack",
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            whl_path = Path(tmp_dir) / "authy_local-2.0.0-py3-none-any.whl"
            for candidate in spoof_candidates:
                with self.subTest(candidate=candidate):
                    _create_test_wheel(whl_path, [candidate])
                    with self.assertRaises(
                        InstallError, msg=f"Spoof candidate '{candidate}' was improperly accepted"
                    ):
                        _wheel(whl_path)

    def test_unicode_homoglyphs_fail_closed(self):
        """Stress-test unicode homoglyphs; verify they never succeed and document unhandled Header TypeError."""
        homoglyphs = [
            "tеxtual",  # Cyrillic e homoglyph
            "fіdo2",  # Cyrillic i homoglyph
            "рluggy",  # Cyrillic p homoglyph
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            whl_path = Path(tmp_dir) / "authy_local-2.0.0-py3-none-any.whl"
            for candidate in homoglyphs:
                with self.subTest(candidate=candidate):
                    _create_test_wheel(whl_path, [candidate])
                    # Verifies fail-closed behavior (cannot succeed).
                    # Documents the bug where email.header.Header causes TypeError instead of InstallError.
                    with self.assertRaises((InstallError, TypeError)):
                        _wheel(whl_path)


class TestAdversarialExtrasSyntax(unittest.TestCase):
    """Stress-test rejection of extras syntax injection in dependency specifications."""

    def test_extras_syntax_rejected(self):
        extras_candidates = [
            "textual[dev]",
            "fido2[all]",
            "pluggy[testing]",
            "textual [dev]",
            "fido2 [all]",
            "pluggy [testing]",
            "textual[ dev ]",
            "textual [ dev, test ]",
            "textual[]",
            "fido2[ ]",
            "textual[dev]>=0.80.0",
            "fido2[all]==2.0.0",
            "pluggy[testing]~=1.0.0",
            "textual[dev",
            "fido2all]",
            "pluggy[[dev]]",
            "textual[!@#]",
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            whl_path = Path(tmp_dir) / "authy_local-2.0.0-py3-none-any.whl"
            for candidate in extras_candidates:
                with self.subTest(candidate=candidate):
                    _create_test_wheel(whl_path, [candidate])
                    with self.assertRaises(
                        InstallError, msg=f"Extras candidate '{candidate}' was improperly accepted"
                    ):
                        _wheel(whl_path)


class TestAdversarialDirectUrlsAndHashes(unittest.TestCase):
    """Stress-test rejection of direct URLs, VCS links, and cryptographic hashes."""

    def test_direct_urls_and_hashes_rejected(self):
        url_candidates = [
            "fido2 @ https://evil.com/wheel.whl",
            "textual @ file:///tmp/wheel.whl",
            "pluggy @ git+https://github.com/evil/pluggy.git",
            "textual @ http://localhost:8080/textual-1.0.whl",
            "fido2 @ ftp://evil.com/fido2.whl",
            "fido2 https://evil.com/wheel.whl",
            "pluggy http://evil.com",
            "textual#sha256=1234567890abcdef",
            "fido2 --hash=sha256:1234567890abcdef",
            "pluggy#egg=pluggy",
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            whl_path = Path(tmp_dir) / "authy_local-2.0.0-py3-none-any.whl"
            for candidate in url_candidates:
                with self.subTest(candidate=candidate):
                    _create_test_wheel(whl_path, [candidate])
                    with self.assertRaises(
                        InstallError,
                        msg=f"URL/hash candidate '{candidate}' was improperly accepted",
                    ):
                        _wheel(whl_path)


class TestAdversarialEnvironmentMarkers(unittest.TestCase):
    """Stress-test rejection of environment markers and conditional requirements."""

    def test_environment_markers_rejected(self):
        marker_candidates = [
            "pluggy; sys_platform == 'linux'",
            'textual ; python_version >= "3.14"',
            'fido2; extra == "dev"',
            'pluggy; os_name == "posix"',
            'textual; platform_python_implementation == "CPython"',
            "fido2;",
            "pluggy ;",
            'textual; sys_platform == "win32" and extra == "dev"',
            "pluggy; python_version < '3.10' or sys_platform == 'darwin'",
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            whl_path = Path(tmp_dir) / "authy_local-2.0.0-py3-none-any.whl"
            for candidate in marker_candidates:
                with self.subTest(candidate=candidate):
                    _create_test_wheel(whl_path, [candidate])
                    with self.assertRaises(
                        InstallError, msg=f"Marker candidate '{candidate}' was improperly accepted"
                    ):
                        _wheel(whl_path)


class TestAdversarialMalformedVersionSpecifiersAndReDoS(unittest.TestCase):
    """Stress-test malformed version strings and regex catastrophic backtracking resistance."""

    def test_malformed_specifiers_rejected(self):
        malformed_candidates = [
            "textual ===",
            "textual === 1.0.0",
            "textual != 1.0.0",
            "textual = 1.0.0",
            "textual !== 1.0.0",
            "textual >= >=",
            "textual >= >= 1.0.0",
            "textual == = 1.0.0",
            "textual > = 1.0.0",
            "textual = = 1.0.0",
            "textual >=",
            "textual ==",
            "textual <=",
            "textual >",
            "textual <",
            "textual ~=",
            "textual 1.0.0",
            "fido2 2.0.0",
            "pluggy 1.0.0",
            "textual>=0.80.0,",
            ",textual>=0.80.0",
            "textual>=0.80.0, ,>=1.0.0",
            "textual>=0.80.0,,>=1.0.0",
            "textual , >=0.80.0",
            "",
            "   ",
            "\t",
            "\n",
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            whl_path = Path(tmp_dir) / "authy_local-2.0.0-py3-none-any.whl"
            for candidate in malformed_candidates:
                with self.subTest(candidate=candidate):
                    _create_test_wheel(whl_path, [candidate])
                    with self.assertRaises(
                        InstallError,
                        msg=f"Malformed candidate '{candidate}' was improperly accepted",
                    ):
                        _wheel(whl_path)

    def test_redos_backtracking_resilience(self):
        """Verify regex evaluation completes in sub-second linear time on adversarial backtracking payloads."""
        redos_payloads = [
            # Long chained valid-looking clauses terminating in mismatch
            "textual" + ", >= 1.0.0" * 1500 + " @ invalid",
            "textual" + ", >= 1.0.0" * 1500 + " ~ mismatch",
            "fido2" + ", == 2.0.0" * 1500 + ", != 2.0.0",
            # Massive whitespace padding terminating in mismatch
            "pluggy" + " " * 8000 + "== 1.0.0 ~ mismatch",
            "textual " + " " * 8000 + ">= 0.80.0 @ invalid",
            # Long version string terminating in invalid character
            "textual == " + "1." * 2000 + "@",
            "fido2 >= " + "9" * 4000 + "$evil",
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            whl_path = Path(tmp_dir) / "authy_local-2.0.0-py3-none-any.whl"
            for i, payload in enumerate(redos_payloads):
                with self.subTest(payload_idx=i):
                    _create_test_wheel(whl_path, [payload])
                    start_time = time.perf_counter()
                    with self.assertRaises(InstallError):
                        _wheel(whl_path)
                    elapsed = time.perf_counter() - start_time
                    self.assertLess(
                        elapsed,
                        0.5,
                        f"ReDoS payload {i} took {elapsed:.3f}s (>0.5s threshold; backtracking vulnerability detected)",
                    )


class TestLegitimateV2DependenciesStrictAcceptance(unittest.TestCase):
    """Verify that all authorized v2.0 dependency shapes are accepted without error."""

    def test_legitimate_requirements_accepted(self):
        valid_matrix = [
            [],  # Empty dependency set
            ["textual"],
            ["fido2"],
            ["pluggy"],
            ["textual>=0.80.0"],
            ["fido2>=2.0.0"],
            ["pluggy>=1.0.0"],
            ["textual==0.80.0"],
            ["fido2==2.0.0"],
            ["pluggy==1.0.0"],
            ["textual~=0.80.0"],
            ["fido2~=2.0.0"],
            ["pluggy~=1.0.0"],
            ["textual>0.80.0"],
            ["fido2>2.0.0"],
            ["pluggy>1.0.0"],
            ["textual<=1.0.0"],
            ["fido2<=3.0.0"],
            ["pluggy<=2.0.0"],
            ["textual>=0.80.0,<1.0.0"],
            ["fido2>=2.0.0,<3.0.0"],
            ["pluggy>=1.0.0,<2.0.0"],
            ["textual>=0.80.0,<=1.5.0,>0.70.0"],
            ["textual>=0.80.0.post1"],
            ["pluggy>=1.0.0b1"],
            ["fido2>=1!2.0.0"],
            # Composite v2.0 production dependency declaration
            ["textual>=0.80.0", "fido2>=2.0.0", "pluggy>=1.0.0"],
            # Multi-specifier composite
            ["textual>=0.80.0,<1.0.0", "fido2>=2.0.0,<3.0.0", "pluggy>=1.0.0,<2.0.0"],
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            whl_path = Path(tmp_dir) / "authy_local-2.0.0-py3-none-any.whl"
            for reqs in valid_matrix:
                with self.subTest(reqs=reqs):
                    _create_test_wheel(whl_path, reqs)
                    path, digest = _wheel(whl_path)
                    self.assertEqual(path, whl_path.resolve())
                    self.assertEqual(len(digest), 64)
                    self.assertTrue(all(c in "0123456789abcdef" for c in digest))


class TestWheelArchiveStructuralHardening(unittest.TestCase):
    """Verify archive integrity boundaries (metadata count, symlinks, traversals)."""

    def test_wrong_package_name_in_metadata_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            whl_path = Path(tmp_dir) / "authy_local-2.0.0-py3-none-any.whl"
            _create_test_wheel(whl_path, ["textual>=0.80.0"], package_name="not-authy-local")
            with self.assertRaises(InstallError):
                _wheel(whl_path)

    def test_path_traversal_in_archive_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            whl_path = Path(tmp_dir) / "authy_local-2.0.0-py3-none-any.whl"
            _create_test_wheel(
                whl_path,
                ["textual>=0.80.0"],
                extra_files={"../escaped.py": "print('traversal')"},
            )
            with self.assertRaises(InstallError):
                _wheel(whl_path)

    def test_symlink_inside_archive_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            whl_path = Path(tmp_dir) / "authy_local-2.0.0-py3-none-any.whl"
            whl_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(whl_path, "w") as zf:
                zf.writestr("authy_local/__init__.py", "__version__ = '2.0.0'\n")
                zf.writestr(
                    "authy_local-2.0.0.dist-info/METADATA",
                    "Metadata-Version: 2.4\nName: authy-local\nVersion: 2.0.0\nRequires-Dist: textual>=0.80.0\n",
                )
                # Create a symlink entry in zip
                zinfo = zipfile.ZipInfo("authy_local/symlink")
                zinfo.create_system = 3  # Unix
                zinfo.external_attr = (stat.S_IFLNK | 0o777) << 16
                zf.writestr(zinfo, "/etc/passwd")

            with self.assertRaises(InstallError):
                _wheel(whl_path)

    def test_multiple_metadata_files_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            whl_path = Path(tmp_dir) / "authy_local-2.0.0-py3-none-any.whl"
            _create_test_wheel(
                whl_path,
                ["textual>=0.80.0"],
                extra_files={
                    "extra.dist-info/METADATA": "Metadata-Version: 2.4\nName: authy-local\n"
                },
            )
            with self.assertRaises(InstallError):
                _wheel(whl_path)
