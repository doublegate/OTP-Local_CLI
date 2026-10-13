"""Hardware token backends: YubiKey (ykman OATH) and TPM 2.0 (tpm2-totp)."""

import shutil

from ..errors import AppError
from ..models import parse_code
from ..processes import run


def probe_hardware(env: dict[str, str]) -> dict[str, dict[str, str]]:
    """Probe hardware token tools without running interactive sessions."""
    result = {}
    ykman = shutil.which("ykman", path=env.get("PATH", ""))
    result["yubikey"] = {"state": "available", "path": ykman} if ykman else {"state": "missing"}

    tpm2_totp = shutil.which("tpm2-totp", path=env.get("PATH", ""))
    result["tpm2-totp"] = (
        {"state": "available", "path": tpm2_totp} if tpm2_totp else {"state": "missing"}
    )
    return result


def yubikey_records(env: dict[str, str]) -> list[tuple[str, str]]:
    """List OATH accounts from connected YubiKey."""
    ykman = shutil.which("ykman", path=env.get("PATH", ""))
    if not ykman:
        raise AppError(3)
    clean = {k: v for k, v in env.items() if not k.startswith("BASH_")}
    result = run(
        [ykman, "oath", "accounts", "list"],
        env=clean,
        timeout=10,
        stdout_cap=65536,
    )
    if result.returncode != 0:
        raise AppError(4)
    lines = [
        line.strip()
        for line in result.stdout.decode("utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    return [(name, f"{name} [YubiKey]") for name in lines]


def yubikey_code(name: str, env: dict[str, str]) -> str:
    """Generate TOTP code from connected YubiKey for specified account name."""
    ykman = shutil.which("ykman", path=env.get("PATH", ""))
    if not ykman:
        raise AppError(3)
    clean = {k: v for k, v in env.items() if not k.startswith("BASH_")}
    result = run(
        [ykman, "oath", "accounts", "code", "-s", name],
        env=clean,
        timeout=15,
        stdout_cap=64,
    )
    if result.returncode != 0:
        raise AppError(4)
    code = result.stdout.decode("ascii", errors="replace").strip()
    return parse_code(code.encode("ascii"))


def tpm2_totp_records(env: dict[str, str]) -> list[tuple[str, str]]:
    """List sealed TOTP keys from Linux TPM 2.0."""
    tpm2_totp = shutil.which("tpm2-totp", path=env.get("PATH", ""))
    if not tpm2_totp:
        raise AppError(3)
    return [("default", "TPM 2.0 Sealed TOTP [Hardware]")]


def tpm2_totp_code(name: str, env: dict[str, str]) -> str:
    """Generate TOTP code from Linux TPM 2.0 NVRAM index."""
    tpm2_totp = shutil.which("tpm2-totp", path=env.get("PATH", ""))
    if not tpm2_totp:
        raise AppError(3)
    clean = {k: v for k, v in env.items() if not k.startswith("BASH_")}
    result = run(
        [tpm2_totp, "show"],
        env=clean,
        timeout=15,
        stdout_cap=64,
    )
    if result.returncode != 0:
        raise AppError(4)
    code = result.stdout.decode("ascii", errors="replace").strip()
    return parse_code(code.encode("ascii"))
