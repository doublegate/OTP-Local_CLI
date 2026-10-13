"""Durable coarse deletion-intent records, without account or entry identifiers."""

import fcntl
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

from authy_local.errors import AppError

_LIMIT = 1024 * 1024


def _directory(path: Path, private: bool = False, create: bool = False) -> None:
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise AppError(3)
    if create:
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or (info.st_mode & 0o777 != 0o700 if private else info.st_mode & 0o022)
    ):
        raise AppError(3)


def _file(info: os.stat_result, incoming: int) -> None:
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o777 != 0o600
        or info.st_nlink != 1
        or info.st_size + incoming > _LIMIT
    ):
        raise AppError(3)


def record(backend: str, home: Path | None = None) -> None:
    """Synchronously audit one confirmed local deletion attempt; errors forbid deletion."""
    if backend not in ("pass-otp", "totpm", "keychain", "dpapi", "fido2", "bitwarden"):
        raise AppError(2)
    try:
        root = Path.home() if home is None else Path(home)
        if not root.is_absolute() or ".." in root.parts:
            raise AppError(3)
        _directory(root)
        local = root / ".local"
        state = local / "state"
        private = state / "authy-local"
        for directory in (local, state, private):
            _directory(directory, private=directory == private, create=True)
        path = private / "deletions.jsonl"
        data = (
            json.dumps(
                {
                    "time": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "uid": os.getuid(),
                    "action": "delete-attempt",
                    "backend": backend,
                    "scope": "one-confirmed-local-entry",
                },
                separators=(",", ":"),
            )
            + "\n"
        ).encode("ascii")
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK
        fd = os.open(path, flags, 0o600)
        try:
            _file(os.fstat(fd), len(data))
            fcntl.flock(fd, fcntl.LOCK_EX)
            _file(os.fstat(fd), len(data))
            remaining = memoryview(data)
            while remaining:
                written = os.write(fd, remaining)
                if written <= 0:
                    raise AppError(3)
                remaining = remaining[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        directory_fd = os.open(private, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError, ValueError, TypeError:
        raise AppError(3) from None
