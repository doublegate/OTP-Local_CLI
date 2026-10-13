"""High-speed binary CBOR IPC protocol with SO_PEERCRED caller verification."""

import os
import socket
import struct
import sys
from pathlib import Path

try:
    from fido2 import cbor as cbor_engine

    def _dump_float(val: float) -> bytes:
        return struct.pack(">Bd", 0xFB, val)

    def _dump_none(_: None) -> bytes:
        return b"\xf6"

    _orig_load_7 = cbor_engine._DESERIALIZERS.get(7)

    def _load_simple_or_float(ai: int, data: bytes):
        if ai == 20:
            return False, data
        elif ai == 21:
            return True, data
        elif ai == 22:
            return None, data
        elif ai == 26:
            return struct.unpack(">f", data[:4])[0], data[4:]
        elif ai == 27:
            return struct.unpack(">d", data[:8])[0], data[8:]
        if _orig_load_7:
            return _orig_load_7(ai, data)
        return False, data

    if not any(k is float for k, _ in cbor_engine._SERIALIZERS):
        cbor_engine._SERIALIZERS.insert(0, (float, _dump_float))
    if not any(k is type(None) for k, _ in cbor_engine._SERIALIZERS):
        cbor_engine._SERIALIZERS.insert(0, (type(None), _dump_none))
    cbor_engine._DESERIALIZERS[7] = _load_simple_or_float
except ImportError, AttributeError:
    cbor_engine = None

MAX_IPC_MESSAGE_SIZE = 65536  # 64 KiB framing boundary to prevent unbounded buffer attacks


def encode_cbor(data: dict) -> bytes:
    """Encode dictionary payload into binary CBOR format with JSON fallback."""
    if cbor_engine is not None:
        return cbor_engine.encode(data)
    import json

    return json.dumps(data).encode("utf-8")


def decode_cbor(payload: bytes) -> dict:
    """Decode binary CBOR payload into Python dictionary with JSON fallback."""
    if cbor_engine is not None:
        try:
            res = cbor_engine.decode(payload)
            if isinstance(res, dict):
                return res
        except Exception:
            pass
    import json

    return json.loads(payload.decode("utf-8"))


def get_runtime_dir(env: dict[str, str] | None = None) -> Path:
    """Return runtime directory for the active UID with enforced 0700 permissions."""
    e = os.environ if env is None else env
    xdg = e.get("XDG_RUNTIME_DIR")
    if xdg:
        p = Path(xdg)
        if p.exists():
            return p

    uid = os.getuid() if hasattr(os, "getuid") else 1000
    run_user = Path(f"/run/user/{uid}")
    if run_user.exists():
        return run_user

    home = Path(e.get("HOME", Path.home()))
    fallback = home / ".local" / "state" / "authy-local"
    fallback.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        os.chmod(fallback, 0o700)
    except OSError:
        pass
    return fallback


def socket_path(env: dict[str, str] | None = None) -> Path:
    """Return default Unix domain socket path for resident daemon."""
    return get_runtime_dir(env) / "otp-local.sock"


def pid_path(env: dict[str, str] | None = None) -> Path:
    """Return default PID file path for resident daemon."""
    return get_runtime_dir(env) / "otp-local.pid"


def _recv_all(sock: socket.socket, length: int) -> bytes:
    """Read exact number of bytes from socket or return partial on EOF."""
    data = bytearray()
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


def send_framed_message(sock: socket.socket, message: dict, encoding: str = "cbor") -> None:
    """Serialize and transmit 4-byte big-endian length-prefixed message."""
    if encoding == "json":
        import json

        payload = json.dumps(message).encode("utf-8")
    else:
        payload = encode_cbor(message)
    if len(payload) > MAX_IPC_MESSAGE_SIZE:
        raise ValueError(f"Payload size {len(payload)} exceeds maximum {MAX_IPC_MESSAGE_SIZE}")
    header = struct.pack(">I", len(payload))
    sock.sendall(header + payload)


def recv_framed_message(sock: socket.socket, max_bytes: int = MAX_IPC_MESSAGE_SIZE) -> dict | None:
    """Receive and deserialize 4-byte big-endian length-prefixed CBOR message."""
    header = _recv_all(sock, 4)
    if len(header) < 4:
        return None
    (msg_len,) = struct.unpack(">I", header)
    if msg_len == 0 or msg_len > max_bytes:
        raise ValueError(f"Invalid message length: {msg_len}")
    payload = _recv_all(sock, msg_len)
    if len(payload) < msg_len:
        return None
    return decode_cbor(payload)


def verify_peer_credentials(
    sock: socket.socket, expected_uid: int | None = None
) -> tuple[int, int, int]:
    """Inspect socket peer credentials (SO_PEERCRED) and verify caller UID matches."""
    if expected_uid is None and hasattr(os, "getuid"):
        expected_uid = os.getuid()

    caller_pid = 0
    caller_uid = expected_uid if expected_uid is not None else 0
    caller_gid = 0

    if sys.platform.startswith("linux") and hasattr(socket, "SO_PEERCRED"):
        try:
            creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            caller_pid, caller_uid, caller_gid = struct.unpack("3i", creds)
        except OSError as exc:
            raise PermissionError(f"Failed to query SO_PEERCRED: {exc}") from exc

    if expected_uid is not None and caller_uid != expected_uid:
        raise PermissionError(f"Unauthorized caller UID {caller_uid}; expected {expected_uid}")

    return caller_pid, caller_uid, caller_gid


def send_ipc_request(
    request: dict,
    sock_path: Path | None = None,
    timeout: float = 2.0,
    env: dict[str, str] | None = None,
) -> dict | None:
    """Send request to resident daemon via Unix socket and return response dictionary."""
    target_path = sock_path if sock_path is not None else socket_path(env)
    if not target_path.exists():
        return None

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(target_path))
        send_framed_message(client, request)
        return recv_framed_message(client)
    except OSError, ValueError:
        return None
    finally:
        try:
            client.close()
        except OSError:
            pass
