"""Resident UNIX domain socket authentication daemon with locked RAM and SHM ring buffer."""

import concurrent.futures
import os
import select
import signal
import socket
import sys
import threading
import time
from pathlib import Path

from .enrollment import OtpParameters, generate_totp_code, parse_secret_or_uri
from .ipc import (
    pid_path,
    recv_framed_message,
    send_framed_message,
    send_ipc_request,
    socket_path,
    verify_peer_credentials,
)
from .security import (
    SecureBuffer,
    init_runtime_security,
    lock_process_memory,
    secure_zero,
)
from .shm import ShmRingBuffer, get_default_shm_name

__all__ = [
    "DaemonServer",
    "daemon_clean",
    "daemon_reload",
    "daemon_restart",
    "daemon_start",
    "daemon_status",
    "daemon_stop",
    "daemon_systemd_install",
    "generate_systemd_unit",
    "lock_process_memory",
]


def generate_systemd_unit(exec_path: str | None = None) -> str:
    """Generate systemd user service unit definition text."""
    binary = exec_path or "%h/.local/bin/otp-local"
    return f"""[Unit]
Description=OTP-Local Resident Authentication Daemon
Documentation=https://github.com/doublegate/OTP-Local_CLI
After=default.target

[Service]
Type=simple
ExecStart={binary} daemon start --foreground
Restart=on-failure
RestartSec=3s
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=%t %h/.local/state/authy-local
LimitMEMLOCK=infinity

[Install]
WantedBy=default.target
"""


class DaemonServer:
    """High-performance resident daemon managing locked memory caches and SHM ring buffer."""

    def __init__(
        self,
        sock_path: Path | None = None,
        shm_name: str | None = None,
        pid_file: Path | None = None,
        env: dict[str, str] | None = None,
        idle_timeout: float = 900.0,
    ) -> None:
        self.env = env
        self.sock_path = sock_path or socket_path(env)
        self.pid_file = pid_file or pid_path(env)
        self.shm_name = shm_name or get_default_shm_name()
        self.idle_timeout = idle_timeout

        self._cached_tokens: dict[str, OtpParameters] = {}
        self._cached_buffers: dict[str, SecureBuffer] = {}
        self._server_sock: socket.socket | None = None
        self._shm: ShmRingBuffer | None = None
        self._running = False
        self._start_time = 0.0
        self._last_active = 0.0
        self._max_workers = 16
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._cache_lock = threading.Lock()

    def start(self) -> None:
        """Bind socket, initialize shared memory, lock RAM, and enter event loop."""
        self._start_time = time.time()
        self._last_active = self._start_time

        # 1. Initialize process security and lock memory
        init_runtime_security(enable_mlock=True)

        # 2. Initialize Shared Memory Ring Buffer
        self._shm = ShmRingBuffer(name=self.shm_name, create=True)

        # 2b. Initialize ThreadPoolExecutor for concurrent client handling
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="daemon-ipc-worker",
        )

        # 3. Bind UNIX domain socket
        if self.sock_path.exists():
            try:
                self.sock_path.unlink()
            except OSError:
                pass

        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind(str(self.sock_path))
        try:
            os.chmod(self.sock_path, 0o600)
        except OSError:
            pass
        self._server_sock.listen(128)
        self._server_sock.setblocking(False)

        # 4. Write PID file
        self.pid_file.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.pid_file.write_text(f"{os.getpid()}\n", encoding="ascii")
        try:
            os.chmod(self.pid_file, 0o600)
        except OSError:
            pass

        self._running = True

        # Signal handlers
        def _handle_term(signum, frame):
            self._running = False

        def _handle_hup(signum, frame):
            self.flush_cache()

        try:
            signal.signal(signal.SIGTERM, _handle_term)
            signal.signal(signal.SIGINT, _handle_term)
            signal.signal(signal.SIGHUP, _handle_hup)
        except ValueError, AttributeError:
            pass

        self._run_loop()

    def _run_loop(self) -> None:
        """Main event loop processing IPC connections and refreshing SHM slots."""
        last_refresh = 0.0
        while self._running:
            now = time.time()

            # Refresh active tokens in shared memory every 1.0 second
            if now - last_refresh >= 1.0:
                self._refresh_shm(now)
                last_refresh = now

            # Idle timeout auto-flush check
            if self.idle_timeout > 0 and (now - self._last_active > self.idle_timeout):
                if self._cached_tokens:
                    self.flush_cache()

            try:
                rlist, _, _ = select.select([self._server_sock], [], [], 0.5)
            except OSError, ValueError:
                break

            if rlist:
                while self._running:
                    try:
                        conn, _ = self._server_sock.accept()
                    except BlockingIOError, InterruptedError:
                        break
                    except OSError, ValueError:
                        break

                    if self._executor is not None:
                        try:
                            self._executor.submit(self._handle_client, conn)
                        except RuntimeError:
                            try:
                                conn.close()
                            except OSError:
                                pass
                    else:
                        self._handle_client(conn)

        self.cleanup()

    def _handle_client(self, conn: socket.socket) -> None:
        """Process incoming client connection, verify peer credentials, and dispatch request."""
        req_format = "cbor"
        try:
            conn.settimeout(2.0)
            # Verify caller UID
            verify_peer_credentials(conn)

            req = recv_framed_message(conn)
            if not req or not isinstance(req, dict):
                return

            req_format = req.get("format", "cbor")
            action = req.get("action")
            self._last_active = time.time()

            if action == "ping":
                resp = {"status": "ok", "version": 1}
            elif action == "status":
                with self._cache_lock:
                    cached_count = len(self._cached_tokens)
                resp = {
                    "status": "ok",
                    "pid": os.getpid(),
                    "cached_count": cached_count,
                    "uptime": time.time() - self._start_time,
                    "shm_name": self.shm_name,
                }
            elif action == "cache_token":
                resp = self._action_cache_token(req)
            elif action == "get_totp":
                resp = self._action_get_totp(req)
            elif action == "verify_totp":
                resp = self._action_verify_totp(req)
            elif action == "list_tokens":
                with self._cache_lock:
                    accounts = sorted(self._cached_tokens.keys())
                resp = {"status": "ok", "accounts": accounts}
            elif action == "flush_cache":
                self.flush_cache()
                resp = {"status": "ok", "flushed": True}
            else:
                resp = {"status": "error", "message": f"Unknown action: {action}"}

            send_framed_message(conn, resp, encoding=req_format)
        except PermissionError:
            # Unauthorized UID caller - immediately close connection without response
            pass
        except Exception as exc:
            try:
                send_framed_message(
                    conn, {"status": "error", "message": str(exc)}, encoding=req_format
                )
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _action_cache_token(self, req: dict) -> dict:
        """Cache a secret or URI in locked RAM and publish initial TOTP code to SHM."""
        account = req.get("account")
        secret = req.get("secret")
        if not account or not secret:
            return {"status": "error", "message": "Missing account or secret"}

        params = parse_secret_or_uri(
            secret,
            fallback_label=account,
            fallback_issuer=req.get("service", ""),
            digits=req.get("digits", 6),
            period=req.get("period", 30),
            algorithm=req.get("algorithm", "SHA1"),
        )
        sec_bytes = params.secret.encode("utf-8")
        sbuf = SecureBuffer(size=max(len(sec_bytes), 64))
        sbuf.write(sec_bytes)

        with self._cache_lock:
            if account in self._cached_buffers:
                self._cached_buffers[account].close()
            self._cached_buffers[account] = sbuf
            self._cached_tokens[account] = params

        # Immediately update SHM slot
        code, rem = generate_totp_code(params)
        now = time.time()
        if self._shm:
            self._shm.write_slot(
                account=account,
                code=code,
                expiry=now + rem,
                valid_until=now + rem,
                digits=params.digits,
                period=params.period,
            )
        return {"status": "ok", "cached": account}

    def _action_get_totp(self, req: dict) -> dict:
        """Compute and return current TOTP code for cached account."""
        account = req.get("account") or req.get("service")
        if not account:
            return {"status": "error", "message": "Account identifier required"}

        with self._cache_lock:
            params = self._cached_tokens.get(account)
        if not params:
            return {"status": "not_found", "message": f"Token for '{account}' not cached"}

        now = req.get("timestamp") or time.time()
        code, rem = generate_totp_code(params, timestamp=now)
        valid_until = now + rem

        # Update SHM slot
        if self._shm:
            self._shm.write_slot(
                account=account,
                code=code,
                expiry=valid_until,
                valid_until=valid_until,
                digits=params.digits,
                period=params.period,
            )

        return {
            "status": "ok",
            "code": code,
            "valid_until": valid_until,
            "remaining_seconds": rem,
        }

    def _action_verify_totp(self, req: dict) -> dict:
        """Verify given TOTP code against cached token within ±1 step window."""
        account = req.get("account") or req.get("service")
        submitted_code = str(req.get("code", "")).strip().replace(" ", "")
        if not account or not submitted_code:
            return {"status": "error", "message": "Account and code required"}

        with self._cache_lock:
            params = self._cached_tokens.get(account)
        if not params:
            return {"status": "not_found", "message": f"Token for '{account}' not cached"}

        now = req.get("timestamp") or time.time()
        period = params.period

        # Check current step, step - 1, step + 1 (±30s window)
        matched = False
        for delta in (0, -period, period):
            cand_code, _ = generate_totp_code(params, timestamp=now + delta)
            if cand_code == submitted_code:
                matched = True
                break

        return {"status": "ok", "valid": matched}

    def _refresh_shm(self, now: float) -> None:
        """Iterate all cached tokens and refresh active codes in SHM."""
        if not self._shm:
            return
        with self._cache_lock:
            items = list(self._cached_tokens.items())
        for acct, params in items:
            try:
                code, rem = generate_totp_code(params, timestamp=now)
                self._shm.write_slot(
                    account=acct,
                    code=code,
                    expiry=now + rem,
                    valid_until=now + rem,
                    digits=params.digits,
                    period=params.period,
                )
            except Exception:
                pass

    def flush_cache(self) -> None:
        """Cryptographically zero memory and clear all cached tokens."""
        with self._cache_lock:
            # 1. Zero and close all active SecureBuffers
            for sbuf in self._cached_buffers.values():
                try:
                    sbuf.close()
                except Exception:
                    pass
            self._cached_buffers.clear()

            # 2. Clear token secret references and dictionary
            for acct in list(self._cached_tokens.keys()):
                params = self._cached_tokens[acct]
                params.secret = ""
            self._cached_tokens.clear()

        # 3. Securely zero shared memory ring buffer slots and re-init header
        if self._shm:
            try:
                buf = getattr(self._shm, "buf", None)
                if buf is not None and not getattr(buf, "released", False):
                    secure_zero(buf)
            except ValueError, BufferError, AttributeError, Exception:
                pass
            try:
                self._shm._init_header()
            except ValueError, BufferError, AttributeError, Exception:
                pass

    def cleanup(self) -> None:
        """Clean up process resources, unlinking socket, PID file, and SHM segment."""
        self.flush_cache()

        if self._executor is not None:
            try:
                self._executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            self._executor = None

        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None

        if self.sock_path.exists():
            try:
                self.sock_path.unlink()
            except OSError:
                pass

        if self.pid_file.exists():
            try:
                self.pid_file.unlink()
            except OSError:
                pass

        if self._shm is not None:
            self._shm.unlink()
            self._shm = None


def daemon_start(foreground: bool = False, env: dict[str, str] | None = None) -> int:
    """Start the resident background daemon or run in foreground with stale PID recovery."""
    s_path = socket_path(env)
    p_path = pid_path(env)

    # Robust stale PID & socket detection
    if p_path.exists():
        is_stale = False
        pid = None
        try:
            raw_pid = p_path.read_text(encoding="ascii").strip()
            pid = int(raw_pid)
            if pid <= 0:
                raise ValueError("Invalid non-positive PID")
            try:
                os.kill(pid, 0)
                # Process is active
                ping_resp = send_ipc_request({"action": "ping"}, sock_path=s_path, timeout=1.0)
                if ping_resp and ping_resp.get("status") == "ok":
                    sys.stdout.write(f"OTP-Local daemon is already running (PID {pid}).\n")
                    return 0
                else:
                    sys.stderr.write(
                        f"Warning: Process {pid} is active but daemon socket is unresponsive.\n"
                    )
                    return 1
            except ProcessLookupError:
                # Dead process
                is_stale = True
            except PermissionError:
                sys.stderr.write(f"Warning: Daemon PID {pid} is running under another user.\n")
                return 1
        except ValueError, OSError:
            is_stale = True

        if is_stale:
            stale_desc = f"process {pid}" if pid and pid > 0 else "corrupted PID"
            sys.stderr.write(
                f"Warning: Cleaning up stale PID file ({stale_desc} is not running).\n"
            )
            try:
                p_path.unlink()
            except OSError:
                pass
            if s_path.exists():
                try:
                    s_path.unlink()
                except OSError:
                    pass

    if foreground:
        server = DaemonServer(sock_path=s_path, pid_file=p_path, env=env)
        sys.stdout.write(f"Starting OTP-Local daemon in foreground (PID {os.getpid()})...\n")
        sys.stdout.flush()
        server.start()
        return 0

    # Double-fork daemonization
    if os.fork() > 0:
        # Parent returns
        return 0

    os.setsid()

    if os.fork() > 0:
        os._exit(0)

    # Redirect standard file descriptors
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    os.close(devnull)

    server = DaemonServer(sock_path=s_path, pid_file=p_path, env=env)
    server.start()
    return 0


def daemon_stop(env: dict[str, str] | None = None) -> int:
    """Signal and stop the running resident daemon process, cleaning stale artifacts if dead."""
    p_path = pid_path(env)
    s_path = socket_path(env)

    if not p_path.exists():
        if s_path.exists():
            try:
                s_path.unlink()
            except OSError:
                pass
        sys.stdout.write("OTP-Local daemon is not running (no PID file).\n")
        return 0

    try:
        raw_pid = p_path.read_text(encoding="ascii").strip()
        pid = int(raw_pid)
        if pid <= 0:
            raise ValueError("Invalid non-positive PID")
    except ValueError, OSError:
        try:
            p_path.unlink()
        except OSError:
            pass
        if s_path.exists():
            try:
                s_path.unlink()
            except OSError:
                pass
        sys.stdout.write("Removed corrupted PID file. Daemon is not running.\n")
        return 0

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        try:
            p_path.unlink()
        except OSError:
            pass
        if s_path.exists():
            try:
                s_path.unlink()
            except OSError:
                pass
        sys.stdout.write(
            f"Daemon process {pid} is no longer running. Cleaned up stale PID and socket files.\n"
        )
        return 0
    except PermissionError:
        sys.stderr.write(f"Permission denied stopping daemon process {pid}.\n")
        return 3
    except OSError as exc:
        sys.stderr.write(f"Error stopping daemon: {exc}\n")
        return 3

    # Wait up to 5 seconds for daemon to terminate
    for _ in range(50):
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except OSError:
            break
    else:
        # Force kill if still active
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    if p_path.exists():
        try:
            p_path.unlink()
        except OSError:
            pass
    if s_path.exists():
        try:
            s_path.unlink()
        except OSError:
            pass

    sys.stdout.write(f"OTP-Local daemon (PID {pid}) stopped.\n")
    return 0


def daemon_clean(env: dict[str, str] | None = None) -> int:
    """Detect and clean up stale PID files and orphaned socket bindings."""
    p_path = pid_path(env)
    s_path = socket_path(env)
    cleaned_any = False

    if p_path.exists():
        try:
            raw_pid = p_path.read_text(encoding="ascii").strip()
            pid = int(raw_pid)
            if pid <= 0:
                raise ValueError("Invalid non-positive PID")
            try:
                os.kill(pid, 0)
                # Process is actively running
                ping_resp = send_ipc_request({"action": "ping"}, sock_path=s_path, timeout=1.0)
                if ping_resp and ping_resp.get("status") == "ok":
                    sys.stdout.write(
                        f"Cannot clean: OTP-Local daemon is actively running (PID {pid}).\n"
                    )
                    return 1
                else:
                    sys.stdout.write(f"Warning: Process {pid} is running but unresponsive.\n")
                    return 1
            except ProcessLookupError:
                try:
                    p_path.unlink()
                except OSError:
                    pass
                sys.stdout.write(f"Removed stale PID file: {p_path} (PID {pid} was dead)\n")
                cleaned_any = True
            except PermissionError:
                sys.stdout.write(f"Cannot clean: PID {pid} is owned by another user.\n")
                return 1
        except ValueError, OSError:
            try:
                p_path.unlink()
            except OSError:
                pass
            sys.stdout.write(f"Removed corrupted PID file: {p_path}\n")
            cleaned_any = True

    if s_path.exists():
        ping_resp = send_ipc_request({"action": "ping"}, sock_path=s_path, timeout=0.5)
        if ping_resp and ping_resp.get("status") == "ok":
            sys.stdout.write(f"Socket {s_path} is active. Daemon is listening.\n")
        else:
            try:
                s_path.unlink()
            except OSError:
                pass
            sys.stdout.write(f"Removed orphaned socket file: {s_path}\n")
            cleaned_any = True

    if not cleaned_any:
        sys.stdout.write("No stale daemon artifacts found.\n")
    return 0


def daemon_restart(foreground: bool = False, env: dict[str, str] | None = None) -> int:
    """Gracefully stop running daemon (if active) and start fresh daemon instance."""
    p_path = pid_path(env)
    if p_path.exists():
        daemon_stop(env=env)
        time.sleep(0.2)
    return daemon_start(foreground=foreground, env=env)


def daemon_status(env: dict[str, str] | None = None) -> int:
    """Query and display active status of the resident daemon."""
    p_path = pid_path(env)
    s_path = socket_path(env)

    if not p_path.exists():
        sys.stdout.write("Status: inactive (daemon is not running)\n")
        return 0

    try:
        pid = int(p_path.read_text(encoding="ascii").strip())
        if pid <= 0:
            raise ValueError("Invalid non-positive PID")
        os.kill(pid, 0)
    except ValueError, OSError:
        sys.stdout.write("Status: dead (stale PID file exists)\n")
        return 0

    resp = send_ipc_request({"action": "status"}, sock_path=s_path, timeout=2.0)
    if resp and resp.get("status") == "ok":
        uptime = int(resp.get("uptime", 0))
        cached = resp.get("cached_count", 0)
        shm = resp.get("shm_name", "none")
        sys.stdout.write(
            f"Status: active (running)\n"
            f"PID: {pid}\n"
            f"Socket: {s_path}\n"
            f"Shared Memory: /dev/shm/{shm}\n"
            f"Cached Tokens: {cached}\n"
            f"Uptime: {uptime}s\n"
        )
        return 0
    sys.stdout.write(f"Status: unresponsive (PID {pid} active but socket not responding)\n")
    return 1


def daemon_reload(env: dict[str, str] | None = None) -> int:
    """Reload daemon configuration and flush cached token secrets."""
    s_path = socket_path(env)
    resp = send_ipc_request({"action": "flush_cache"}, sock_path=s_path, timeout=2.0)
    if resp and resp.get("status") == "ok":
        sys.stdout.write("OTP-Local daemon cache flushed and reloaded.\n")
        return 0
    sys.stderr.write("Failed to reload daemon (daemon unreachable).\n")
    return 3


def daemon_systemd_install(env: dict[str, str] | None = None) -> int:
    """Write systemd user unit to ~/.config/systemd/user/otp-local.service and run daemon-reload."""
    e = os.environ if env is None else env
    home = Path(e.get("HOME", Path.home()))
    unit_dir = home / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_file = unit_dir / "otp-local.service"

    unit_content = generate_systemd_unit()
    unit_file.write_text(unit_content, encoding="utf-8")
    sys.stdout.write(f"Wrote systemd user unit to {unit_file}\n")

    # Run systemctl --user daemon-reload if systemctl exists
    import shutil

    systemctl = shutil.which("systemctl")
    if systemctl:
        from .processes import run

        run([systemctl, "--user", "daemon-reload"], timeout=5)
        sys.stdout.write("Executed systemctl --user daemon-reload successfully.\n")
        sys.stdout.write("Enable with: systemctl --user enable --now otp-local.service\n")

    return 0
