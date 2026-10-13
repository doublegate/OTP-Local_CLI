"""FIDO2 CTAP 2.1 hardware security key backend with HMAC-secret derivation."""

import ctypes
import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

from ..enrollment import OtpParameters, generate_totp_code
from ..errors import AppError

LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
SALT_PREFIX = b"OTP-Local-Salt-v1"
KDK_PREFIX = b"OTP-Local-KDK-v1:"
RP_ID = "otp-local"

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

try:
    from fido2.ctap2 import Ctap2
    from fido2.ctap2.extensions import HMACGetSecretInput
    from fido2.ctap2.pin import ClientPin
    from fido2.hid import CtapHidDevice

    HAS_FIDO2 = True
except ImportError:
    HAS_FIDO2 = False

_device_override: list[Any] | None = None


def _set_device_override(devices: list[Any] | None) -> None:
    """Set synthetic device override for automated unit tests."""
    global _device_override
    _device_override = devices


def _get_store_path(env: dict[str, str]) -> Path:
    base = env.get("XDG_STATE_HOME") or env.get("LOCALAPPDATA")
    if base:
        directory = Path(base) / "authy-local"
    else:
        directory = Path.home() / ".local/state/authy-local"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        pass
    return directory / "fido2_vault.json"


def _read_vault(env: dict[str, str]) -> dict[str, Any]:
    path = _get_store_path(env)
    if not path.is_file():
        return {"accounts": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "accounts" in data and isinstance(data["accounts"], dict):
            return data
    except Exception:
        pass
    return {"accounts": {}}


def _write_vault(vault: dict[str, Any], env: dict[str, str]) -> None:
    path = _get_store_path(env)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(vault, indent=2) + "\n", encoding="utf-8")
    try:
        temp.chmod(0o600)
        temp.replace(path)
    except OSError:
        pass


def _derive_salt(account: str) -> bytes:
    """Derive deterministic 32-byte salt for FIDO2 HMAC-secret assertion."""
    return hmac.new(SALT_PREFIX, account.encode("utf-8"), hashlib.sha256).digest()


def _derive_kdk(hmac_output: bytes) -> bytes:
    """Derive 256-bit AES-GCM key from hardware HMAC-secret output."""
    return hashlib.sha256(KDK_PREFIX + hmac_output).digest()


def list_devices() -> list[Any]:
    """Enumerate connected FIDO2 HID devices or return synthetic overrides."""
    if _device_override is not None:
        return _device_override
    if not HAS_FIDO2:
        return []
    try:
        return list(CtapHidDevice.list_devices())
    except Exception:
        return []


def get_ctap2_device() -> tuple[Any, Any]:
    """Find and return an active CTAP2 authenticator with hmac-secret support."""
    devices = list_devices()
    if not devices:
        raise AppError(3)

    for dev in devices:
        try:
            if hasattr(dev, "ctap"):
                ctap = dev.ctap
            else:
                ctap = Ctap2(dev)
            info = getattr(ctap, "info", None)
            if info is None and hasattr(ctap, "get_info"):
                info = ctap.get_info()

            extensions = getattr(info, "extensions", []) or []
            if "hmac-secret" in extensions or getattr(dev, "has_hmac_secret", True):
                return dev, ctap
        except Exception:
            continue

    # Fallback to first device if extension negotiation is flexible
    first = devices[0]
    ctap = getattr(first, "ctap", None) or Ctap2(first)
    return first, ctap


def probe(env: dict[str, str]) -> dict[str, Any]:
    """Probe system availability of FIDO2 CTAP 2.1 hardware tokens."""
    if not HAS_FIDO2 or not HAS_CRYPTOGRAPHY:
        return {"state": "missing", "reason": "fido2 or cryptography library missing"}

    devices = list_devices()
    if not devices:
        return {"state": "missing", "device_count": 0}

    usable = False
    for dev in devices:
        try:
            ctap = getattr(dev, "ctap", None) or Ctap2(dev)
            info = getattr(ctap, "info", None)
            extensions = getattr(info, "extensions", []) or []
            if "hmac-secret" in extensions or getattr(dev, "has_hmac_secret", True):
                usable = True
                break
        except Exception:
            pass

    return {
        "state": "available" if usable else "missing",
        "device_count": len(devices),
        "hmac_secret": usable,
    }


def fido2_records(env: dict[str, str]) -> list[tuple[str, str]]:
    """Enumerate enrolled FIDO2 accounts from the local vault."""
    vault = _read_vault(env)
    accounts = sorted(list(vault.get("accounts", {}).keys()))
    return [(acct, f"{acct} [FIDO2]") for acct in accounts]


def fido2_enroll(
    account: str,
    secret: str,
    env: dict[str, str],
    pin: str | None = None,
    touch_callback: Callable[[], None] | None = None,
) -> None:
    """Enroll a new TOTP secret protected by physical FIDO2 CTAP 2.1 HMAC-secret key."""
    if not account or not LABEL.fullmatch(account):
        raise AppError(2)
    if not secret:
        raise AppError(2)
    if not HAS_FIDO2 or not HAS_CRYPTOGRAPHY:
        raise AppError(3)

    dev, ctap = get_ctap2_device()

    if touch_callback:
        touch_callback()

    client_data_hash = hashlib.sha256(f"OTP-Local Enrollment: {account}".encode("utf-8")).digest()
    user_id = hashlib.sha256(account.encode("utf-8")).digest()

    salt = _derive_salt(account)

    # Execute make_credential with hmacCreateSecret extension
    try:
        if hasattr(dev, "mock_enroll"):
            # Synthetic mock path
            cred_id, hmac_output, aaguid = dev.mock_enroll(
                account=account, salt=salt, pin=pin
            )
        else:
            # Native fido2 CTAP2 path
            pin_auth = None
            if pin and hasattr(ctap, "info") and ctap.info.options.get("clientPin"):
                client_pin = ClientPin(ctap)
                pin_auth = client_pin.get_pin_token(pin)

            ext_inputs = {"hmacCreateSecret": True}
            attestation = ctap.make_credential(
                client_data_hash=client_data_hash,
                rp={"id": RP_ID, "name": "OTP-Local"},
                user={"id": user_id, "name": account, "displayName": account},
                key_params=[{"type": "public-key", "alg": -7}],  # ES256
                extensions=ext_inputs,
                pin_uv_param=pin_auth,
            )

            auth_data = attestation.auth_data
            cred_id = auth_data.credential_data.credential_id
            aaguid = auth_data.credential_data.aaguid.hex()

            # Perform initial assertion to extract initial HMAC-secret
            assertion = ctap.get_assertion(
                rp_id=RP_ID,
                client_data_hash=client_data_hash,
                allow_list=[{"type": "public-key", "id": cred_id}],
                extensions={"hmac-secret": HMACGetSecretInput(salt1=salt)},
                pin_uv_param=pin_auth,
            )
            hmac_output = assertion.auth_data.extensions.get("hmac-secret")
            if not hmac_output:
                raise AppError(4)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(4) from exc

    kdk = _derive_kdk(hmac_output)
    aes = AESGCM(kdk)
    nonce = os.urandom(12)
    ciphertext = aes.encrypt(nonce, secret.strip().encode("utf-8"), account.encode("utf-8"))

    vault = _read_vault(env)
    vault["accounts"][account] = {
        "credential_id": cred_id.hex() if isinstance(cred_id, bytes) else str(cred_id),
        "salt": salt.hex(),
        "nonce": nonce.hex(),
        "ciphertext": ciphertext.hex(),
        "aaguid": str(aaguid),
        "created_at": time.time(),
        "backup_tokens": [],
    }
    _write_vault(vault, env)


def fido2_add_backup_token(
    account: str,
    secret: str,
    env: dict[str, str],
    pin: str | None = None,
    touch_callback: Callable[[], None] | None = None,
) -> None:
    """Register a secondary backup FIDO2 security key for an enrolled account."""
    if not account or not LABEL.fullmatch(account):
        raise AppError(2)
    if not secret:
        raise AppError(2)
    if not HAS_FIDO2 or not HAS_CRYPTOGRAPHY:
        raise AppError(3)

    vault = _read_vault(env)
    entry = vault.get("accounts", {}).get(account)
    if not entry:
        raise AppError(4)

    dev, ctap = get_ctap2_device()
    if touch_callback:
        touch_callback()

    client_data_hash = hashlib.sha256(
        f"OTP-Local Backup Enrollment: {account}".encode("utf-8")
    ).digest()
    user_id = hashlib.sha256(account.encode("utf-8")).digest()
    salt = bytes.fromhex(entry["salt"])

    try:
        if hasattr(dev, "mock_enroll"):
            cred_id, hmac_output, aaguid = dev.mock_enroll(
                account=account, salt=salt, pin=pin
            )
        else:
            pin_auth = None
            if pin and hasattr(ctap, "info") and ctap.info.options.get("clientPin"):
                client_pin = ClientPin(ctap)
                pin_auth = client_pin.get_pin_token(pin)

            ext_inputs = {"hmacCreateSecret": True}
            attestation = ctap.make_credential(
                client_data_hash=client_data_hash,
                rp={"id": RP_ID, "name": "OTP-Local"},
                user={"id": user_id, "name": account, "displayName": account},
                key_params=[{"type": "public-key", "alg": -7}],
                extensions=ext_inputs,
                pin_uv_param=pin_auth,
            )

            auth_data = attestation.auth_data
            cred_id = auth_data.credential_data.credential_id
            aaguid = auth_data.credential_data.aaguid.hex()

            assertion = ctap.get_assertion(
                rp_id=RP_ID,
                client_data_hash=client_data_hash,
                allow_list=[{"type": "public-key", "id": cred_id}],
                extensions={"hmac-secret": HMACGetSecretInput(salt1=salt)},
                pin_uv_param=pin_auth,
            )
            hmac_output = assertion.auth_data.extensions.get("hmac-secret")
            if not hmac_output:
                raise AppError(4)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(4) from exc

    kdk = _derive_kdk(hmac_output)
    aes = AESGCM(kdk)
    nonce = os.urandom(12)
    ciphertext = aes.encrypt(nonce, secret.strip().encode("utf-8"), account.encode("utf-8"))

    backup_tokens = entry.setdefault("backup_tokens", [])
    backup_tokens.append(
        {
            "credential_id": cred_id.hex() if isinstance(cred_id, bytes) else str(cred_id),
            "nonce": nonce.hex(),
            "ciphertext": ciphertext.hex(),
            "aaguid": str(aaguid),
            "created_at": time.time(),
        }
    )
    _write_vault(vault, env)


def fido2_code(
    account: str,
    env: dict[str, str],
    pin: str | None = None,
    touch_callback: Callable[[], None] | None = None,
    timestamp: float | None = None,
) -> str:
    """Retrieve FIDO2-protected TOTP code using primary or backup physical key upon touch."""
    if not account or not LABEL.fullmatch(account):
        raise AppError(2)
    if not HAS_FIDO2 or not HAS_CRYPTOGRAPHY:
        raise AppError(3)

    vault = _read_vault(env)
    entry = vault.get("accounts", {}).get(account)
    if not entry:
        raise AppError(4)

    salt = bytes.fromhex(entry["salt"])

    candidates = [
        {
            "credential_id": entry["credential_id"],
            "nonce": entry["nonce"],
            "ciphertext": entry["ciphertext"],
        }
    ]
    for b in entry.get("backup_tokens", []):
        candidates.append(b)

    dev, ctap = get_ctap2_device()

    if touch_callback:
        touch_callback()

    client_data_hash = hashlib.sha256(
        f"OTP-Local Code Generation: {account}".encode("utf-8")
    ).digest()

    last_error = None
    for cand in candidates:
        cred_id = bytes.fromhex(cand["credential_id"])
        nonce = bytes.fromhex(cand["nonce"])
        ciphertext = bytes.fromhex(cand["ciphertext"])
        try:
            if hasattr(dev, "mock_assertion"):
                hmac_output = dev.mock_assertion(cred_id=cred_id, salt=salt, pin=pin)
            else:
                pin_auth = None
                if pin and hasattr(ctap, "info") and ctap.info.options.get("clientPin"):
                    client_pin = ClientPin(ctap)
                    pin_auth = client_pin.get_pin_token(pin)

                assertion = ctap.get_assertion(
                    rp_id=RP_ID,
                    client_data_hash=client_data_hash,
                    allow_list=[{"type": "public-key", "id": cred_id}],
                    extensions={"hmac-secret": HMACGetSecretInput(salt1=salt)},
                    pin_uv_param=pin_auth,
                )
                hmac_output = assertion.auth_data.extensions.get("hmac-secret")
                if not hmac_output:
                    continue

            kdk = _derive_kdk(hmac_output)
            aes = AESGCM(kdk)
            plaintext_bytes = aes.decrypt(nonce, ciphertext, account.encode("utf-8"))
            raw_secret = plaintext_bytes.decode("utf-8", errors="replace").strip()
            try:
                params = OtpParameters(secret=raw_secret, account=account)
                code, _ = generate_totp_code(params, timestamp=timestamp)
                return code
            finally:
                raw_secret = ""
                c_buf = (ctypes.c_char * len(plaintext_bytes)).from_buffer(
                    bytearray(plaintext_bytes)
                )
                ctypes.memset(ctypes.addressof(c_buf), 0, len(plaintext_bytes))
        except AppError as exc:
            last_error = exc
            continue
        except Exception:
            continue

    if last_error:
        raise last_error
    raise AppError(5)


def fido2_delete(account: str, env: dict[str, str]) -> None:
    """Delete an enrolled FIDO2 credential entry from the local vault."""
    if not account or not LABEL.fullmatch(account):
        raise AppError(2)
    vault = _read_vault(env)
    if account in vault.get("accounts", {}):
        del vault["accounts"][account]
        _write_vault(vault, env)
