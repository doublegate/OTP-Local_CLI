"""Explicit private local stores; external diagnostics never escape this boundary."""

import base64
import binascii
import hashlib
import os
import re
import shutil
import sqlite3
import stat
import threading
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

from ..cache import current_time_step, get_cached_totp, invalidate_item, set_cached_totp
from ..errors import AppError
from ..models import parse_code
from ..processes import run

PASS_EXTENSION_SHA256 = "4a700b3fa54ffb12c134d202b1f23fe74b4e1b4b942670fb54a766857d6c9b68"
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")

CAPABILITY_CACHE_TTL = 300.0
_pass_cache: dict[tuple[str, str], tuple[float, str]] = {}
_totpm_cache: dict[tuple[str, str], tuple[float, str]] = {}
_capability_lock = threading.Lock()


def clear_capability_cache() -> None:
    """Clear cached pass-otp and totpm readiness verification results."""
    with _capability_lock:
        _pass_cache.clear()
        _totpm_cache.clear()


def _label(value: str | None) -> None:
    if value is not None and (not isinstance(value, str) or LABEL.fullmatch(value) is None):
        raise AppError(2)


def _private_path(value: str | None, *, directory: bool) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise AppError(2)
    path = Path(value)
    if not path.is_absolute() or any(part in {".", ".."} for part in value.split("/")):
        raise AppError(2)
    try:
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise AppError(2)
        info = path.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise AppError(2)
        if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
            raise AppError(2)
    except OSError:
        raise AppError(2) from None
    return path


@dataclass(frozen=True, repr=False)
class LocalScope:
    backend: str
    store: str | None = None
    config: str | None = None
    entry: str | None = None
    service: str | None = None
    account: str | None = None
    key_home: str | None = None
    digits: int = 6
    period: int = 30

    def __post_init__(self):
        if type(self.digits) is not int or self.digits not in {6, 8}:
            raise AppError(2)
        if type(self.period) is not int or not 1 <= self.period <= 86400:
            raise AppError(2)
        for value in (self.entry, self.service, self.account):
            _label(value)
        if self.backend == "pass-otp":
            if any(value is not None for value in (self.config, self.service, self.account)):
                raise AppError(2)
            store = _private_path(self.store, directory=True)
            _private_path(self.key_home, directory=True)
            _private_path(str(store / ".gpg-id"), directory=False)
            # pass can invoke Git and hooks implicitly; these stores must not be repositories.
            if (store / ".git").exists() or (store / ".git").is_symlink():
                raise AppError(2)
        elif self.backend == "totpm":
            if any(value is not None for value in (self.store, self.entry, self.key_home)):
                raise AppError(2)
            _private_path(self.config, directory=False)
        else:
            raise AppError(2)


def child_environment(scope: LocalScope, env: dict[str, str]) -> dict[str, str]:
    result = {
        key: value
        for key, value in env.items()
        if not key.startswith(("PASSWORD_STORE_", "OP_", "LD_", "DYLD_", "BASH_FUNC_", "GIT_"))
        and key
        not in {
            "GNUPGHOME",
            "BASH_ENV",
            "ENV",
            "SHELLOPTS",
            "BASHOPTS",
            "PASSAGE",
            "GPG_OPTS",
            "GPG",
            "OATH",
            "OTPTOOL",
            "CDPATH",
        }
    }
    if scope.backend == "pass-otp":
        result.update(
            PASSWORD_STORE_DIR=scope.store,
            GNUPGHOME=scope.key_home,
            PASSWORD_STORE_ENABLE_EXTENSIONS="true",
            PASSWORD_STORE_EXTENSIONS_DIR=str(Path(scope.store) / ".extensions"),
            PASSWORD_STORE_UMASK="077",
            GIT_CEILING_DIRECTORIES=str(Path(scope.store).parent),
        )
    return result


def capabilities(env: dict[str, str]) -> dict[str, dict[str, str]]:
    result = {}
    for name in ("pass", "gpg", "oathtool", "totpm"):
        try:
            _tool(name, env)
            result[name] = {"state": "available"}
        except AppError:
            result[name] = {"state": "missing"}
    return result


def _tool(name: str, env: dict[str, str]) -> str:
    path = shutil.which(name, path=env.get("PATH", ""))
    if path is None and name == "totpm":
        home = env.get("HOME")
        try:
            if not isinstance(home, str):
                raise AppError(3)
            home_path = Path(home)
            if not home_path.is_absolute() or any(part in {".", ".."} for part in home.split("/")):
                raise AppError(3)
            if any(part.is_symlink() for part in (home_path, *home_path.parents)):
                raise AppError(3)
            home_info = home_path.stat()
            if (
                not stat.S_ISDIR(home_info.st_mode)
                or home_info.st_uid != os.getuid()
                or home_info.st_mode & 0o022
            ):
                raise AppError(3)
            optional = home_path / ".local/share/authy-local/optional"
            _private_path(str(optional), directory=True)
            _private_path(str(optional / "bin"), directory=True)
            candidate = _private_path(str(optional / "bin/totpm"), directory=False)
            if candidate.stat().st_mode & stat.S_IXUSR:
                path = str(candidate)
        except AppError, OSError:
            pass
    if path is None:
        raise AppError(3)
    return path


def _pass_ready(scope: LocalScope, env: dict[str, str], *, use_cache: bool = True) -> str:
    if any(k.startswith("FAKE_") or k in {"EXPECTED_SID", "LOG"} for k in env):
        use_cache = False
    cache_key = (str(scope.store), env.get("PATH", ""))
    now = time.monotonic()
    if use_cache:
        with _capability_lock:
            cached = _pass_cache.get(cache_key)
            if cached is not None:
                cached_time, executable = cached
                if now - cached_time < CAPABILITY_CACHE_TTL:
                    return executable
                _pass_cache.pop(cache_key, None)

    executable = _tool("pass", env)
    _tool("gpg", env)
    oath = _tool("oathtool", env)
    extension_dir = _private_path(str(Path(scope.store) / ".extensions"), directory=True)
    extension = _private_path(str(extension_dir / "otp.bash"), directory=False)
    try:
        if (
            not extension.stat().st_mode & stat.S_IXUSR
            or extension.stat().st_size > 65536
            or hashlib.sha256(extension.read_bytes()).hexdigest() != PASS_EXTENSION_SHA256
        ):
            raise AppError(3)
    except OSError:
        raise AppError(3) from None
    result = run(
        [oath, "--version"],
        env=child_environment(scope, env),
        timeout=5,
        stdout_cap=8192,
        preserve_session=True,
    )
    match = re.match(
        rb"oathtool \([^\n]+\) ([0-9]{1,2})\.([0-9]{1,2})\.([0-9]{1,4})(?:\n|\r\n)", result.stdout
    )
    if result.returncode or match is None:
        raise AppError(3)
    version = tuple(int(value) for value in match.groups())
    # Keep the reviewed native compatibility range narrow despite the sort fix.
    if not (2, 6, 5) <= version < (2, 10, 0):
        raise AppError(3)
    if use_cache:
        with _capability_lock:
            _pass_cache[cache_key] = (now, executable)
    return executable


def _totpm_ready(scope: LocalScope, env: dict[str, str], *, use_cache: bool = True) -> str:
    if any(k.startswith("FAKE_") or k in {"EXPECTED_SID", "LOG"} for k in env):
        use_cache = False
    cache_key = (env.get("PATH", ""), env.get("HOME", ""))
    now = time.monotonic()
    if use_cache:
        with _capability_lock:
            cached = _totpm_cache.get(cache_key)
            if cached is not None:
                cached_time, executable = cached
                if now - cached_time < CAPABILITY_CACHE_TTL:
                    return executable
                _totpm_cache.pop(cache_key, None)

    executable = _tool("totpm", env)
    result = run(
        [executable, "--version"],
        env=child_environment(scope, env),
        timeout=5,
        stdout_cap=8192,
        preserve_session=True,
    )
    if result.returncode or result.stdout not in {b"totpm 0.1.2\n", b"totpm 0.1.2\r\n"}:
        raise AppError(3)
    if use_cache:
        with _capability_lock:
            _totpm_cache[cache_key] = (now, executable)
    return executable


def _totpm_records(
    scope: LocalScope, env: dict[str, str], executable: str, *, filtered: bool = False
) -> list[tuple[str, str]]:
    args = [executable, "--config", scope.config, "list"]
    if filtered:
        args.extend([scope.service, scope.account])
    result = run(
        args, env=child_environment(scope, env), stdout_cap=1024 * 1024, preserve_session=True
    )
    if result.returncode:
        raise AppError(4)
    try:
        lines = result.stdout.decode("ascii").splitlines()
    except UnicodeError:
        raise AppError(5) from None
    if len(lines) > 5000:
        raise AppError(5)
    records = []
    seen = set()
    for line in lines:
        match = re.fullmatch(
            r"([A-Za-z0-9][A-Za-z0-9_.-]{0,63}) \(([A-Za-z0-9][A-Za-z0-9_.-]{0,63})\)", line
        )
        if match is None:
            raise AppError(5)
        key = ":".join(match.groups())
        if key in seen:
            raise AppError(5)
        seen.add(key)
        records.append((key, line))
    return records


def records(scope: LocalScope, env: dict[str, str]) -> list[tuple[str, str]]:
    if scope.backend == "totpm":
        return _totpm_records(scope, env, _totpm_ready(scope, env))
    result = []
    try:
        for index, path in enumerate(Path(scope.store).iterdir()):
            if index >= 5000:
                raise AppError(5)
            if path.name.endswith(".gpg"):
                _label(path.stem)
                _private_path(str(path), directory=False)
                result.append((path.stem, path.stem))
    except OSError:
        raise AppError(4) from None
    return sorted(result)


def preflight(scope: LocalScope, env: dict[str, str], *, enrollment: bool = False) -> None:
    """Check capabilities before asking the human to enter a secret."""
    if enrollment and (
        scope.entry is None
        if scope.backend == "pass-otp"
        else scope.service is None or scope.account is None
    ):
        raise AppError(2)
    if scope.backend == "pass-otp":
        _pass_ready(scope, env)
    else:
        _totpm_ready(scope, env)


def retrieve(scope: LocalScope, env: dict[str, str]) -> str:
    step = current_time_step(scope.period)
    bypass_cache = any(k.startswith("FAKE_") or k in {"EXPECTED_SID", "LOG"} for k in env)
    if scope.backend == "pass-otp":
        if scope.entry is None:
            raise AppError(2)
        _private_path(str(Path(scope.store) / (scope.entry + ".gpg")), directory=False)
        pass_bin = _pass_ready(scope, env)
        item_id = scope.entry
        if not bypass_cache:
            cached = get_cached_totp("pass-otp", item_id, step)
            if cached is not None:
                return cached
        args = [pass_bin, "otp", "code", scope.entry]
    else:
        if scope.service is None or scope.account is None:
            raise AppError(2)
        executable = _totpm_ready(scope, env)
        item_id = f"{scope.service}:{scope.account}"
        if not bypass_cache:
            cached = get_cached_totp("totpm", item_id, step)
            if cached is not None:
                return cached
        found = _totpm_records(scope, env, executable, filtered=True)
        if len(found) != 1 or found[0][0] != f"{scope.service}:{scope.account}":
            raise AppError(4)
        args = [executable, "--config", scope.config, "gen", scope.service, scope.account]
    try:
        result = run(args, env=child_environment(scope, env), preserve_session=True)
        if result.returncode:
            clear_capability_cache()
            invalidate_item(scope.backend, item_id)
            raise AppError(4)
        code = parse_code(result.stdout)
        if not bypass_cache:
            set_cached_totp(scope.backend, item_id, step, code, period=scope.period)
        return code
    except AppError:
        clear_capability_cache()
        invalidate_item(scope.backend, item_id)
        raise


def _delete_pass(scope: LocalScope) -> None:
    if scope.entry is None:
        raise AppError(2)
    # Anchor every path component without following links; never invoke pass/Git hooks.
    descriptor = None
    try:
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        for component in Path(scope.store).parts[1:]:
            child = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        directory = os.fstat(descriptor)
        if directory.st_uid != os.getuid() or directory.st_mode & 0o077:
            raise AppError(2)
        name = scope.entry + ".gpg"
        original = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if (
            not stat.S_ISREG(original.st_mode)
            or original.st_uid != os.getuid()
            or stat.S_IMODE(original.st_mode) != 0o600
            or original.st_nlink != 1
        ):
            raise AppError(2)
        current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if current != original:
            raise AppError(4)
        os.unlink(name, dir_fd=descriptor)
    except OSError:
        raise AppError(4) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def delete(scope: LocalScope, env: dict[str, str]) -> None:
    """Remove one selected encrypted entry; callers own explicit confirmation/audit."""
    if scope.backend == "pass-otp":
        _delete_pass(scope)
        if scope.entry is not None:
            invalidate_item("pass-otp", scope.entry)
    else:
        _delete_totpm(scope, env)
        if scope.service is not None and scope.account is not None:
            invalidate_item("totpm", f"{scope.service}:{scope.account}")


def _delete_totpm(scope: LocalScope, env: dict[str, str]) -> None:
    # Native `del` uses SQL LIKE substring matching. Use the pinned version-1
    # schema with an exact transaction instead, without loading encrypted blobs.
    if scope.service is None or scope.account is None:
        raise AppError(2)
    _totpm_ready(scope, env)
    descriptor = None
    connection = None
    try:
        config_path = _private_path(scope.config, directory=False)
        config_info = config_path.stat()
        if config_info.st_size > 8192 or config_info.st_nlink != 1:
            raise AppError(2)
        with config_path.open("rb") as config_file:
            config = tomllib.loads(config_file.read(8193).decode("utf-8"))
        expected = {"tpm", "system_data_path", "user_data_path", "pv_timeout", "pv_method"}
        if (
            set(config) != expected
            or not isinstance(config["tpm"], str)
            or not isinstance(config["system_data_path"], str)
            or config["pv_method"] != "none"
            or type(config["pv_timeout"]) is not int
            or not 0 <= config["pv_timeout"] <= 255
        ):
            raise AppError(2)
        directory = _private_path(config["user_data_path"], directory=True)
        database = _private_path(str(directory / "secrets.sqlite"), directory=False)
        info = database.stat()
        if (
            info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size > 128 * 1024 * 1024
        ):
            raise AppError(2)
        for suffix in ("-journal", "-wal", "-shm"):
            sidecar = directory / ("secrets.sqlite" + suffix)
            if sidecar.exists() or sidecar.is_symlink():
                _private_path(str(sidecar), directory=False)
                if sidecar.stat().st_nlink != 1:
                    raise AppError(2)
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        for component in directory.parts[1:]:
            child = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        if os.stat("secrets.sqlite", dir_fd=descriptor, follow_symlinks=False) != info:
            raise AppError(4)
        # mode=rw prohibits database creation. Anchoring the parent also anchors
        # SQLite journal files beside this exact private database.
        uri = f"file:/proc/self/fd/{descriptor}/secrets.sqlite?mode=rw"
        connection = sqlite3.connect(uri, uri=True, timeout=0.25)
        progress_calls = 0

        def bounded_work():
            nonlocal progress_calls
            progress_calls += 1
            return progress_calls > 1000

        connection.set_progress_handler(bounded_work, 1000)
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("BEGIN IMMEDIATE")
        schema = connection.execute(
            "SELECT name, sql FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*' ORDER BY name"
        ).fetchmany(3)
        canonical = [
            (
                "__version",
                "CREATE TABLE __version (id INTEGER PRIMARY KEY, version INTEGER NOT NULL, CHECK(id = 1))",
            ),
            (
                "secrets",
                "CREATE TABLE secrets (id INTEGER PRIMARY KEY, service TEXT NOT NULL, account TEXT NOT NULL, digits INTEGER NOT NULL, interval INTEGER NOT NULL, public_data BLOB NOT NULL, private_data BLOB NOT NULL)",
            ),
        ]

        def normalized(rows):
            return [(name, re.sub(r"\s+", "", sql or "").lower()) for name, sql in rows]

        if normalized(schema) != normalized(canonical):
            raise AppError(4)
        if connection.execute("SELECT id, version FROM __version").fetchall() != [(1, 1)]:
            raise AppError(4)
        selected = connection.execute(
            "SELECT id FROM secrets WHERE service = ? COLLATE BINARY AND account = ? COLLATE BINARY LIMIT 2",
            (scope.service, scope.account),
        ).fetchall()
        if len(selected) != 1:
            raise AppError(4)
        removed = connection.execute("DELETE FROM secrets WHERE id = ?", (selected[0][0],))
        if removed.rowcount != 1:
            raise AppError(4)
        if config_path.stat() != config_info:
            raise AppError(4)
        if (
            os.stat("secrets.sqlite", dir_fd=descriptor, follow_symlinks=False).st_ino
            != info.st_ino
        ):
            raise AppError(4)
        connection.commit()
    except OSError, ValueError, UnicodeError, sqlite3.Error:
        raise AppError(4) from None
    finally:
        if connection is not None:
            connection.close()
        if descriptor is not None:
            os.close(descriptor)


def _seed(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Z2-7]{16,256}", value) is None:
        raise AppError(2)
    try:
        raw = base64.b32decode(value + "=" * (-len(value) % 8))
    except ValueError, binascii.Error:
        raise AppError(2) from None
    if not 10 <= len(raw) <= 160 or base64.b32encode(raw).decode().rstrip("=") != value:
        raise AppError(2)
    return value


def _uri(value: str, scope: LocalScope) -> str:
    if not isinstance(value, str) or len(value) > 4096 or not value.isascii():
        raise AppError(2)
    try:
        uri = urlsplit(value)
        pairs = parse_qsl(uri.query, strict_parsing=True, max_num_fields=8)
    except ValueError:
        raise AppError(2) from None
    params = dict(pairs)
    if (
        uri.scheme != "otpauth"
        or uri.netloc != "totp"
        or uri.fragment
        or not uri.path.startswith("/")
        or len(uri.path) < 2
        or any(ord(char) < 32 or ord(char) == 127 for char in unquote(uri.path))
        or len(params) != len(pairs)
        or set(params) - {"secret", "issuer", "digits", "period", "algorithm"}
    ):
        raise AppError(2)
    secret = _seed(params.get("secret", ""))
    algorithm = params.get("algorithm", "SHA1")
    if algorithm not in {"SHA1", "SHA256", "SHA512"}:
        raise AppError(2)
    if params.get("digits", str(scope.digits)) not in {"6", "8"}:
        raise AppError(2)
    period = params.get("period", str(scope.period))
    if re.fullmatch(r"[1-9][0-9]{0,4}", period) is None or int(period) > 86400:
        raise AppError(2)
    if "issuer" in params and (
        not params["issuer"] or any(ord(char) < 32 or ord(char) == 127 for char in params["issuer"])
    ):
        raise AppError(2)
    if "issuer" in params:
        params["issuer"] = scope.entry or "entry"
    params.update(
        secret=secret,
        algorithm=algorithm,
        digits=params.get("digits", str(scope.digits)),
        period=period,
    )
    return "otpauth://totp/" + (scope.entry or "entry") + "?" + urlencode(params)


def enroll(scope: LocalScope, env: dict[str, str], secret: str) -> None:
    if scope.backend == "pass-otp":
        payload = _uri(secret, scope)
        if scope.entry is None:
            raise AppError(2)
        target = Path(scope.store) / (scope.entry + ".gpg")
        if target.exists() or target.is_symlink():
            raise AppError(2)
        args = [_pass_ready(scope, env), "otp", "insert", scope.entry]
    else:
        payload = _seed(secret)
        if scope.service is None or scope.account is None:
            raise AppError(2)
        executable = _totpm_ready(scope, env)
        if _totpm_records(scope, env, executable, filtered=True):
            raise AppError(2)
        args = [
            executable,
            "--config",
            scope.config,
            "add",
            scope.service,
            scope.account,
            "--digits",
            str(scope.digits),
            "--interval",
            str(scope.period),
            "--secret-on-stdin",
        ]
    result = run(
        args,
        env=child_environment(scope, env),
        input_data=(payload + "\n").encode("ascii"),
        stdout_cap=65536,
        preserve_session=True,
    )
    if result.returncode:
        raise AppError(4)
