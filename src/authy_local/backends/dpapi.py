"""Microsoft Windows Data Protection API (DPAPI) and Credential Manager token backend."""

import ctypes
import hashlib
import json
import os
import re
import sys
from ctypes import wintypes
from pathlib import Path

from ..enrollment import OtpParameters, generate_totp_code
from ..errors import AppError

CREDENTIAL_TARGET_PREFIX = "OTP-Local:"
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
CRYPTPROTECT_UI_FORBIDDEN = 0x1
CRYPTPROTECT_LOCAL_MACHINE = 0x4
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


PCREDENTIALW = ctypes.POINTER(CREDENTIALW)

_crypt32_override = None
_advapi32_override = None
_kernel32_override = None


def _get_crypt32():
    if _crypt32_override is not None:
        return _crypt32_override
    if sys.platform != "win32":
        raise AppError(3)
    return ctypes.windll.crypt32


def _get_advapi32():
    if _advapi32_override is not None:
        return _advapi32_override
    if sys.platform != "win32":
        raise AppError(3)
    return ctypes.windll.advapi32


def _get_kernel32():
    if _kernel32_override is not None:
        return _kernel32_override
    if sys.platform != "win32":
        raise AppError(3)
    return ctypes.windll.kernel32


def _index_path(env: dict[str, str]) -> Path:
    base = env.get("LOCALAPPDATA") or env.get("XDG_STATE_HOME")
    if base:
        directory = Path(base) / "authy-local"
    else:
        directory = Path.home() / ".local/state/authy-local"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        pass
    return directory / "dpapi_index.json"


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


def _get_entropy(env: dict[str, str]) -> bytes:
    """Derive 32-byte application-specific salt from machine GUID and user identity."""
    override = env.get("OTP_LOCAL_DPAPI_ENTROPY")
    if override:
        return hashlib.sha256(override.encode("utf-8")).digest()

    guid = ""
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
            ) as key:
                guid = str(winreg.QueryValueEx(key, "MachineGuid")[0])
        except Exception:
            pass

    user = env.get("USERNAME") or env.get("USER") or ""
    domain = env.get("USERDOMAIN") or ""
    raw = f"OTP-Local-DPAPI-Entropy:{guid}:{domain}:{user}".encode("utf-8")
    return hashlib.sha256(raw).digest()


def has_windows_hello() -> bool:
    """Detect presence or configuration of Windows Hello PIN or biometrics."""
    if sys.platform != "win32":
        return False
    if os.environ.get("OTP_LOCAL_WINDOWS_HELLO") == "1":
        return True
    try:
        import winreg

        for path in (
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\LogonUI\NgcPin",
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon",
        ):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path):
                    return True
            except OSError:
                continue
    except Exception:
        pass
    return False


def probe(env: dict[str, str]) -> dict[str, str | bool]:
    """Probe availability of Windows DPAPI."""
    if sys.platform != "win32" and _crypt32_override is None:
        return {"state": "not-applicable"}
    try:
        _get_crypt32()
        return {
            "state": "available",
            "hello": has_windows_hello(),
        }
    except Exception:
        return {"state": "missing"}


def probe_credman(env: dict[str, str]) -> dict[str, str]:
    """Probe availability of Windows Credential Manager."""
    if sys.platform != "win32" and _advapi32_override is None:
        return {"state": "not-applicable"}
    try:
        _get_advapi32()
        return {"state": "available"}
    except Exception:
        return {"state": "missing"}


def dpapi_encrypt(
    plaintext: bytes,
    entropy: bytes | None = None,
    description: str = "OTP-Local Secret",
) -> bytes:
    """Encrypt raw bytes using CryptProtectData with application entropy."""
    crypt32 = _get_crypt32()
    kernel32 = _get_kernel32()

    in_buf = ctypes.create_string_buffer(plaintext)
    data_in = DATA_BLOB(len(plaintext), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    data_out = DATA_BLOB()
    p_data_out = ctypes.pointer(data_out)

    p_entropy = None
    if entropy:
        ent_buf = ctypes.create_string_buffer(entropy)
        entropy_blob = DATA_BLOB(
            len(entropy), ctypes.cast(ent_buf, ctypes.POINTER(ctypes.c_char))
        )
        p_entropy = ctypes.pointer(entropy_blob)

    success = crypt32.CryptProtectData(
        ctypes.pointer(data_in),
        description,
        p_entropy,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        p_data_out,
    )
    if not success:
        raise AppError(4)

    result_blob = p_data_out.contents
    try:
        ciphertext = ctypes.string_at(result_blob.pbData, result_blob.cbData)
        return bytes(ciphertext)
    finally:
        if result_blob.pbData:
            kernel32.LocalFree(result_blob.pbData)


def dpapi_decrypt(ciphertext: bytes, entropy: bytes | None = None) -> bytes:
    """Decrypt DPAPI ciphertext using CryptUnprotectData with application entropy."""
    crypt32 = _get_crypt32()
    kernel32 = _get_kernel32()

    in_buf = ctypes.create_string_buffer(ciphertext)
    data_in = DATA_BLOB(len(ciphertext), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    data_out = DATA_BLOB()
    p_data_out = ctypes.pointer(data_out)

    p_entropy = None
    if entropy:
        ent_buf = ctypes.create_string_buffer(entropy)
        entropy_blob = DATA_BLOB(
            len(entropy), ctypes.cast(ent_buf, ctypes.POINTER(ctypes.c_char))
        )
        p_entropy = ctypes.pointer(entropy_blob)

    success = crypt32.CryptUnprotectData(
        ctypes.pointer(data_in),
        None,
        p_entropy,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        p_data_out,
    )
    if not success:
        raise AppError(4)

    result_blob = p_data_out.contents
    try:
        plaintext = ctypes.string_at(result_blob.pbData, result_blob.cbData)
        ctypes.memset(result_blob.pbData, 0, result_blob.cbData)
        return bytes(plaintext)
    finally:
        if result_blob.pbData:
            kernel32.LocalFree(result_blob.pbData)


def credman_write(target_name: str, blob: bytes, comment: str = "") -> None:
    """Write encrypted blob to Windows Credential Manager."""
    advapi32 = _get_advapi32()

    blob_buf = ctypes.create_string_buffer(blob)
    cred = CREDENTIALW()
    cred.Flags = 0
    cred.Type = CRED_TYPE_GENERIC
    cred.TargetName = target_name
    cred.Comment = comment
    cred.CredentialBlobSize = len(blob)
    cred.CredentialBlob = ctypes.cast(blob_buf, ctypes.POINTER(ctypes.c_char))
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE
    cred.AttributeCount = 0
    cred.Attributes = None
    cred.TargetAlias = None
    cred.UserName = None

    success = advapi32.CredWriteW(ctypes.pointer(cred), 0)
    if not success:
        raise AppError(4)


def credman_read(target_name: str) -> bytes:
    """Read encrypted blob from Windows Credential Manager."""
    advapi32 = _get_advapi32()

    p_cred = PCREDENTIALW()
    p_cred_ptr = ctypes.pointer(p_cred)
    success = advapi32.CredReadW(target_name, CRED_TYPE_GENERIC, 0, p_cred_ptr)
    result_cred = p_cred_ptr.contents
    if not success or not result_cred:
        raise AppError(4)

    try:
        cred = result_cred.contents
        blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        return bytes(blob)
    finally:
        advapi32.CredFree(result_cred)


def credman_delete(target_name: str) -> None:
    """Delete credential from Windows Credential Manager."""
    advapi32 = _get_advapi32()
    advapi32.CredDeleteW(target_name, CRED_TYPE_GENERIC, 0)


def credman_list(prefix: str = CREDENTIAL_TARGET_PREFIX) -> list[str]:
    """Enumerate credential targets matching prefix from Windows Credential Manager."""
    advapi32 = _get_advapi32()

    count = wintypes.DWORD()
    p_count = ctypes.pointer(count)
    p_p_creds = ctypes.POINTER(PCREDENTIALW)()
    p_creds_out = ctypes.pointer(p_p_creds)
    filter_str = f"{prefix}*"
    success = advapi32.CredEnumerateW(
        filter_str, 0, p_count, p_creds_out
    )
    result_creds = p_creds_out.contents
    if not success or not result_creds:
        return []

    targets = []
    try:
        for i in range(p_count.contents.value):
            cred_ptr = result_creds[i]
            if cred_ptr:
                cred = cred_ptr.contents
                if cred.TargetName:
                    targets.append(cred.TargetName)
        return targets
    finally:
        advapi32.CredFree(result_creds)


def dpapi_records(env: dict[str, str]) -> list[tuple[str, str]]:
    """List enrolled OTP accounts from Windows Credential Manager / index."""
    accounts = []
    try:
        targets = credman_list(CREDENTIAL_TARGET_PREFIX)
        accounts = [
            t[len(CREDENTIAL_TARGET_PREFIX) :]
            for t in targets
            if t.startswith(CREDENTIAL_TARGET_PREFIX)
        ]
    except Exception:
        accounts = _read_index(env)
    if not accounts:
        accounts = _read_index(env)
    tag = "DPAPI/Hello" if has_windows_hello() else "DPAPI"
    return [(acct, f"{acct} [{tag}]") for acct in sorted(list(set(accounts)))]


def dpapi_code(account: str, env: dict[str, str], timestamp: float | None = None) -> str:
    """Retrieve DPAPI-encrypted secret from Windows Credential Manager, generate TOTP, and zeroize."""
    if not account or not LABEL.fullmatch(account):
        raise AppError(2)
    target = f"{CREDENTIAL_TARGET_PREFIX}{account}"
    try:
        ciphertext = credman_read(target)
    except AppError:
        raise AppError(4) from None

    raw_secret_bytes = dpapi_decrypt(ciphertext, entropy=_get_entropy(env))
    if not raw_secret_bytes:
        raise AppError(5)

    raw_secret = raw_secret_bytes.decode("utf-8", errors="replace").strip()
    try:
        params = OtpParameters(secret=raw_secret, account=account)
        code, _ = generate_totp_code(params, timestamp=timestamp)
        return code
    finally:
        raw_secret = ""
        if isinstance(raw_secret_bytes, (bytearray, bytes)):
            raw_secret_bytes = b"\x00" * len(raw_secret_bytes)


def dpapi_enroll(account: str, secret: str, env: dict[str, str]) -> None:
    """Encrypt OTP secret via Windows DPAPI and persist in Windows Credential Manager."""
    if not account or not LABEL.fullmatch(account):
        raise AppError(2)
    if not secret:
        raise AppError(2)
    target = f"{CREDENTIAL_TARGET_PREFIX}{account}"
    ciphertext = dpapi_encrypt(
        secret.encode("utf-8"),
        entropy=_get_entropy(env),
        description=f"OTP-Local: {account}",
    )
    credman_write(target, ciphertext, comment=f"OTP-Local token for {account}")
    accounts = _read_index(env)
    if account not in accounts:
        accounts.append(account)
        _write_index(accounts, env)


def dpapi_delete(account: str, env: dict[str, str]) -> None:
    """Delete an OTP credential from Windows Credential Manager and index."""
    if not account or not LABEL.fullmatch(account):
        raise AppError(2)
    target = f"{CREDENTIAL_TARGET_PREFIX}{account}"
    credman_delete(target)
    accounts = _read_index(env)
    if account in accounts:
        accounts.remove(account)
        _write_index(accounts, env)
