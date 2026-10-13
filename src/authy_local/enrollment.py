"""Interactive OTP ingestion, QR decoding, Wayland clipboard, and RFC 6238 generation."""

import base64
import binascii
import hashlib
import hmac
import re
import shutil
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

from .errors import AppError
from .processes import run


@dataclass
class OtpParameters:
    """Validated parameters for an OTP token."""

    secret: str
    account: str = "account"
    issuer: str = ""
    algorithm: str = "SHA1"
    digits: int = 6
    period: int = 30
    token_type: str = "totp"
    counter: int = 0

    def to_uri(self) -> str:
        """Serialize parameters to canonical otpauth URI."""
        label = (
            f"{self.issuer}:{self.account}"
            if self.issuer and self.account
            else (self.issuer or self.account or "entry")
        )
        params = [("secret", self.secret)]
        if self.issuer:
            params.append(("issuer", self.issuer))
        if self.algorithm != "SHA1":
            params.append(("algorithm", self.algorithm))
        if self.digits != 6:
            params.append(("digits", str(self.digits)))
        if self.token_type == "hotp":
            params.append(("counter", str(self.counter)))
        elif self.period != 30:
            params.append(("period", str(self.period)))
        return f"otpauth://{self.token_type}/{label}?{urlencode(params)}"


def clean_base32(value: str) -> str:
    """Normalize and validate a Base32 secret string.

    Strips whitespace, hyphens, and padding; converts to uppercase; validates
    RFC 4648 Base32 alphabet and length bounds.
    """
    if not isinstance(value, str):
        raise AppError(2)
    cleaned = re.sub(r"[\s\-]+", "", value).upper().rstrip("=")
    if not cleaned or re.fullmatch(r"[A-Z2-7]{16,256}", cleaned) is None:
        raise AppError(2)
    try:
        raw = base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))
    except ValueError, binascii.Error:
        raise AppError(2) from None
    if not 10 <= len(raw) <= 160:
        raise AppError(2)
    return cleaned


def parse_secret_or_uri(
    text: str,
    *,
    fallback_label: str = "",
    fallback_issuer: str = "",
    digits: int = 6,
    period: int = 30,
    algorithm: str = "SHA1",
) -> OtpParameters:
    """Parse either an otpauth:// / steam:// URI or a raw Base32 secret string."""
    if not isinstance(text, str):
        raise AppError(2)
    raw_text = text.strip()
    if not raw_text:
        raise AppError(2)

    if raw_text.startswith("otpauth://") or raw_text.startswith("steam://"):
        return _parse_uri(raw_text)

    # Raw secret string path
    secret = clean_base32(raw_text)
    if digits not in (5, 6, 8):
        raise AppError(2)
    if period < 5 or period > 86400:
        raise AppError(2)
    algo_upper = algorithm.upper()
    if algo_upper not in {"SHA1", "SHA256", "SHA512", "STEAM"}:
        raise AppError(2)
    if digits == 5 or algo_upper == "STEAM":
        digits = 5
        algo_upper = "STEAM"

    account = fallback_label.strip() or "account"
    issuer = fallback_issuer.strip()
    return OtpParameters(
        secret=secret,
        account=account,
        issuer=issuer,
        algorithm=algo_upper,
        digits=digits,
        period=period,
        token_type="totp",
    )


def _parse_uri(uri_str: str) -> OtpParameters:
    """Strictly parse and validate an otpauth or steam URI."""
    if len(uri_str) > 4096 or not uri_str.isascii():
        raise AppError(2)
    try:
        uri = urlsplit(uri_str)
        pairs = parse_qsl(uri.query, strict_parsing=True, max_num_fields=12)
    except ValueError:
        raise AppError(2) from None

    if uri.fragment:
        raise AppError(2)

    if uri.scheme == "steam":
        token_type = "totp"
        path = unquote(uri.path or uri.netloc).lstrip("/")
    elif uri.scheme == "otpauth":
        if uri.netloc not in {"totp", "hotp"}:
            raise AppError(2)
        token_type = uri.netloc
        path = unquote(uri.path).lstrip("/")
    else:
        raise AppError(2)

    if not path or any(ord(c) < 32 or ord(c) == 127 for c in path):
        raise AppError(2)

    params = dict(pairs)
    if len(params) != len(pairs):
        raise AppError(2)  # Duplicate query keys rejected

    allowed_keys = {"secret", "issuer", "digits", "period", "algorithm", "counter"}
    if set(params) - allowed_keys:
        raise AppError(2)

    if "secret" not in params:
        raise AppError(2)
    secret = clean_base32(params["secret"])

    # Parse label into issuer and account
    label = path
    if ":" in label:
        path_issuer, _, path_account = label.partition(":")
        path_issuer = path_issuer.strip()
        path_account = path_account.strip()
    else:
        path_issuer = ""
        path_account = label.strip()

    issuer = params.get("issuer", path_issuer).strip()
    account = path_account or "account"

    raw_algo = params.get(
        "algorithm", "STEAM" if (uri.scheme == "steam" or params.get("digits") == "5") else "SHA1"
    ).upper()
    if raw_algo not in {"SHA1", "SHA256", "SHA512", "STEAM"}:
        raise AppError(2)

    digits = int(params.get("digits", 5 if raw_algo == "STEAM" else 6))
    if digits not in (5, 6, 8):
        raise AppError(2)

    period = int(params.get("period", 30))
    if period < 5 or period > 86400:
        raise AppError(2)

    if digits == 5 or raw_algo == "STEAM":
        digits = 5
        raw_algo = "STEAM"

    counter = 0
    if "counter" in params:
        try:
            counter = int(params["counter"])
            if counter < 0 or counter > 2**63 - 1:
                raise AppError(2)
        except ValueError:
            raise AppError(2) from None

    return OtpParameters(
        secret=secret,
        account=account,
        issuer=issuer,
        algorithm=raw_algo,
        digits=digits,
        period=period,
        token_type=token_type,
        counter=counter,
    )


def decode_qr_image_bytes(image_bytes: bytes, env: dict[str, str]) -> str:
    """Decode a QR code from raw image bytes using zbarimg via stdin."""
    if not image_bytes:
        raise AppError(2)
    zbarimg = shutil.which("zbarimg", path=env.get("PATH", ""))
    if zbarimg is None:
        raise AppError(3)

    clean_env = {
        k: v for k, v in env.items() if not k.startswith("BASH_") and k not in {"SHELL", "PROMPT"}
    }
    result = run(
        [zbarimg, "-q", "--raw", "-"],
        env=clean_env,
        input_data=image_bytes,
        timeout=15,
        stdout_cap=65536,
        stderr_cap=8192,
        preserve_session=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise AppError(2)

    try:
        decoded = result.stdout.decode("utf-8").strip()
    except UnicodeDecodeError:
        try:
            decoded = result.stdout.decode("latin-1").strip()
        except Exception:
            raise AppError(2) from None

    if not decoded:
        raise AppError(2)
    return decoded


def decode_qr_image_file(path: str | Path, env: dict[str, str]) -> str:
    """Decode a QR code from a file on disk."""
    p = Path(path).expanduser().resolve()
    if not p.is_file() or p.is_symlink():
        raise AppError(2)
    try:
        size = p.stat().st_size
        if size > 25 * 1024 * 1024:  # 25 MB max limit
            raise AppError(2)
        data = p.read_bytes()
    except OSError:
        raise AppError(2) from None
    return decode_qr_image_bytes(data, env)


def get_clipboard_image(env: dict[str, str]) -> bytes:
    """Retrieve raw image bytes from Wayland clipboard using wl-paste."""
    if not env.get("WAYLAND_DISPLAY"):
        raise AppError(3)
    wl_paste = shutil.which("wl-paste", path=env.get("PATH", ""))
    if wl_paste is None:
        raise AppError(3)

    clean_env = {
        k: v for k, v in env.items() if not k.startswith("BASH_") and k not in {"SHELL", "PROMPT"}
    }
    result = run(
        [wl_paste, "-t", "image/png"],
        env=clean_env,
        timeout=8,
        stdout_cap=25 * 1024 * 1024,
        stderr_cap=4096,
        preserve_session=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise AppError(2)
    return result.stdout


def get_clipboard_text(env: dict[str, str]) -> str:
    """Retrieve text from Wayland clipboard using wl-paste."""
    if not env.get("WAYLAND_DISPLAY"):
        raise AppError(3)
    wl_paste = shutil.which("wl-paste", path=env.get("PATH", ""))
    if wl_paste is None:
        raise AppError(3)

    clean_env = {
        k: v for k, v in env.items() if not k.startswith("BASH_") and k not in {"SHELL", "PROMPT"}
    }
    result = run(
        [wl_paste, "-t", "text/plain"],
        env=clean_env,
        timeout=5,
        stdout_cap=32768,
        stderr_cap=4096,
        preserve_session=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise AppError(2)
    return result.stdout.decode("utf-8", errors="replace").strip()


def generate_totp_code(
    params: OtpParameters,
    timestamp: float | None = None,
) -> tuple[str, float]:
    """Compute RFC 6238 TOTP code and remaining valid seconds.

    Returns:
        tuple[str, float]: (code_str, remaining_seconds)
    """
    now = time.time() if timestamp is None else timestamp
    step = int(now // params.period)
    remaining = float(params.period - (now % params.period))

    # Decode Base32 key
    secret_clean = clean_base32(params.secret)
    key = bytearray(base64.b32decode(secret_clean + "=" * (-len(secret_clean) % 8), casefold=True))

    try:
        msg = struct.pack(">Q", step)
        algo_name = params.algorithm.lower()
        if algo_name == "sha256":
            digest_mod = hashlib.sha256
        elif algo_name == "sha512":
            digest_mod = hashlib.sha512
        else:
            digest_mod = hashlib.sha1

        h = hmac.new(bytes(key), msg, digest_mod).digest()
        offset = h[-1] & 0x0F
        code_int = struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF
        if algo_name == "steam" or params.digits == 5:
            charset = "23456789BCDFGHJKMNPQRTVWXY"
            chars = []
            for _ in range(5):
                chars.append(charset[code_int % len(charset)])
                code_int //= len(charset)
            code_str = "".join(chars)
        else:
            code_str = str(code_int % (10**params.digits)).zfill(params.digits)
        return code_str, remaining
    finally:
        # Cryptographic memory hygiene: zero out key buffer
        for i in range(len(key)):
            key[i] = 0


def generate_totp_from_uri(
    uri_or_secret: str,
    timestamp: float | None = None,
    digits: int = 6,
    period: int = 30,
    algorithm: str = "SHA1",
) -> tuple[str, float]:
    """Compute RFC 6238 TOTP code and remaining seconds directly from URI or secret."""
    params = parse_secret_or_uri(uri_or_secret, digits=digits, period=period, algorithm=algorithm)
    if params.token_type != "totp":
        raise AppError(2)
    return generate_totp_code(params, timestamp=timestamp)


def generate_hotp_code(
    secret: str,
    counter: int,
    digits: int = 6,
    algorithm: str = "SHA1",
) -> str:
    """Compute RFC 4226 HOTP code for a given counter value."""
    if counter < 0 or counter > 2**63 - 1:
        raise AppError(2)
    secret_clean = clean_base32(secret)
    key = bytearray(base64.b32decode(secret_clean + "=" * (-len(secret_clean) % 8), casefold=True))
    try:
        msg = struct.pack(">Q", counter)
        algo_name = algorithm.lower()
        if algo_name == "sha256":
            digest_mod = hashlib.sha256
        elif algo_name == "sha512":
            digest_mod = hashlib.sha512
        else:
            digest_mod = hashlib.sha1

        h = hmac.new(bytes(key), msg, digest_mod).digest()
        offset = h[-1] & 0x0F
        code_int = struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF
        return str(code_int % (10**digits)).zfill(digits)
    finally:
        for i in range(len(key)):
            key[i] = 0


def generate_hotp_from_uri(
    uri_or_secret: str,
    counter: int | None = None,
    digits: int = 6,
    algorithm: str = "SHA1",
) -> str:
    """Compute RFC 4226 HOTP code directly from URI or secret."""
    params = parse_secret_or_uri(uri_or_secret, digits=digits, algorithm=algorithm)
    if params.token_type != "hotp":
        raise AppError(2)
    cnt = params.counter if counter is None else counter
    return generate_hotp_code(params.secret, cnt, digits=params.digits, algorithm=params.algorithm)
