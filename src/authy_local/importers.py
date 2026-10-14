"""Bulk migration importers for Google Authenticator, Aegis, Bitwarden, and URI lists."""

import base64
import binascii
import errno
import json
import os
import stat
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .enrollment import OtpParameters, clean_base32, parse_secret_or_uri
from .errors import AppError

_MAX_IMPORT_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
_MAX_TOKENS = 5000


def _read_varint(buffer: bytes, offset: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while offset < len(buffer):
        byte = buffer[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not (byte & 0x80):
            return result, offset
    raise ValueError("Truncated protobuf varint")


def parse_google_authenticator_migration(source: str) -> list[OtpParameters]:
    """Parse an otpauth-migration:// URI or base64 data string into OtpParameters."""
    clean_str = source.strip()
    data_b64 = clean_str
    if clean_str.startswith("otpauth-migration://"):
        try:
            parts = urlsplit(clean_str)
            qs = parse_qs(parts.query, strict_parsing=True)
            if "data" not in qs or not qs["data"]:
                raise AppError(2)
            data_b64 = qs["data"][0]
        except Exception:
            raise AppError(2) from None

    # URL-safe base64 unquote and pad
    data_b64 = unquote(data_b64).strip()
    data_b64 += "=" * (-len(data_b64) % 4)
    try:
        raw = base64.b64decode(data_b64, validate=False)
    except binascii.Error, ValueError:
        raise AppError(2) from None

    if not raw or len(raw) > _MAX_IMPORT_FILE_SIZE:
        raise AppError(2)

    tokens: list[OtpParameters] = []
    offset = 0

    try:
        while offset < len(raw):
            tag, offset = _read_varint(raw, offset)
            field_num = tag >> 3
            wire_type = tag & 0x07

            if wire_type == 0:
                _, offset = _read_varint(raw, offset)
            elif wire_type == 1:
                offset += 8
            elif wire_type == 2:
                length, offset = _read_varint(raw, offset)
                if offset + length > len(raw):
                    raise ValueError("Field length exceeds buffer")
                msg_bytes = raw[offset : offset + length]
                offset += length

                if field_num == 1:  # repeated OtpParameters
                    p_off = 0
                    secret_bytes = b""
                    name = ""
                    issuer = ""
                    algo = "SHA1"
                    digits = 6
                    token_type = "totp"

                    while p_off < len(msg_bytes):
                        p_tag, p_off = _read_varint(msg_bytes, p_off)
                        p_field = p_tag >> 3
                        p_wire = p_tag & 0x07

                        if p_wire == 0:
                            val, p_off = _read_varint(msg_bytes, p_off)
                            if p_field == 4:
                                algo = {1: "SHA1", 2: "SHA256", 3: "SHA512", 4: "MD5"}.get(
                                    val, "SHA1"
                                )
                            elif p_field == 5:
                                digits = 8 if val == 2 else 6
                            elif p_field == 6:
                                token_type = "hotp" if val == 1 else "totp"
                        elif p_wire == 1:
                            p_off += 8
                        elif p_wire == 2:
                            p_len, p_off = _read_varint(msg_bytes, p_off)
                            f_bytes = msg_bytes[p_off : p_off + p_len]
                            p_off += p_len
                            if p_field == 1:
                                secret_bytes = f_bytes
                            elif p_field == 2:
                                name = f_bytes.decode("utf-8", errors="replace").strip()
                            elif p_field == 3:
                                issuer = f_bytes.decode("utf-8", errors="replace").strip()
                        elif p_wire == 5:
                            p_off += 4
                        else:
                            raise ValueError(f"Unsupported wire type: {p_wire}")

                    if secret_bytes and token_type == "totp":
                        b32 = base64.b32encode(secret_bytes).decode("ascii").rstrip("=")
                        clean_secret = clean_base32(b32)

                        account = name
                        if not issuer and ":" in name:
                            issuer_part, _, acct_part = name.partition(":")
                            issuer = issuer_part.strip()
                            account = acct_part.strip()

                        tokens.append(
                            OtpParameters(
                                secret=clean_secret,
                                account=account or "account",
                                issuer=issuer,
                                algorithm=algo,
                                digits=digits,
                                period=30,
                                token_type="totp",
                            )
                        )
                        if len(tokens) > _MAX_TOKENS:
                            raise AppError(5)
            elif wire_type == 5:
                offset += 4
            else:
                raise ValueError(f"Unsupported wire type: {wire_type}")
    except ValueError, IndexError:
        raise AppError(2) from None

    if not tokens:
        raise AppError(2)
    return tokens


def parse_aegis_json(content: str | bytes | dict) -> list[OtpParameters]:
    """Parse plain Aegis Authenticator JSON export into OtpParameters."""
    try:
        data = (
            content
            if isinstance(content, dict)
            else json.loads(content if isinstance(content, str) else content.decode("utf-8"))
        )
    except Exception:
        raise AppError(2) from None

    if not isinstance(data, dict):
        raise AppError(2)

    # If vault is encrypted, header will have slots
    if "header" in data and isinstance(data["header"], dict) and data["header"].get("slots"):
        # Encrypted Aegis file requires decryption first
        raise AppError(2)

    db = data.get("db", data)
    entries = db.get("entries", [])
    if not isinstance(entries, list):
        raise AppError(2)

    tokens: list[OtpParameters] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_type = entry.get("type", "totp").lower()
        if entry_type != "totp":
            continue

        name = entry.get("name", "").strip()
        issuer = entry.get("issuer", "").strip()
        info = entry.get("info", {})
        if not isinstance(info, dict):
            continue

        raw_secret = info.get("secret", "").strip()
        if not raw_secret:
            continue

        try:
            clean_secret = clean_base32(raw_secret)
        except AppError:
            continue

        digits = int(info.get("digits", 6))
        period = int(info.get("period", 30))
        algo = info.get("algo", "SHA1").upper()
        if algo not in {"SHA1", "SHA256", "SHA512"}:
            algo = "SHA1"

        tokens.append(
            OtpParameters(
                secret=clean_secret,
                account=name or "account",
                issuer=issuer,
                algorithm=algo,
                digits=digits if digits in (6, 8) else 6,
                period=period if 5 <= period <= 86400 else 30,
                token_type="totp",
            )
        )
        if len(tokens) > _MAX_TOKENS:
            raise AppError(5)

    if not tokens:
        raise AppError(2)
    return tokens


def parse_bitwarden_json(content: str | bytes | dict) -> list[OtpParameters]:
    """Parse Bitwarden vault export JSON into OtpParameters."""
    try:
        data = (
            content
            if isinstance(content, dict)
            else json.loads(content if isinstance(content, str) else content.decode("utf-8"))
        )
    except Exception:
        raise AppError(2) from None

    if not isinstance(data, dict):
        raise AppError(2)

    items = data.get("items", [])
    if not isinstance(items, list):
        raise AppError(2)

    tokens: list[OtpParameters] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        login = item.get("login")
        if not isinstance(login, dict):
            continue
        totp_raw = login.get("totp")
        if not totp_raw or not isinstance(totp_raw, str):
            continue

        item_name = item.get("name", "").strip()
        username = login.get("username", "").strip()

        try:
            param = parse_secret_or_uri(
                totp_raw,
                fallback_label=username or item_name or "account",
                fallback_issuer=item_name,
            )
            if param.token_type == "totp":
                tokens.append(param)
        except AppError:
            continue

        if len(tokens) > _MAX_TOKENS:
            raise AppError(5)

    if not tokens:
        raise AppError(2)
    return tokens


def parse_uri_list(text: str) -> list[OtpParameters]:
    """Parse newline-delimited list of otpauth:// and steam:// URIs."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    tokens: list[OtpParameters] = []
    seen: set[tuple[str, str, str]] = set()

    for line in lines:
        if line.startswith("#"):
            continue
        if line.startswith("otpauth://") or line.startswith("steam://"):
            try:
                p = parse_secret_or_uri(line)
                key = (p.issuer or "", p.account or "", p.secret)
                if key not in seen:
                    seen.add(key)
                    tokens.append(p)
            except AppError:
                continue

    if not tokens:
        raise AppError(2)
    if len(tokens) > _MAX_TOKENS:
        raise AppError(5)
    return tokens


def detect_and_parse_import(
    source: str | Path,
    fmt: str = "auto",
) -> list[OtpParameters]:
    """Detect or parse import format (Google Auth URI, Aegis, Bitwarden, or URI list)."""
    if isinstance(source, str) and source.strip().startswith("otpauth-migration://"):
        return parse_google_authenticator_migration(source.strip())

    path = Path(source).expanduser()
    if path.is_symlink():
        raise AppError(3)

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        raise AppError(2) from None
    except OSError as err:
        if err.errno == errno.ELOOP:
            raise AppError(3) from None
        if err.errno in (errno.ENAMETOOLONG, errno.EINVAL, errno.ENOENT):
            raise AppError(2) from None
        raise AppError(3) from None

    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > _MAX_IMPORT_FILE_SIZE:
            os.close(fd)
            raise AppError(2)
        chunks = []
        bytes_read = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            bytes_read += len(chunk)
            if bytes_read > _MAX_IMPORT_FILE_SIZE:
                os.close(fd)
                raise AppError(2)
            chunks.append(chunk)
        os.close(fd)
        content_bytes = b"".join(chunks)
    except AppError:
        raise
    except OSError:
        try:
            os.close(fd)
        except OSError:
            pass
        raise AppError(3) from None

    text = content_bytes.decode("utf-8", errors="replace").strip()
    if fmt == "uri-list":
        return parse_uri_list(text)
    if fmt == "google-migration" or text.startswith("otpauth-migration://"):
        return parse_google_authenticator_migration(text)

    # Try JSON formats
    if text.startswith("{") or fmt in ("aegis", "bitwarden"):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                if fmt == "bitwarden" or "items" in data:
                    return parse_bitwarden_json(data)
                if fmt == "aegis" or "db" in data or "entries" in data or "header" in data:
                    return parse_aegis_json(data)
        except Exception:
            if fmt in ("aegis", "bitwarden"):
                raise AppError(2) from None

    # Try line-by-line otpauth:// / steam:// URIs
    try:
        return parse_uri_list(text)
    except AppError:
        pass

    raise AppError(2)
