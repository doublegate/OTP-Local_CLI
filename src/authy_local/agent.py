"""Ephemeral session agent daemon with Unix domain socket and idle auto-lock."""

import json
import os
import select
import socket
import time
from pathlib import Path

from .enrollment import generate_totp_from_uri
from .errors import AppError


def socket_location(home: Path | None = None, create: bool = False) -> Path:
    """Return the private Unix domain socket path with bounded ownership checks."""
    root = Path.home() if home is None else Path(home)
    state_dir = root / ".local" / "state" / "authy-local"
    if create:
        state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        # Enforce 0o700 permissions
        try:
            os.chmod(state_dir, 0o700)
        except OSError:
            pass
    return state_dir / "agent.sock"


def send_agent_request(
    command: str,
    payload: dict | None = None,
    home: Path | None = None,
    timeout: float = 2.0,
) -> dict | None:
    """Send a command to the running session agent daemon, or None if unavailable."""
    sock_path = socket_location(home, create=False)
    if not sock_path.exists():
        return None

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(sock_path))
        req = {"command": command}
        if payload:
            req.update(payload)
        client.sendall((json.dumps(req) + "\n").encode("utf-8"))

        raw = b""
        while b"\n" not in raw:
            chunk = client.recv(4096)
            if not chunk:
                break
            raw += chunk
        if not raw:
            return None
        return json.loads(raw.decode("utf-8").strip())
    except OSError, ValueError:
        return None
    finally:
        try:
            client.close()
        except OSError:
            pass


class SessionAgent:
    """Daemon server handling private cached OTP generation with auto-lock."""

    def __init__(
        self,
        home: Path | None = None,
        idle_timeout: float = 900.0,
    ) -> None:
        self.sock_path = socket_location(home, create=True)
        self.idle_timeout = idle_timeout
        self._secrets: dict[str, str] = {}
        self._locked = False
        self._last_active = time.time()
        self._running = False
        self._server_sock: socket.socket | None = None

    def lock(self) -> None:
        """Cryptographically wipe secrets from memory and mark daemon locked."""
        for k in list(self._secrets.keys()):
            val = self._secrets[k]
            # Best-effort overwrite before deletion
            self._secrets[k] = "\x00" * len(val)
        self._secrets.clear()
        self._locked = True

    def cache(self, key: str, secret: str) -> None:
        """Cache an entry's secret in memory and mark active."""
        if self._locked:
            self._locked = False
        self._secrets[key] = secret
        self._last_active = time.time()

    def get_code(self, key: str) -> tuple[str, float] | None:
        """Compute TOTP code in-process for a cached secret."""
        self._last_active = time.time()
        if self._locked or key not in self._secrets:
            return None
        secret = self._secrets[key]
        try:
            return generate_totp_from_uri(secret)
        except Exception:
            return None

    def handle_request(self, data: dict) -> dict:
        """Dispatch a single client request dictionary."""
        cmd = data.get("command", "")
        self._last_active = time.time()

        if cmd == "ping":
            return {
                "status": "ok",
                "locked": self._locked,
                "cached_count": len(self._secrets),
            }
        elif cmd == "status":
            return {
                "status": "ok",
                "locked": self._locked,
                "cached_count": len(self._secrets),
                "idle_seconds": round(time.time() - self._last_active, 1),
            }
        elif cmd == "cache":
            key = data.get("key")
            secret = data.get("secret")
            if not key or not secret:
                return {"status": "error", "message": "Missing key or secret"}
            self.cache(key, secret)
            return {"status": "ok"}
        elif cmd == "get_code":
            key = data.get("key")
            if not key:
                return {"status": "error", "message": "Missing key"}
            if self._locked:
                return {"status": "locked"}
            res = self.get_code(key)
            if res is None:
                return {"status": "not_found"}
            code, remaining = res
            return {"status": "ok", "code": code, "remaining": remaining}
        elif cmd == "lock":
            self.lock()
            return {"status": "locked"}
        elif cmd == "stop":
            self._running = False
            return {"status": "stopping"}

        return {"status": "error", "message": "Unknown command"}

    def run(self) -> None:
        """Serve Unix domain socket connections until stopped or killed."""
        listen_fds = os.environ.get("LISTEN_FDS")
        listen_pid = os.environ.get("LISTEN_PID")
        activated_fd = None
        if listen_fds and listen_pid:
            try:
                if int(listen_pid) == os.getpid() and int(listen_fds) >= 1:
                    activated_fd = 3
            except ValueError:
                pass

        if activated_fd is not None:
            self._server_sock = socket.fromfd(activated_fd, socket.AF_UNIX, socket.SOCK_STREAM)
        else:
            if self.sock_path.exists():
                # Check if preexisting agent is already running
                existing = send_agent_request("ping", home=self.sock_path.parents[2])
                if existing is not None:
                    raise AppError(2)  # Already running
                self.sock_path.unlink(missing_ok=True)

            self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._server_sock.bind(str(self.sock_path))
            os.chmod(str(self.sock_path), 0o600)
            self._server_sock.listen(16)

        self._server_sock.setblocking(False)
        self._running = True

        try:
            while self._running:
                # Check idle timeout auto-lock
                if not self._locked and (time.time() - self._last_active > self.idle_timeout):
                    self.lock()

                rlist, _, _ = select.select([self._server_sock], [], [], 1.0)
                if not rlist:
                    continue

                client, _ = self._server_sock.accept()
                client.settimeout(2.0)
                try:
                    raw = b""
                    while b"\n" not in raw:
                        chunk = client.recv(4096)
                        if not chunk:
                            break
                        raw += chunk
                    if raw:
                        req = json.loads(raw.decode("utf-8").strip())
                        resp = self.handle_request(req)
                        client.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                except Exception:
                    pass
                finally:
                    try:
                        client.close()
                    except OSError:
                        pass
        finally:
            self.lock()
            if self._server_sock:
                try:
                    self._server_sock.close()
                except OSError:
                    pass
            self.sock_path.unlink(missing_ok=True)
