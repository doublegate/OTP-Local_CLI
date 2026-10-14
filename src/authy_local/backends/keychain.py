"""Apple macOS Keychain & Secure Enclave token backend."""

import json
import platform
import re
import shutil
import sys
from pathlib import Path

from ..enrollment import OtpParameters, generate_totp_code
from ..errors import AppError
from ..processes import run
from ..security import secure_zero

KEYCHAIN_SERVICE = "otp-local"
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")


def _index_path(env: dict[str, str]) -> Path:
    base = env.get("XDG_STATE_HOME")
    if base:
        directory = Path(base) / "authy-local"
    else:
        directory = Path.home() / ".local/state/authy-local"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        pass
    return directory / "keychain_index.json"


def _read_index(env: dict[str, str]) -> list[str]:
    path = _index_path(env)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and all(isinstance(x, str) for x in data):
            return data
    except Exception:
        pass
    return []


def _write_index(accounts: list[str], env: dict[str, str]) -> None:
    path = _index_path(env)
    temp = path.with_suffix(".tmp")
    payload = json.dumps(sorted(list(set(accounts))), indent=2) + "\n"
    temp.write_text(payload, encoding="utf-8")
    try:
        temp.chmod(0o600)
        temp.replace(path)
    except OSError:
        pass


def has_secure_enclave() -> bool:
    """Detect presence of Apple Secure Enclave hardware co-processor."""
    if sys.platform != "darwin":
        return False
    if platform.machine() == "arm64":
        return True
    try:
        proc = run(["system_profiler", "SPiBridgeDataType"], timeout=3, stdout_cap=2048)
        if b"T2" in proc.stdout or b"Apple T2" in proc.stdout:
            return True
    except Exception:
        pass
    return False


def probe(env: dict[str, str]) -> dict[str, str | bool]:
    """Probe availability of macOS Keychain and Secure Enclave."""
    if sys.platform != "darwin":
        return {"state": "not-applicable"}
    security = shutil.which("security", path=env.get("PATH", ""))
    if not security:
        return {"state": "missing"}
    return {
        "state": "available",
        "path": security,
        "enclave": has_secure_enclave(),
    }


def keychain_records(env: dict[str, str]) -> list[tuple[str, str]]:
    """List enrolled OTP accounts from macOS Keychain index."""
    security = shutil.which("security", path=env.get("PATH", ""))
    if not security:
        raise AppError(3)
    accounts = _read_index(env)
    tag = "Keychain/SecureEnclave" if has_secure_enclave() else "Keychain"
    return [(acct, f"{acct} [{tag}]") for acct in accounts]


def keychain_code(account: str, env: dict[str, str], timestamp: float | None = None) -> str:
    """Retrieve secret from macOS Keychain, generate RFC 6238 TOTP, and zeroize memory."""
    if not account or not LABEL.fullmatch(account):
        raise AppError(2)
    security = shutil.which("security", path=env.get("PATH", ""))
    if not security:
        raise AppError(3)

    clean = {k: v for k, v in env.items() if not k.startswith("BASH_")}
    result = run(
        [security, "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", account, "-w"],
        env=clean,
        timeout=10,
        stdout_cap=1024,
    )
    if result.returncode != 0:
        raise AppError(4)

    raw_secret_buf = bytearray(result.stdout.strip())
    if not raw_secret_buf:
        raise AppError(5)

    raw_secret = raw_secret_buf.decode("utf-8", errors="replace")
    try:
        params = OtpParameters(secret=raw_secret, account=account)
        code, _ = generate_totp_code(params, timestamp=timestamp)
        return code
    finally:
        raw_secret = ""
        secure_zero(raw_secret_buf)


def keychain_enroll(account: str, secret: str, env: dict[str, str]) -> None:
    """Save an OTP secret into macOS Keychain under service 'otp-local'."""
    if not account or not LABEL.fullmatch(account):
        raise AppError(2)
    if not secret:
        raise AppError(2)
    security = shutil.which("security", path=env.get("PATH", ""))
    if not security:
        raise AppError(3)

    clean = {k: v for k, v in env.items() if not k.startswith("BASH_")}
    result = run(
        [
            security,
            "add-generic-password",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            account,
            "-w",
            secret,
            "-U",
        ],
        env=clean,
        timeout=10,
        stdout_cap=1024,
    )
    if result.returncode != 0:
        raise AppError(4)

    accounts = _read_index(env)
    if account not in accounts:
        accounts.append(account)
        _write_index(accounts, env)


def keychain_delete(account: str, env: dict[str, str]) -> None:
    """Delete an OTP secret from macOS Keychain."""
    if not account or not LABEL.fullmatch(account):
        raise AppError(2)
    security = shutil.which("security", path=env.get("PATH", ""))
    if not security:
        raise AppError(3)

    clean = {k: v for k, v in env.items() if not k.startswith("BASH_")}
    result = run(
        [security, "delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", account],
        env=clean,
        timeout=10,
        stdout_cap=1024,
    )
    if result.returncode != 0:
        raise AppError(4)

    accounts = _read_index(env)
    if account in accounts:
        accounts.remove(account)
        _write_index(accounts, env)
