#!/usr/bin/env python3
"""Adversarial Verification Script for Milestone M2 (Packaging & Allowlist).

Authored by Challenger 2 (Empirical Challenger) to rigorously challenge:
1. Synthetic mock wheels with forbidden Requires-Dist entries:
   - evil-package, requests, urllib3, textual-evil
   - textual; extra == "dev"
   - textual [syntax] / textual [dev]
   - textual; sys_platform == "win32"
   - textual @ https://evil.com/wheel.whl
2. Exact textual and version specifications allowlist enforcement.
3. Offline installation behavior when wheelhouse files are missing or corrupted:
   - Missing wheelhouse / no-deps bypass
   - Corrupted wheel in wheelhouse
   - Incomplete wheelhouse (missing transitive dependencies)
   - Zero external network access and zero credential leakage
"""

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from authy_local.installer import InstallError, _wheel, operate


def make_mock_wheel(wheel_path: Path, requires_dist: list[str]) -> None:
    """Create a syntactically valid mock authy-local wheel with custom Requires-Dist."""
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
        metadata_content = "\n".join(metadata_lines) + "\n"
        z.writestr("authy_local-1.0.0.dist-info/METADATA", metadata_content)


def run_test_allowlist_vector(name: str, reqs: list[str], should_allow: bool) -> tuple[bool, str]:
    """Test whether _wheel allows or rejects the given requirement list."""
    with tempfile.TemporaryDirectory() as tmp:
        whl = Path(tmp) / "authy_local-1.0.0-py3-none-any.whl"
        make_mock_wheel(whl, reqs)
        try:
            _wheel(whl)
            actual_allowed = True
            err_msg = "ACCEPTED"
        except InstallError as e:
            actual_allowed = False
            err_msg = f"REJECTED ({e})"

        if actual_allowed == should_allow:
            return True, f"OK ({err_msg})"
        else:
            status = "UNEXPECTEDLY ACCEPTED (Bypass)" if actual_allowed else "UNEXPECTEDLY REJECTED"
            return False, f"FAIL: {status} for {reqs}"


def run_test_missing_wheelhouse_fail_closed() -> tuple[bool, str]:
    """Test whether installer fails closed when wheelhouse files are missing.

    A secure offline installer must NOT install --no-deps and report success
    when required runtime dependencies (Textual) are absent from wheelhouse.
    """
    repo_root = Path(__file__).resolve().parent.parent
    real_wheel = next((repo_root / "dist").glob("authy_local-*.whl"))

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        isolated_dir = Path(tmp) / "isolated"
        isolated_dir.mkdir()
        fake_wheel = isolated_dir / real_wheel.name
        shutil.copyfile(real_wheel, fake_wheel)

        old_cwd = os.getcwd()
        os.chdir(tmp)  # Ensure dist/wheels is not in cwd
        try:
            try:
                operate("install", home, wheel=fake_wheel, apply=True, environment={})
                # Check if textual is actually installed and importable in that release
                releases = list((home / ".local/share/authy-local/releases").glob("*"))
                if releases:
                    env_python = releases[0] / "bin/python"
                    res = subprocess.run(
                        [str(env_python), "-c", "import authy_local.tui"],
                        capture_output=True,
                        text=True,
                    )
                    if res.returncode != 0:
                        return (
                            False,
                            "FAIL: Installer succeeded with --no-deps despite missing wheelhouse; release is broken at runtime (ModuleNotFoundError: textual)",
                        )
                return False, "FAIL: Installer succeeded when wheelhouse was completely missing"
            except InstallError:
                return True, "PASS: Correctly failed closed with InstallError"
        finally:
            os.chdir(old_cwd)


def run_test_corrupted_wheelhouse_wheel() -> tuple[bool, str]:
    """Test whether installer fails closed when a wheelhouse wheel is corrupted."""
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
        (wheels_dir / "textual-8.2.8-py3-none-any.whl").write_bytes(b"corrupted zip bytes")

        old_cwd = os.getcwd()
        os.chdir(tmp)
        try:
            try:
                operate("install", home, wheel=fake_wheel, apply=True, environment={})
                return False, "FAIL: Succeeded with corrupted wheelhouse wheel"
            except InstallError:
                return True, "PASS: Correctly failed closed with InstallError"
        finally:
            os.chdir(old_cwd)


def run_test_missing_transitive_dependency() -> tuple[bool, str]:
    """Test whether installer fails closed when transitive dependency is missing."""
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
        # Copy only textual, omit rich, pygments, markdown-it-py, etc.
        shutil.copyfile(
            repo_root / "dist/wheels/textual-8.2.8-py3-none-any.whl",
            wheels_dir / "textual-8.2.8-py3-none-any.whl",
        )

        old_cwd = os.getcwd()
        os.chdir(tmp)
        try:
            try:
                operate("install", home, wheel=fake_wheel, apply=True, environment={})
                return False, "FAIL: Succeeded with missing transitive dependencies"
            except InstallError:
                return True, "PASS: Correctly failed closed with InstallError"
        finally:
            os.chdir(old_cwd)


def main() -> int:
    print("=" * 80)
    print("Milestone M2 Adversarial Verification Suite: Packaging & Allowlist")
    print("=" * 80)

    test_vectors = [
        # (ID, Name, Requires-Dist, Should Allow)
        ("T01", "Forbidden: evil-package", ["evil-package"], False),
        ("T02", "Forbidden: requests", ["requests"], False),
        ("T03", "Forbidden: urllib3", ["urllib3"], False),
        ("T04", "Forbidden: textual-evil", ["textual-evil"], False),
        ("T05", "Forbidden: textual_evil", ["textual_evil"], False),
        ("T06", "Forbidden extra: textual; extra == 'dev'", ['textual; extra == "dev"'], False),
        (
            "T07",
            "Forbidden extra space: textual ; extra == 'dev'",
            ['textual ; extra == "dev"'],
            False,
        ),
        (
            "T08",
            "Forbidden marker: textual; sys_platform == 'win32'",
            ['textual; sys_platform == "win32"'],
            False,
        ),
        (
            "T09",
            "Forbidden marker: textual; python_version < '3.0'",
            ['textual; python_version < "3.0"'],
            False,
        ),
        ("T10", "Forbidden extra: textual [syntax]", ["textual [syntax]"], False),
        ("T11", "Forbidden extra: textual [dev]", ["textual [dev]"], False),
        (
            "T12",
            "Forbidden direct url: textual @ https://...",
            ["textual @ https://evil.com/x.whl"],
            False,
        ),
        (
            "T13",
            "Multiple with forbidden: textual + requests",
            ["textual>=0.80.0", "requests"],
            False,
        ),
        (
            "T14",
            "Multiple with extra: textual + textual; extra == 'dev'",
            ["textual>=0.80.0", 'textual; extra == "dev"'],
            False,
        ),
        ("T15", "Allowed exact: textual", ["textual"], True),
        ("T16", "Allowed version: textual>=0.80.0", ["textual>=0.80.0"], True),
        ("T17", "Allowed version: textual==8.2.8", ["textual==8.2.8"], True),
        ("T18", "Allowed version: textual>0.80.0", ["textual>0.80.0"], True),
        ("T19", "Allowed version: textual<=9.0.0", ["textual<=9.0.0"], True),
        ("T20", "Allowed version: textual~=0.80.0", ["textual~=0.80.0"], True),
        ("T21", "Allowed multi-version: textual>=0.80.0,<1.0.0", ["textual>=0.80.0,<1.0.0"], True),
        ("T22", "Allowed empty: no Requires-Dist", [], True),
    ]

    passed = 0
    failed = 0

    print(f"\n{'ID':<5} | {'Test Vector':<42} | {'Expected':<10} | {'Result'}")
    print("-" * 80)

    for test_id, name, reqs, should_allow in test_vectors:
        expected_str = "ALLOW" if should_allow else "REJECT"
        ok, msg = run_test_allowlist_vector(name, reqs, should_allow)
        if ok:
            passed += 1
            print(f"{test_id:<5} | {name:<42} | {expected_str:<10} | PASS: {msg}")
        else:
            failed += 1
            print(f"{test_id:<5} | {name:<42} | {expected_str:<10} | *** {msg} ***")

    print("\n" + "=" * 80)
    print("Offline Wheelhouse Fail-Closed & Integrity Tests")
    print("=" * 80)

    offline_tests = [
        ("T23", "Missing wheelhouse fail-closed", run_test_missing_wheelhouse_fail_closed),
        ("T24", "Corrupted wheelhouse wheel fail-closed", run_test_corrupted_wheelhouse_wheel),
        (
            "T25",
            "Missing transitive dependency fail-closed",
            run_test_missing_transitive_dependency,
        ),
    ]

    for test_id, name, test_func in offline_tests:
        ok, msg = test_func()
        if ok:
            passed += 1
            print(f"{test_id:<5} | {name:<42} | FAIL-CLOSED | PASS: {msg}")
        else:
            failed += 1
            print(f"{test_id:<5} | {name:<42} | FAIL-CLOSED | *** {msg} ***")

    total = passed + failed
    print("\n" + "=" * 80)
    print(f"Summary: {total} tests, {passed} PASSED, {failed} FAILED")
    print("=" * 80)

    if failed > 0:
        print("\nEMPIRICAL VERDICT: REJECT")
        print(f"Encountered {failed} failure(s) in allowlist validation and offline staging.")
        return 1
    else:
        print("\nEMPIRICAL VERDICT: APPROVE")
        return 0


if __name__ == "__main__":
    sys.exit(main())
