"""WSL2 (Windows Subsystem for Linux) named pipe and UNIX socket interop bridge."""

import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any

from .errors import AppError


def is_wsl() -> bool:
    """Detect whether current process is running inside WSL (Windows Subsystem for Linux)."""
    if sys.platform != "linux":
        return False
    if "WSL_DISTRO_NAME" in os.environ or "WSL_INTEROP" in os.environ:
        return True
    try:
        proc_version = Path("/proc/version")
        if proc_version.is_file():
            content = proc_version.read_text(encoding="utf-8", errors="replace").lower()
            if "microsoft" in content or "wsl" in content:
                return True
    except OSError:
        pass
    try:
        if Path("/proc/sys/fs/binfmt_misc/WSLInterop").exists():
            return True
    except OSError:
        pass
    return False


def get_bridge_socket_path(env: dict[str, str] | None = None) -> str:
    """Get the communication socket or named pipe path for the WSL bridge."""
    if env is None:
        env = dict(os.environ)

    override = env.get("OTP_LOCAL_BRIDGE_SOCKET")
    if override:
        return override

    user = env.get("USER") or env.get("USERNAME") or "default"
    if sys.platform == "win32":
        return rf"\\.\pipe\otp-local-bridge-{user}"

    # On Linux/WSL, check default UNIX socket path
    return f"/tmp/otp-local-bridge-{user}.sock"


class WslBridgeServer:
    """Server that runs on host Windows (or WSL host bridge) and handles DPAPI queries."""

    def __init__(self, socket_path: str | None = None, env: dict[str, str] | None = None) -> None:
        self.env = dict(env) if env is not None else dict(os.environ)
        self.env["OTP_LOCAL_BRIDGE_SERVER"] = "1"
        self.socket_path = socket_path or get_bridge_socket_path(self.env)
        self._running = False
        self._server_sock: socket.socket | None = None

    def start(self) -> None:
        """Bind and start the listening socket."""
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass

        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock.bind(self.socket_path)
        try:
            os.chmod(self.socket_path, 0o600)
        except OSError:
            pass

        self._server_sock.listen(5)
        self._server_sock.settimeout(1.0)
        self._running = True

    def stop(self) -> None:
        """Stop server and clean up socket file."""
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Dispatch an incoming JSON request to the DPAPI backend."""
        from .backends import dpapi

        action = request.get("action")
        try:
            if action == "ping":
                return {"status": "ok", "message": "pong"}

            if action == "records":
                records = dpapi.dpapi_records(self.env)
                return {"status": "ok", "records": records}

            if action == "code":
                account = request.get("account")
                if not account:
                    return {"status": "error", "error": "Missing account", "exit_code": 2}
                timestamp = request.get("timestamp")
                code = dpapi.dpapi_code(account, self.env, timestamp=timestamp)
                return {"status": "ok", "code": code}

            if action == "enroll":
                account = request.get("account")
                secret = request.get("secret")
                if not account or not secret:
                    return {
                        "status": "error",
                        "error": "Missing account or secret",
                        "exit_code": 2,
                    }
                dpapi.dpapi_enroll(account, secret, self.env)
                return {"status": "ok"}

            if action == "delete":
                account = request.get("account")
                if not account:
                    return {"status": "error", "error": "Missing account", "exit_code": 2}
                dpapi.dpapi_delete(account, self.env)
                return {"status": "ok"}

            return {
                "status": "error",
                "error": f"Unknown action: {action}",
                "exit_code": 2,
            }
        except AppError as exc:
            return {"status": "error", "error": str(exc), "exit_code": exc.exit_code}
        except Exception as exc:
            return {"status": "error", "error": str(exc), "exit_code": 3}

    def serve_one(self) -> bool:
        """Accept and handle a single incoming connection. Returns True if handled, False on timeout."""
        if not self._server_sock or not self._running:
            return False
        try:
            client, _ = self._server_sock.accept()
        except TimeoutError, socket.timeout, OSError:
            return False

        try:
            data = b""
            while not data.endswith(b"\n"):
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk

            if not data:
                return True

            try:
                request = json.loads(data.decode("utf-8", errors="replace").strip())
                response = self.handle_request(request)
            except Exception as exc:
                response = {
                    "status": "error",
                    "error": f"Invalid JSON payload: {exc}",
                    "exit_code": 2,
                }

            out_bytes = json.dumps(response).encode("utf-8") + b"\n"
            client.sendall(out_bytes)
        finally:
            client.close()
        return True


class WslBridgeClient:
    """Client that runs inside WSL2 and relays OTP queries to the host bridge."""

    def __init__(self, socket_path: str | None = None, env: dict[str, str] | None = None) -> None:
        self.env = env or dict(os.environ)
        self.socket_path = socket_path or get_bridge_socket_path(self.env)

    def _send_request(self, request: dict[str, Any], timeout: float = 3.0) -> dict[str, Any]:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(self.socket_path)
            payload = json.dumps(request).encode("utf-8") + b"\n"
            sock.sendall(payload)

            data = b""
            while not data.endswith(b"\n"):
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk

            if not data:
                raise AppError(4)

            resp = json.loads(data.decode("utf-8", errors="replace").strip())
            if resp.get("status") == "ok":
                return resp
            exit_code = resp.get("exit_code", 4)
            raise AppError(exit_code)
        except OSError:
            raise AppError(3) from None
        finally:
            sock.close()

    def ping(self) -> bool:
        """Check if WSL bridge server is reachable."""
        try:
            resp = self._send_request({"action": "ping"}, timeout=1.0)
            return resp.get("status") == "ok"
        except Exception:
            return False

    def get_records(self) -> list[tuple[str, str]]:
        """Retrieve list of enrolled accounts from host Windows DPAPI."""
        resp = self._send_request({"action": "records"})
        records = resp.get("records", [])
        return [
            (str(r[0]), str(r[1])) for r in records if isinstance(r, (list, tuple)) and len(r) >= 2
        ]

    def get_code(self, account: str, timestamp: float | None = None) -> str:
        """Request evaluation of TOTP code for account from host Windows DPAPI."""
        req: dict[str, Any] = {"action": "code", "account": account}
        if timestamp is not None:
            req["timestamp"] = timestamp
        resp = self._send_request(req)
        code = resp.get("code")
        if not code or not isinstance(code, str):
            raise AppError(5)
        return code

    def enroll(self, account: str, secret: str) -> None:
        """Enroll secret into host Windows DPAPI."""
        self._send_request({"action": "enroll", "account": account, "secret": secret})

    def delete(self, account: str) -> None:
        """Delete account from host Windows DPAPI."""
        self._send_request({"action": "delete", "account": account})


def run_bridge_server(socket_path: str | None = None) -> None:
    """Run bridge server in foreground until interrupted."""
    server = WslBridgeServer(socket_path=socket_path)
    server.start()
    try:
        while True:
            server.serve_one()
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
