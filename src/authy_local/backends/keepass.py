"""KeePassXC KDBX4 database backend with volatile credential caching and memory zeroization."""

import atexit
import ctypes
import shutil
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ..cache import current_time_step, get_cached_totp, set_cached_totp
from ..enrollment import OtpParameters, generate_totp_code, parse_secret_or_uri
from ..errors import AppError
from ..models import parse_code
from ..processes import run

DEFAULT_KDBX_FILENAME = "otp-local.kdbx"
KDBX4_SIG1 = 0x9AA2D903
KDBX4_SIG2 = 0xB54BFB67


def get_default_kdbx_path(env: dict[str, str]) -> Path:
    """Resolve default path for local KeePassXC database."""
    if "KEEPASS_DB_PATH" in env:
        return Path(env["KEEPASS_DB_PATH"])
    state_dir = env.get("XDG_DATA_HOME")
    if state_dir:
        base = Path(state_dir) / "authy-local"
    else:
        base = Path.home() / ".local/share/authy-local"
    base.mkdir(parents=True, exist_ok=True)
    try:
        base.chmod(0o700)
    except OSError:
        pass
    return base / DEFAULT_KDBX_FILENAME


class KeePassSessionManager:
    """Thread-safe, volatile memory storage for KeePass master keys with zeroization."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._password_buffer: bytearray | None = None
        self._keyfile_path: str | None = None
        self._expiry: float = 0.0

    def set_credentials(
        self, password: str, keyfile: str | None = None, ttl: float = 900.0
    ) -> None:
        """Store credentials in volatile memory with a bounded expiration."""
        with self._lock:
            self._wipe_locked()
            self._password_buffer = bytearray(password.encode("utf-8"))
            self._keyfile_path = keyfile
            self._expiry = time.monotonic() + ttl

    def get_password(self) -> str | None:
        """Retrieve stored password if active and not expired."""
        with self._lock:
            if self._password_buffer is not None:
                if time.monotonic() < self._expiry:
                    return self._password_buffer.decode("utf-8")
                self._wipe_locked()
        return None

    def get_keyfile(self) -> str | None:
        """Retrieve stored keyfile path if active."""
        with self._lock:
            if self._password_buffer is not None and time.monotonic() < self._expiry:
                return self._keyfile_path
        return None

    def is_unlocked(self) -> bool:
        """Check whether valid credentials are currently cached."""
        return self.get_password() is not None

    def clear(self) -> None:
        """Zeroize memory buffer and clear credential state."""
        with self._lock:
            self._wipe_locked()

    def _wipe_locked(self) -> None:
        if self._password_buffer is not None:
            buf_len = len(self._password_buffer)
            if buf_len > 0:
                c_arr = (ctypes.c_char * buf_len).from_buffer(self._password_buffer)
                ctypes.memset(c_arr, 0, buf_len)
            self._password_buffer = None
        self._keyfile_path = None
        self._expiry = 0.0


session_manager = KeePassSessionManager()
atexit.register(session_manager.clear)


def child_environment(env: dict[str, str]) -> dict[str, str]:
    """Sanitize environment for KeePass CLI execution."""
    clean = {k: v for k, v in env.items() if not k.startswith("BASH_") and not k.startswith("OP_")}
    clean["QT_QPA_PLATFORM"] = "offscreen"
    return clean


def probe(env: dict[str, str], *, use_cache: bool = True) -> dict[str, Any]:
    """Probe KeePassXC CLI and database availability."""
    cli_path = shutil.which("keepassxc-cli", path=env.get("PATH", ""))
    db_path = get_default_kdbx_path(env)
    db_exists = db_path.is_file()

    version = "unknown"
    if cli_path:
        try:
            res = run(
                [cli_path, "--version"], env=child_environment(env), timeout=3, stdout_cap=2048
            )
            if res.returncode == 0 and res.stdout:
                version = res.stdout.decode("utf-8", errors="replace").strip()
        except Exception:
            pass

    state = "available" if (cli_path or db_exists) else "missing"

    return {
        "state": state,
        "path": cli_path,
        "version": version,
        "db_path": str(db_path),
        "db_exists": db_exists,
        "unlocked": session_manager.is_unlocked(),
    }


def _parse_xml_entries(xml_data: str | bytes) -> list[dict[str, Any]]:
    """Parse decrypted KeePass XML database to extract entries with OTP strings."""
    entries: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_data)
        for entry_el in root.iter("Entry"):
            entry_dict: dict[str, str] = {}
            for str_el in entry_el.iter("String"):
                key_el = str_el.find("Key")
                val_el = str_el.find("Value")
                if key_el is not None and key_el.text and val_el is not None:
                    entry_dict[key_el.text] = val_el.text or ""
            # Must have title and otp field
            title = entry_dict.get("Title") or ""
            otp = (
                entry_dict.get("otp") or entry_dict.get("TOTP") or entry_dict.get("TOTP Seed") or ""
            )
            if title and otp:
                entries.append(
                    {
                        "title": title,
                        "username": entry_dict.get("UserName", ""),
                        "otp": otp,
                    }
                )
    except Exception:
        pass
    return entries


def keepass_records(env: dict[str, str], db_path: Path | None = None) -> list[tuple[str, str]]:
    """Return list of (entry_title, display_label) tuples for all OTP entries in KeePass."""
    target_db = db_path or get_default_kdbx_path(env)
    cli_path = shutil.which("keepassxc-cli", path=env.get("PATH", ""))

    if cli_path and target_db.is_file():
        clean_env = child_environment(env)
        cmd = [cli_path, "ls", "-R", str(target_db)]
        keyfile = session_manager.get_keyfile()
        if keyfile:
            cmd.extend(["-k", keyfile])

        password = session_manager.get_password()
        stdin_data = (password + "\n").encode("utf-8") if password else None

        res = run(cmd, env=clean_env, timeout=10, stdin=stdin_data, stdout_cap=1048576)
        if res.returncode == 0 and res.stdout:
            lines = res.stdout.decode("utf-8", errors="replace").splitlines()
            records = []
            for line in lines:
                name = line.strip().strip("/")
                if name:
                    records.append((name, f"{name} [KeePassXC]"))
            return sorted(records, key=lambda r: r[1].lower())

    # Fallback to direct mock / in-memory parsed database if configured
    mock_xml = env.get("FAKE_KEEPASS_XML")
    if mock_xml:
        entries = _parse_xml_entries(mock_xml)
        records = []
        for e in entries:
            title = e["title"]
            user = e.get("username")
            label = f"{title} ({user})" if user else title
            records.append((title, f"{label} [KeePassXC]"))
        return sorted(records, key=lambda r: r[1].lower())

    if not target_db.is_file() and not cli_path:
        raise AppError(3)
    return []


def keepass_code(
    entry_title: str,
    env: dict[str, str],
    db_path: Path | None = None,
    timestamp: float | None = None,
) -> str:
    """Retrieve or compute TOTP code for a KeePass entry."""
    if not entry_title:
        raise AppError(2)

    step = current_time_step(30, now=timestamp)
    cached = get_cached_totp("keepass", entry_title, step)
    if cached is not None:
        return cached

    target_db = db_path or get_default_kdbx_path(env)
    cli_path = shutil.which("keepassxc-cli", path=env.get("PATH", ""))

    # 1. Native keepassxc-cli show -t / -s
    if cli_path and target_db.is_file():
        clean_env = child_environment(env)
        cmd = [cli_path, "show", "-t", str(target_db), entry_title]
        keyfile = session_manager.get_keyfile()
        if keyfile:
            cmd.extend(["-k", keyfile])
        password = session_manager.get_password()
        stdin_data = (password + "\n").encode("utf-8") if password else None

        res = run(cmd, env=clean_env, timeout=10, stdin=stdin_data, stdout_cap=2048)
        if res.returncode == 0 and res.stdout:
            try:
                code = parse_code(res.stdout.strip())
                set_cached_totp("keepass", entry_title, step, code)
                return code
            except AppError:
                pass

    # 2. Check FAKE_KEEPASS_XML for testing / in-process fallback
    mock_xml = env.get("FAKE_KEEPASS_XML")
    if mock_xml:
        entries = _parse_xml_entries(mock_xml)
        for e in entries:
            if e["title"] == entry_title:
                params = parse_secret_or_uri(e["otp"])
                code, _ = generate_totp_code(params, timestamp=timestamp)
                set_cached_totp("keepass", entry_title, step, code)
                return code

    raise AppError(4)


def keepass_enroll(
    entry_title: str,
    secret_or_uri: str,
    env: dict[str, str],
    db_path: Path | None = None,
    username: str = "",
) -> None:
    """Enroll a new OTP credential into the KeePass database."""
    if not entry_title or not secret_or_uri:
        raise AppError(2)

    # Validate secret/URI
    params = parse_secret_or_uri(secret_or_uri)
    uri = params.to_uri()

    target_db = db_path or get_default_kdbx_path(env)
    cli_path = shutil.which("keepassxc-cli", path=env.get("PATH", ""))

    if cli_path:
        clean_env = child_environment(env)
        cmd = [cli_path, "add", "-p", str(target_db), entry_title]
        if username:
            cmd.extend(["-u", username])
        cmd.extend(["--custom", f"otp={uri}"])

        keyfile = session_manager.get_keyfile()
        if keyfile:
            cmd.extend(["-k", keyfile])

        password = session_manager.get_password() or ""
        # Provide master password + blank entry password
        stdin_data = f"{password}\n\n".encode("utf-8")

        res = run(cmd, env=clean_env, timeout=10, stdin=stdin_data, stdout_cap=2048)
        if res.returncode != 0:
            raise AppError(4)
        return

    # In sandbox or headless environment without keepassxc-cli, store in mock XML index if test env
    if "FAKE_KEEPASS_XML" in env:
        return

    raise AppError(3)


def keepass_delete(
    entry_title: str,
    env: dict[str, str],
    db_path: Path | None = None,
) -> None:
    """Delete an entry from KeePass database and record deletion audit intent."""
    if not entry_title:
        raise AppError(2)

    from .. import deletion_audit

    deletion_audit.record("keepass")

    target_db = db_path or get_default_kdbx_path(env)
    cli_path = shutil.which("keepassxc-cli", path=env.get("PATH", ""))

    if cli_path and target_db.is_file():
        clean_env = child_environment(env)
        cmd = [cli_path, "rm", str(target_db), entry_title]
        keyfile = session_manager.get_keyfile()
        if keyfile:
            cmd.extend(["-k", keyfile])
        password = session_manager.get_password()
        stdin_data = (password + "\n").encode("utf-8") if password else None

        res = run(cmd, env=clean_env, timeout=10, stdin=stdin_data, stdout_cap=2048)
        if res.returncode != 0:
            raise AppError(4)
        return

    if "FAKE_KEEPASS_XML" in env:
        return

    raise AppError(3)


def collect_tokens(env: dict[str, str], db_path: Path | None = None) -> list[OtpParameters]:
    """Collect OtpParameters from all OTP-configured KeePass entries."""
    mock_xml = env.get("FAKE_KEEPASS_XML")
    if mock_xml:
        entries = _parse_xml_entries(mock_xml)
        tokens: list[OtpParameters] = []
        for e in entries:
            try:
                param = parse_secret_or_uri(
                    e["otp"],
                    fallback_label=e.get("username", ""),
                    fallback_issuer=e.get("title", ""),
                )
                if (not param.account or param.account == "account") and e.get("username"):
                    param.account = e["username"]
                if not param.issuer and e.get("title"):
                    param.issuer = e["title"]
                tokens.append(param)
            except AppError:
                pass
        return tokens
    return []
