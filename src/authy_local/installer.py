"""Offline, preview-first home installer. Never accesses the authentication backend."""

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import venv
import zipfile
from contextlib import contextmanager
from email.parser import BytesParser
from pathlib import Path


class InstallError(Exception):
    """Safe installation failure; caller reports no external command output."""


WRAPPERS = {
    "otp1p.fish": "function otp1p\n    otp-local show $argv\nend\n",
    "otp1pc.fish": "function otp1pc\n    otp-local copy $argv\nend\n",
    "otp1pf.fish": "function otp1pf\n    otp-local select $argv\nend\n",
}
ALIAS = "function otp\n    otp1p $argv\nend\n"


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _safe(path, home):
    """Refuse symbolic links in every component, including nonexistent leaf links."""
    path = Path(os.path.abspath(path))
    if path != home and home not in path.parents:
        raise InstallError("Target escapes the selected home.")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise InstallError("Symbolic link in installation path.")
        if part.exists() and part != path and not part.is_dir():
            raise InstallError("Non-directory installation parent.")
    return path


def _paths(home, environment, *, ambient=False):
    roots = {}
    for key, default in (
        ("DATA", ".local/share"),
        ("CONFIG", ".config"),
        ("STATE", ".local/state"),
    ):
        raw = environment.get(f"XDG_{key}_HOME")
        if ambient and raw is not None:
            raw_path = Path(raw)
            if raw_path != home and home not in raw_path.parents:
                raw = None
        if raw is None:
            raw = str(home / default)
        if not Path(raw).is_absolute():
            raise InstallError("XDG directories must be absolute.")
        roots[key] = _safe(Path(raw), home)
    return roots


def _snapshot(path):
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise InstallError("Target is not a bounded regular file.")
    data = path.read_bytes()
    return {
        "data": base64.b64encode(data).decode(),
        "mode": stat.S_IMODE(path.stat().st_mode),
        "hash": _hash(data),
    }


def _valid_snapshot(value):
    if value is None:
        return
    try:
        data = base64.b64decode(value["data"], validate=True)
        valid = (
            set(value) == {"data", "mode", "hash"}
            and len(data) <= 1024 * 1024
            and type(value["mode"]) is int
            and 0 <= value["mode"] <= 0o777
            and value["hash"] == _hash(data)
        )
    except KeyError, TypeError, ValueError:
        valid = False
    if not valid:
        raise InstallError("Invalid ownership snapshot.")


def _write(path, data, mode=0o600):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".authy-local-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
        os.replace(name, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _put(path, snapshot):
    if snapshot is None:
        path.unlink(missing_ok=True)
    else:
        _write(path, base64.b64decode(snapshot["data"], validate=True), snapshot["mode"])


def _json_write(path, value):
    _write(path, json.dumps(value, sort_keys=True).encode())


def _read(path):
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise InstallError("Invalid installer state.")
    try:
        return json.loads(path.read_bytes())
    except ValueError, UnicodeError:
        raise InstallError("Invalid installer state.") from None


def _validate_manifest(value, targets, releases, home):
    if value is None:
        return
    try:
        if set(value) != {"schema", "release", "files", "tree"} or value["schema"] != 1:
            raise ValueError
        release = value["release"]
        if (
            not isinstance(release, str)
            or len(release) != 64
            or any(c not in "0123456789abcdef" for c in release)
        ):
            raise ValueError
        if not isinstance(value["files"], dict) or not value["files"]:
            raise ValueError
        for raw, entry in value["files"].items():
            path = _safe(Path(raw), home)
            if str(path) != raw or path not in targets or set(entry) != {"installed", "original"}:
                raise ValueError
            _valid_snapshot(entry["installed"])
            _valid_snapshot(entry["original"])
            if entry["installed"] is None:
                raise ValueError
        if not isinstance(value["tree"], dict) or not value["tree"]:
            raise ValueError
        for raw, digest in value["tree"].items():
            relative = Path(raw)
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise ValueError
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError
        _safe(releases / release, home)
    except KeyError, TypeError, ValueError:
        raise InstallError("Invalid ownership manifest.") from None


def _tree(path):
    result = {}
    if not path.is_dir() or path.is_symlink():
        raise InstallError("Release is unavailable.")
    for file in path.rglob("*"):
        relative = file.relative_to(path).as_posix()
        if file.is_symlink():
            # CPython venv creates this single architecture compatibility link.
            if relative != "lib64" or os.readlink(file) != "lib":
                raise InstallError("Unexpected release symlink.")
            continue
        if file.is_file():
            result[relative] = _hash(file.read_bytes())
    return result


def _verify_release(manifest, releases):
    current_tree = {
        k: v
        for k, v in _tree(releases / manifest["release"]).items()
        if "__pycache__" not in k and not k.endswith(".pyc")
    }
    manifest_tree = {
        k: v
        for k, v in manifest["tree"].items()
        if "__pycache__" not in k and not k.endswith(".pyc")
    }
    if current_tree != manifest_tree:
        raise InstallError("Installed release was modified.")


def _wheel(path):
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
        raise InstallError("Expected a bounded local wheel.")
    if not path.name.startswith("authy_local-") or not path.name.endswith("-py3-none-any.whl"):
        raise InstallError("Expected the local authy-local wheel.")
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(row.file_size for row in entries) > 64 * 1024 * 1024:
                raise ValueError
            for entry in entries:
                name = Path(entry.filename)
                if name.is_absolute() or ".." in name.parts or "\\" in entry.filename:
                    raise ValueError
                if stat.S_ISLNK(entry.external_attr >> 16):
                    raise ValueError
            metadata = [row for row in entries if row.filename.endswith(".dist-info/METADATA")]
            if len(metadata) != 1:
                raise ValueError
            content = BytesParser().parsebytes(archive.read(metadata[0]))
            if content.get_all("Name") != ["authy-local"]:
                raise ValueError
            pattern = re.compile(
                r"^textual(\s*(==|>=|<=|>|<|~=)\s*[\w\.\*\+!]+(\s*,\s*(==|>=|<=|>|<|~=)\s*[\w\.\*\+!]+)*)?$"
            )
            for req in content.get_all("Requires-Dist") or ():
                if any(ch in req for ch in (";", "[", "]", "@")):
                    raise ValueError("Invalid dependency")
                if not pattern.match(req.strip()):
                    raise ValueError("Invalid dependency")
    except OSError, ValueError, zipfile.BadZipFile, UnicodeError:
        raise InstallError("Invalid local wheel.") from None
    return path, _hash(path.read_bytes())


def _stage(wheel, destination):
    if destination.exists():
        raise InstallError("Unowned release directory already exists.")

    find_links = []
    wheelhouse = wheel.parent / "wheels"
    dist_wheels = Path("dist/wheels")
    if wheelhouse.is_dir() and any(wheelhouse.glob("*.whl")):
        find_links = ["--find-links", str(wheelhouse)]
    elif dist_wheels.is_dir() and any(dist_wheels.glob("*.whl")):
        find_links = ["--find-links", str(dist_wheels.resolve())]
    elif any(w for w in wheel.parent.glob("*.whl") if w != wheel):
        find_links = ["--find-links", str(wheel.parent)]

    requires_dist = []
    with zipfile.ZipFile(wheel) as archive:
        metadata = [
            row for row in archive.infolist() if row.filename.endswith(".dist-info/METADATA")
        ]
        if metadata:
            content = BytesParser().parsebytes(archive.read(metadata[0]))
            requires_dist = content.get_all("Requires-Dist") or []

    if requires_dist and not find_links:
        raise InstallError(
            "Offline release prep failed: local wheelhouse missing required dependencies."
        )

    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        venv.EnvBuilder(with_pip=True, symlinks=False).create(destination)
        environment = {
            "PATH": os.defpath,
            "HOME": str(destination),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PIP_CONFIG_FILE": os.devnull,
        }

        for arguments in (
            [
                str(destination / "bin/python"),
                "-I",
                "-m",
                "pip",
                "--isolated",
                "install",
                "--no-index",
                *find_links,
                "--no-compile",
                "--disable-pip-version-check",
                str(wheel),
            ],
            [str(destination / "bin/python"), "-I", "-m", "authy_local", "--help"],
            [str(destination / "bin/python"), "-I", "-c", "import authy_local.tui, textual"],
        ):
            try:
                result = subprocess.run(
                    arguments,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=60,
                )
            except OSError, subprocess.TimeoutExpired:
                raise InstallError("Offline release preparation failed.") from None
            if result.returncode:
                raise InstallError("Offline release preparation failed.")
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


@contextmanager
def _lock(state):
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    if stat.S_IMODE(state.stat().st_mode) != 0o700 or state.stat().st_uid != os.getuid():
        raise InstallError("Installer state must be private and owned by this user.")
    descriptor = os.open(state / "lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise InstallError("Another installer operation is active.") from None
        yield
    finally:
        os.close(descriptor)


def _recover(state, targets, home):
    journal = _read(state / "journal.json")
    if journal is None:
        return
    try:
        if set(journal) != {"schema", "changes", "manifest", "previous"} or journal["schema"] != 1:
            raise ValueError
        for raw, row in journal["changes"].items():
            path = _safe(Path(raw), home)
            if path not in targets or set(row) != {"before", "after"}:
                raise ValueError
            _valid_snapshot(row["before"])
            _valid_snapshot(row["after"])
        _valid_snapshot(journal["manifest"])
        _valid_snapshot(journal["previous"])
    except KeyError, TypeError, ValueError:
        raise InstallError("Invalid recovery journal.") from None
    # Restore our unchanged writes while retaining any concurrent edit and journal.
    conflicts = False
    for raw, row in reversed(list(journal["changes"].items())):
        _safe(Path(raw), home)
        current = _snapshot(Path(raw))
        if current == row["after"]:
            _put(Path(raw), row["before"])
        elif current != row["before"]:
            conflicts = True
    if conflicts:
        raise InstallError("Recovery conflicts with a modified target.")
    _put(state / "manifest.json", journal["manifest"])
    _put(state / "previous.json", journal["previous"])
    (state / "journal.json").unlink()


def _activate(launcher, snapshot):
    _put(launcher, snapshot)


def _transaction(state, changes, manifest, previous, launcher, home):
    journal = {
        "schema": 1,
        "changes": changes,
        "manifest": _snapshot(state / "manifest.json"),
        "previous": _snapshot(state / "previous.json"),
    }
    _json_write(state / "journal.json", journal)
    for raw, row in changes.items():
        if Path(raw) != launcher:
            _safe(Path(raw), home)
            if _snapshot(Path(raw)) != row["before"]:
                raise InstallError("Installation target changed during activation.")
            _put(Path(raw), row["after"])
    # Activation happens only after all wrappers have landed.
    if str(launcher) in changes:
        _safe(launcher, home)
        if _snapshot(launcher) != changes[str(launcher)]["before"]:
            raise InstallError("Launcher changed during activation.")
        _activate(launcher, changes[str(launcher)]["after"])
    if manifest is None:
        (state / "manifest.json").unlink(missing_ok=True)
    else:
        _json_write(state / "manifest.json", manifest)
    if previous is None:
        (state / "previous.json").unlink(missing_ok=True)
    else:
        _json_write(state / "previous.json", previous)
    (state / "journal.json").unlink()


def operate(action, home, *, wheel=None, apply=False, backup=(), alias=False, environment=None):
    """Return a path-only plan/result. Apply is deliberately separate from preview."""
    home = Path(os.path.abspath(home))
    _safe(home, home)
    roots = _paths(
        home, os.environ if environment is None else environment, ambient=environment is None
    )
    state = _safe(roots["STATE"] / "authy-local", home)
    releases = _safe(roots["DATA"] / "authy-local/releases", home)
    launcher = _safe(home / ".local/bin/otp-local", home)
    functions = roots["CONFIG"] / "fish/functions"
    targets = {launcher, *(_safe(functions / name, home) for name in (*WRAPPERS, "otp.fish"))}
    for filename in ("manifest.json", "previous.json", "prepared.json", "journal.json", "lock"):
        _safe(state / filename, home)
    if action not in {"install", "rollback", "uninstall"}:
        raise InstallError("Unknown installer operation.")
    artifact = _wheel(wheel) if action == "install" else None
    if action != "install" and (wheel is not None or backup or alias):
        raise InstallError("Install-only options are not valid here.")

    def perform():
        if (state / "journal.json").exists():
            if not apply:
                raise InstallError("Interrupted operation requires apply recovery before preview.")
            _recover(state, targets, home)
        current = _read(state / "manifest.json")
        previous = _read(state / "previous.json")
        _validate_manifest(current, targets, releases, home)
        _validate_manifest(previous, targets, releases, home)
        if current:
            _verify_release(current, releases)
        if action == "install":
            source, release_id = artifact
            if current and alias != (str(functions / "otp.fish") in current["files"]):
                raise InstallError("Changing the generic alias requires uninstall first.")
            selected = {str(_safe(Path(raw), home)) for raw in backup}
            if any(Path(raw) not in targets for raw in selected):
                raise InstallError("Backup selection must name an exact installation target.")
            release = releases / release_id
            contents = {functions / name: value.encode() for name, value in WRAPPERS.items()}
            if alias:
                contents[functions / "otp.fish"] = ALIAS.encode()
            if current and set(current["files"]) != {str(path) for path in contents} | {
                str(launcher)
            }:
                raise InstallError("Finish the partial uninstall before reinstalling.")
            # A shell launcher safely quotes the fixed selected runtime path.
            quoted = "'" + str(release / "bin/python").replace("'", "'\\''") + "'"
            contents[launcher] = (f'#!/bin/sh\nexec {quoted} -I -B -m authy_local "$@"\n').encode()
            files = {}
            for path, data in contents.items():
                before = _snapshot(path)
                owned = current and current["files"].get(str(path))
                if owned and before != owned["installed"]:
                    raise InstallError("Owned target was modified.")
                if before is not None and not owned and str(path) not in selected:
                    raise InstallError("Unowned target collision; select its exact backup path.")
                installed = {
                    "data": base64.b64encode(data).decode(),
                    "mode": 0o755 if path == launcher else 0o600,
                    "hash": _hash(data),
                }
                files[str(path)] = {
                    "installed": installed,
                    "original": owned["original"] if owned else before,
                }
            if selected - set(files):
                raise InstallError("Backup selection is not part of this installation.")
            if current and current["release"] == release_id:
                return ["unchanged " + raw for raw in files]
            changes = {
                raw: {"before": _snapshot(Path(raw)), "after": row["installed"]}
                for raw, row in files.items()
            }
            plan = [
                f"install {raw} sha256={row['installed']['hash']}" for raw, row in files.items()
            ]
            if release.exists():
                prepared = _read(state / "prepared.json")
                _validate_manifest(prepared, targets, releases, home)
                if prepared is None or prepared["release"] != release_id:
                    raise InstallError("Unowned release directory already exists.")
                _verify_release(prepared, releases)
                tree = prepared["tree"]
            else:
                tree = None
            if not apply:
                return [f"source {source} sha256={release_id}", f"release {release}", *plan]
            if tree is None:
                _stage(source, release)
                tree = _tree(release)
            manifest = {"schema": 1, "release": release_id, "files": files, "tree": tree}
            # Retain proven staging provenance so recovery can retry the same wheel.
            _json_write(state / "prepared.json", manifest)
            try:
                _transaction(state, changes, manifest, current, launcher, home)
            except BaseException:
                _recover(state, targets, home)
                raise
            return plan
        if current is None:
            return ["nothing installed"]
        if action == "rollback":
            if previous is None:
                raise InstallError("No verified previous release is available.")
            _verify_release(previous, releases)
            if set(previous["files"]) != set(current["files"]):
                raise InstallError("Rollback ownership targets differ.")
            changes = {}
            for raw, row in current["files"].items():
                before = _snapshot(Path(raw))
                if before != row["installed"]:
                    raise InstallError("Rollback target was modified.")
                changes[raw] = {"before": before, "after": previous["files"][raw]["installed"]}
            if apply:
                try:
                    _transaction(state, changes, previous, current, launcher, home)
                except BaseException:
                    _recover(state, targets, home)
                    raise
            return ["rollback " + raw for raw in changes]
        changes, remaining, plan = {}, {}, []
        for raw, row in current["files"].items():
            before = _snapshot(Path(raw))
            if before != row["installed"]:
                remaining[raw] = row
                plan.append("preserved modified " + raw)
            else:
                changes[raw] = {"before": before, "after": row["original"]}
                plan.append("restore original " + raw if row["original"] else "remove " + raw)
        manifest = dict(current, files=remaining) if remaining else None
        if apply:
            try:
                _transaction(state, changes, manifest, None, launcher, home)
            except BaseException:
                _recover(state, targets, home)
                raise
        return plan

    if not apply:
        return perform()
    with _lock(state):
        return perform()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline home installer; defaults to preview.")
    parser.add_argument("action", choices=("install", "rollback", "uninstall"))
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", action="append", default=[], metavar="EXACT_TARGET")
    parser.add_argument("--generic-alias", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if arguments.action == "install" and arguments.wheel is None:
            raise InstallError("Install requires an explicit local wheel.")
        plan = operate(
            arguments.action,
            arguments.home,
            wheel=arguments.wheel,
            apply=arguments.apply,
            backup=arguments.backup,
            alias=arguments.generic_alias,
        )
        print("APPLY" if arguments.apply else "PREVIEW (no changes)")
        print("\n".join(plan))
        return 0
    except InstallError, OSError, ValueError:
        print(
            "Installer refused or failed. Resolve paths, ownership or recovery state privately.",
            file=sys.stderr,
        )
        return 3
    except KeyboardInterrupt:
        print("Installer interrupted; rerun with --apply to recover.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
