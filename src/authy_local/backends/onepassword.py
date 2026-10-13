"""Only version probes and explicitly scoped OTP retrieval are allowed."""

import re
import shutil
import threading
import time

from ..cache import current_time_step, get_cached_totp, invalidate_item, set_cached_totp
from ..errors import AppError
from ..models import Scope, parse_code
from ..processes import run

PROBE_CACHE_TTL = 300.0
_probe_cache: dict[str, tuple[float, dict[str, str]]] = {}
_probe_lock = threading.Lock()


def clear_probe_cache() -> None:
    """Clear cached 1Password capability probe results."""
    with _probe_lock:
        _probe_cache.clear()


def foreign_auth(env: dict[str, str]) -> bool:
    return any(
        name in {"OP_SERVICE_ACCOUNT_TOKEN", "OP_CONNECT_TOKEN", "OP_CONNECT_HOST"}
        or name == "OP_SESSION"
        or name.startswith("OP_SESSION_")
        for name in env
    )


def child_environment(env: dict[str, str]) -> dict[str, str]:
    # Retain desktop IPC/locale, but no caller-controlled op defaults/auth modes.
    result = {key: value for key, value in env.items() if not key.startswith("OP_")}
    result["OP_BIOMETRIC_UNLOCK_ENABLED"] = "true"
    return result


def probe(env: dict[str, str], *, use_cache: bool = True) -> dict[str, str]:
    if any(k.startswith("FAKE_") or k in {"EXPECTED_SID", "LOG"} for k in env):
        use_cache = False
    cache_key = env.get("PATH", "")
    now = time.monotonic()
    if use_cache:
        with _probe_lock:
            cached = _probe_cache.get(cache_key)
            if cached is not None:
                cached_time, capability = cached
                if now - cached_time < PROBE_CACHE_TTL:
                    return dict(capability)
                _probe_cache.pop(cache_key, None)

    executable = shutil.which("op", path=env.get("PATH", ""))
    if executable is None:
        return {"state": "missing"}
    try:
        result = run(
            [executable, "--version"],
            env=child_environment(env),
            timeout=5,
            stdout_cap=8192,
            stderr_cap=8192,
            preserve_session=True,
        )
        match = re.fullmatch(rb"2\.([0-9]{1,4})\.([0-9]{1,4})\r?\n?", result.stdout)
        if result.returncode == 0 and match and int(match[1]) >= 39:
            capability = {
                "state": "available",
                "path": executable,
                "version": result.stdout.strip().decode("ascii"),
            }
            if use_cache:
                with _probe_lock:
                    _probe_cache[cache_key] = (now, capability)
            return dict(capability)
    except AppError as error:
        if error.exit_code == 130:
            raise
    return {"state": "unknown", "path": executable}


def retrieve(scope: Scope, env: dict[str, str]) -> str:
    if foreign_auth(env):
        raise AppError(3)
    capability = probe(env)
    if capability["state"] != "available":
        raise AppError(3)
    bypass_cache = any(k.startswith("FAKE_") or k in {"EXPECTED_SID", "LOG"} for k in env)
    step = current_time_step(30)
    if not bypass_cache:
        cached = get_cached_totp("onepassword", scope.item, step)
        if cached is not None:
            return cached
    try:
        result = run(
            [
                capability["path"],
                "item",
                "get",
                scope.item,
                "--account",
                scope.account,
                "--vault",
                scope.vault,
                "--otp",
                "--format",
                "human-readable",
                "--no-color",
                "--cache=false",
                "--debug=false",
            ],
            env=child_environment(env),
            preserve_session=True,
        )
        if result.returncode != 0:
            clear_probe_cache()
            invalidate_item("onepassword", scope.item)
            raise AppError(4)
        code = parse_code(result.stdout)
        if not bypass_cache:
            set_cached_totp("onepassword", scope.item, step, code, period=30)
        return code
    except AppError:
        clear_probe_cache()
        invalidate_item("onepassword", scope.item)
        raise


def enroll(
    account: str,
    vault: str,
    title: str,
    otp_uri: str,
    env: dict[str, str],
    *,
    item_id: str | None = None,
    tags: str = "OTP",
) -> str:
    """Create or update a 1Password Login item with an OTP field and 'OTP' tag."""
    import json

    if foreign_auth(env):
        raise AppError(3)
    capability = probe(env)
    if capability["state"] != "available":
        raise AppError(3)

    Scope("a" * 26, account, vault)
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise AppError(2)
    if not isinstance(otp_uri, str) or not otp_uri.startswith("otpauth://"):
        raise AppError(2)

    executable = capability["path"]
    clean_env = child_environment(env)

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    if "OTP" not in tag_list:
        tag_list.append("OTP")
    tags_arg = ",".join(tag_list)

    if item_id:
        Scope(item_id, account, vault)
        cmd = [
            executable,
            "item",
            "edit",
            item_id,
            "--vault",
            vault,
            "--account",
            account,
            "--tags",
            tags_arg,
            f"one-time password[otp]={otp_uri}",
            "--format",
            "json",
        ]
    else:
        cmd = [
            executable,
            "item",
            "create",
            "--category",
            "Login",
            "--title",
            title.strip(),
            "--vault",
            vault,
            "--account",
            account,
            "--tags",
            tags_arg,
            f"one-time password[otp]={otp_uri}",
            "--format",
            "json",
        ]

    result = run(
        cmd,
        env=clean_env,
        timeout=30,
        stdout_cap=65536,
        preserve_session=True,
    )
    if result.returncode != 0:
        raise AppError(4)

    try:
        data = json.loads(result.stdout)
        return data.get("id", item_id or title)
    except Exception:
        return item_id or title
