"""Bitwarden and Vaultwarden CLI storage backend with volatile session management."""

import atexit
import ctypes
import json
import re
import shutil
import threading
import time
from typing import Any

from ..cache import current_time_step, get_cached_totp, set_cached_totp
from ..enrollment import OtpParameters, generate_totp_code, parse_secret_or_uri
from ..errors import AppError
from ..models import parse_code
from ..processes import run

LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
SESSION_KEY_PATTERN = re.compile(r"^[A-Za-z0-9+/=_-]{20,}$")
DEFAULT_SESSION_TTL = 900.0  # 15 minutes
BITWARDEN_LIST_STDOUT_CAP = 2 * 1024 * 1024  # 2MB stdout capture cap for large enterprise vaults


class BitwardenSessionManager:
    """Thread-safe, volatile in-memory storage for BW_SESSION with memory zeroization."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session_buffer: bytearray | None = None
        self._expiry: float = 0.0

    def set_session(self, session_key: str, ttl: float = DEFAULT_SESSION_TTL) -> None:
        """Store session key in memory and schedule expiration."""
        cleaned = session_key.strip()
        if not cleaned:
            raise AppError(2)
        with self._lock:
            self._wipe_locked()
            raw = cleaned.encode("utf-8")
            self._session_buffer = bytearray(raw)
            self._expiry = time.monotonic() + ttl

    def get_session(self, env: dict[str, str] | None = None) -> str | None:
        """Retrieve active session key, or check env fallback if not expired."""
        with self._lock:
            if self._session_buffer is not None:
                if time.monotonic() < self._expiry:
                    return self._session_buffer.decode("utf-8")
                self._wipe_locked()

        if env and "BW_SESSION" in env:
            candidate = env["BW_SESSION"].strip()
            if candidate:
                return candidate
        return None

    def is_unlocked(self, env: dict[str, str] | None = None) -> bool:
        """Check whether an active, valid session key is present."""
        return self.get_session(env) is not None

    def clear_session(self) -> None:
        """Zeroize memory and invalidate the current session key."""
        with self._lock:
            self._wipe_locked()

    def _wipe_locked(self) -> None:
        """Internal zeroization helper while lock is held."""
        if self._session_buffer is not None:
            buf_len = len(self._session_buffer)
            if buf_len > 0:
                c_arr = (ctypes.c_char * buf_len).from_buffer(self._session_buffer)
                ctypes.memset(c_arr, 0, buf_len)
            self._session_buffer = None
        self._expiry = 0.0

    def unlock(self, password: str, env: dict[str, str], ttl: float = DEFAULT_SESSION_TTL) -> str:
        """Unlock Bitwarden vault using raw master password and cache session key."""
        bw = shutil.which("bw", path=env.get("PATH", ""))
        if not bw:
            raise AppError(3)

        clean_env = child_environment(env)
        # Never pass password on CLI arguments to avoid /proc inspection
        res = run(
            [bw, "unlock", "--raw"],
            env=clean_env,
            timeout=15,
            input_data=password.encode("utf-8"),
            stdout_cap=4096,
            stderr_cap=4096,
        )
        if res.returncode != 0:
            raise AppError(4)

        raw_key = res.stdout.decode("utf-8", errors="replace").strip()
        if not raw_key:
            raise AppError(4)

        self.set_session(raw_key, ttl=ttl)
        return raw_key

    def lock(self, env: dict[str, str]) -> None:
        """Lock the Bitwarden vault and clear local memory."""
        self.clear_session()
        bw = shutil.which("bw", path=env.get("PATH", ""))
        if bw:
            clean_env = child_environment(env)
            try:
                run([bw, "lock"], env=clean_env, timeout=10, stdout_cap=2048)
            except Exception:
                pass


session_manager = BitwardenSessionManager()
atexit.register(session_manager.clear_session)


def child_environment(env: dict[str, str], session_key: str | None = None) -> dict[str, str]:
    """Sanitize environment for child bw processes, injecting BW_SESSION securely."""
    clean = {
        k: v
        for k, v in env.items()
        if not k.startswith("BASH_") and not k.startswith("OP_") and k not in ("BW_SESSION",)
    }
    clean["BW_NO_TELEMETRY"] = "true"

    active_session = session_key or session_manager.get_session(env)
    if active_session:
        clean["BW_SESSION"] = active_session

    return clean


def probe(env: dict[str, str], *, use_cache: bool = True) -> dict[str, Any]:
    """Probe Bitwarden CLI availability, version, and vault status."""
    bw = shutil.which("bw", path=env.get("PATH", ""))
    if not bw:
        return {"state": "missing"}

    version = "unknown"
    try:
        ver_res = run([bw, "--version"], env=child_environment(env), timeout=5, stdout_cap=2048)
        if ver_res.returncode == 0 and ver_res.stdout:
            version = ver_res.stdout.decode("utf-8", errors="replace").strip()
    except Exception:
        pass

    vault_status = "unknown"
    try:
        stat_res = run([bw, "status"], env=child_environment(env), timeout=5, stdout_cap=4096)
        if stat_res.returncode == 0 and stat_res.stdout:
            data = json.loads(stat_res.stdout.decode("utf-8", errors="replace"))
            if isinstance(data, dict):
                vault_status = data.get("status", "unknown")
    except Exception:
        pass

    is_unlocked = vault_status == "unlocked" or session_manager.is_unlocked(env)

    return {
        "state": "available",
        "path": bw,
        "version": version,
        "vault_status": vault_status,
        "unlocked": is_unlocked,
    }


def list_items(env: dict[str, str], search: str | None = None) -> list[dict[str, Any]]:
    """List vault items containing TOTP logins."""
    bw = shutil.which("bw", path=env.get("PATH", ""))
    if not bw:
        raise AppError(3)

    cmd = [bw, "list", "items"]
    if search:
        cmd.extend(["--search", search])

    clean_env = child_environment(env)
    res = run(cmd, env=clean_env, timeout=15, stdout_cap=BITWARDEN_LIST_STDOUT_CAP)
    if res.returncode != 0:
        raise AppError(4)

    try:
        items = json.loads(res.stdout.decode("utf-8", errors="replace"))
        if not isinstance(items, list):
            return []
        # Return only items that contain a login and a configured TOTP seed
        totp_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            login = item.get("login")
            if isinstance(login, dict) and login.get("totp"):
                totp_items.append(item)
        return totp_items
    except Exception:
        raise AppError(4) from None


_bw_list_items = list_items


def bitwarden_records(env: dict[str, str], search: str | None = None) -> list[tuple[str, str]]:
    """Return list of (item_id, display_label) tuples for all TOTP-configured Bitwarden items."""
    items = list_items(env, search=search)
    records = []
    for item in items:
        item_id = item.get("id", "")
        name = item.get("name") or "Unnamed"
        username = item.get("login", {}).get("username")
        label = f"{name} ({username})" if username else name
        records.append((item_id, f"{label} [Bitwarden]"))
    return sorted(records, key=lambda r: r[1].lower())


def bitwarden_code(
    item_id_or_name: str,
    env: dict[str, str],
    timestamp: float | None = None,
) -> str:
    """Retrieve TOTP code for a Bitwarden item, with in-process step caching."""
    if not item_id_or_name:
        raise AppError(2)

    bw = shutil.which("bw", path=env.get("PATH", ""))
    if not bw:
        raise AppError(3)

    step = current_time_step(30, now=timestamp)
    cached = get_cached_totp("bitwarden", item_id_or_name, step)
    if cached is not None:
        return cached

    clean_env = child_environment(env)
    # 1. Try native 'bw get totp <item_id_or_name>'
    res = run(
        [bw, "get", "totp", item_id_or_name],
        env=clean_env,
        timeout=10,
        stdout_cap=2048,
    )
    if res.returncode == 0 and res.stdout:
        raw = res.stdout.decode("utf-8", errors="replace").strip()
        try:
            code = parse_code(raw.encode("ascii"))
            set_cached_totp("bitwarden", item_id_or_name, step, code)
            return code
        except AppError:
            pass

    # 2. Fallback: retrieve item JSON and calculate TOTP in-process
    item_res = run(
        [bw, "get", "item", item_id_or_name],
        env=clean_env,
        timeout=10,
        stdout_cap=65536,
    )
    if item_res.returncode == 0 and item_res.stdout:
        try:
            item_data = json.loads(item_res.stdout.decode("utf-8", errors="replace"))
            totp_val = item_data.get("login", {}).get("totp")
            if totp_val:
                params = parse_secret_or_uri(totp_val)
                code, _ = generate_totp_code(params, timestamp=timestamp)
                set_cached_totp("bitwarden", item_id_or_name, step, code)
                return code
        except Exception:
            pass

    raise AppError(4)


def bitwarden_enroll(
    name: str,
    secret_or_uri: str,
    env: dict[str, str],
    folder_id: str | None = None,
) -> str:
    """Enroll a new OTP credential into the Bitwarden vault."""
    if not name or not secret_or_uri:
        raise AppError(2)

    bw = shutil.which("bw", path=env.get("PATH", ""))
    if not bw:
        raise AppError(3)

    # Validate secret or URI
    parse_secret_or_uri(secret_or_uri)

    item: dict[str, Any] = {
        "type": 1,  # Login item
        "name": name,
        "notes": "Enrolled via otp-local",
        "login": {
            "totp": secret_or_uri,
        },
    }
    if folder_id:
        item["folderId"] = folder_id

    clean_env = child_environment(env)
    payload = json.dumps(item)

    # Use 'bw encode' and 'bw create item'
    res = run(
        [bw, "create", "item"],
        env=clean_env,
        timeout=15,
        input_data=payload.encode("utf-8"),
        stdout_cap=65536,
    )
    if res.returncode != 0:
        raise AppError(4)

    try:
        created = json.loads(res.stdout.decode("utf-8", errors="replace"))
        return created.get("id", "")
    except Exception:
        return ""


def bitwarden_delete(item_id: str, env: dict[str, str]) -> None:
    """Delete an item from the Bitwarden vault and record deletion audit intent."""
    if not item_id:
        raise AppError(2)

    from .. import deletion_audit

    deletion_audit.record("bitwarden")

    bw = shutil.which("bw", path=env.get("PATH", ""))
    if not bw:
        raise AppError(3)

    clean_env = child_environment(env)
    res = run([bw, "delete", "item", item_id], env=clean_env, timeout=10, stdout_cap=2048)
    if res.returncode != 0:
        raise AppError(4)


def collect_tokens(env: dict[str, str]) -> list[OtpParameters]:
    """Collect OtpParameters for all TOTP credentials stored in Bitwarden vault."""
    items = list_items(env)
    tokens: list[OtpParameters] = []
    for item in items:
        totp_raw = item.get("login", {}).get("totp")
        if not totp_raw:
            continue
        try:
            param = parse_secret_or_uri(totp_raw)
            if not param.account and item.get("login", {}).get("username"):
                param.account = item["login"]["username"]
            if not param.issuer and item.get("name"):
                param.issuer = item["name"]
            tokens.append(param)
        except AppError:
            pass
    return tokens
