"""Private scope defaults only; credentials and item inventories are never persisted."""

import json
import os
import re
import stat
import tempfile
from pathlib import Path

from authy_local.errors import AppError

_FIELDS = {
    "onepassword": {"account", "vault"},
    "pass-otp": {"store", "key_home"},
    "totpm": {"config"},
}
_LIMIT = 8192


def valid_tag(value: object) -> bool:
    """Accept one bounded metadata tag, or blank to disable the filter."""
    return (
        isinstance(value, str)
        and len(value) <= 64
        and not value.startswith("-")
        and "," not in value
        and all(32 <= ord(char) <= 126 for char in value)
    )


def _validate(value: object) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict) or not value.keys() <= _FIELDS.keys():
        raise AppError(2)
    result = {}
    for backend, scope in value.items():
        allowed = _FIELDS[backend] | ({"tag"} if backend == "onepassword" else set())
        if not isinstance(scope, dict) or not _FIELDS[backend] <= scope.keys() <= allowed:
            raise AppError(2)
        for name, field in scope.items():
            if name == "tag":
                if not valid_tag(field):
                    raise AppError(2)
                continue
            if not isinstance(field, str):
                raise AppError(2)
            if backend == "onepassword":
                if re.fullmatch(r"[A-Za-z0-9]{26}", field) is None:
                    raise AppError(2)
            elif (
                not field.startswith("/")
                or len(field) > 1024
                or any(ord(char) < 32 or ord(char) == 127 for char in field)
                or ".." in Path(field).parts
            ):
                raise AppError(2)
        result[backend] = dict(scope)
    return result


def _check_path(path: Path, mode: int | None = None, directory: bool = True) -> bool:
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise AppError(3)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        not kind(info.st_mode)
        or info.st_uid != os.getuid()
        or (info.st_mode & 0o777 != mode if mode is not None else info.st_mode & 0o022)
    ):
        raise AppError(3)
    return True


def _location(home: Path | None, create: bool = False) -> Path:
    root = Path.home() if home is None else Path(home)
    if not root.is_absolute() or ".." in root.parts:
        raise AppError(3)
    if not _check_path(root):
        raise AppError(3)
    config = root / ".config"
    private = config / "authy-local"
    for directory, mode in ((config, None), (private, 0o700)):
        if not _check_path(directory, mode) and create:
            directory.mkdir(mode=0o700)
            _check_path(directory, mode)
    path = private / "tui-profiles.json"
    _check_path(path, 0o600, directory=False)
    return path


def _object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise AppError(2)
        result[key] = value
    return result


def load(home: Path | None = None) -> dict[str, dict[str, str]]:
    """Load complete scopes from a bounded private file, without native operations."""
    try:
        path = _location(home)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return {}
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o777 != 0o600
            ):
                raise AppError(3)
            raw = source.read(_LIMIT + 1)
        if len(raw) > _LIMIT:
            raise AppError(2)
        return _validate(json.loads(raw, object_pairs_hook=_object))
    except ValueError, UnicodeError, RecursionError:
        raise AppError(2) from None
    except OSError:
        raise AppError(3) from None


def save(profiles: dict[str, dict[str, str]], home: Path | None = None) -> None:
    """Atomically replace private scope defaults; refuse unsafe preexisting paths."""
    data = (json.dumps(_validate(profiles), ensure_ascii=True) + "\n").encode()
    if len(data) > _LIMIT:
        raise AppError(2)
    temporary = None
    try:
        path = _location(home, create=True)
        fd, name = tempfile.mkstemp(prefix=".tui-profiles-", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(fd, "wb") as target:
            os.fchmod(target.fileno(), 0o600)
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        _location(home)
        os.replace(temporary, path)
    except OSError:
        raise AppError(3) from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                raise AppError(3) from None
