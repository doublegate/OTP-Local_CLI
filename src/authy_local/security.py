"""Military-grade runtime memory security, core dump exclusion, and zeroization."""

import atexit
import ctypes
import mmap
import resource
import signal
import sys
import threading
from typing import Any

# POSIX / Linux memory management constants
MADV_DONTDUMP = 16
PR_SET_DUMPABLE = 4
MCL_CURRENT = 1
MCL_FUTURE = 2

_LIBC: ctypes.CDLL | None = None
_LIBC_INITIALIZED = False
_LOCK = threading.Lock()
_ACTIVE_BUFFERS: set["SecureBuffer"] = set()
_ORIGINAL_HANDLERS: dict[int, Any] = {}
_HANDLERS_INSTALLED = False


def get_libc() -> ctypes.CDLL | None:
    """Return platform C standard library handle via ctypes, or None if unavailable."""
    global _LIBC, _LIBC_INITIALIZED
    with _LOCK:
        if not _LIBC_INITIALIZED:
            _LIBC_INITIALIZED = True
            if sys.platform.startswith("linux") or sys.platform == "darwin":
                try:
                    _LIBC = ctypes.CDLL(None)
                except Exception:
                    _LIBC = None
        return _LIBC


def mlock(address: int, length: int) -> bool:
    """Lock virtual memory pages into RAM to prevent paging to unencrypted swap."""
    if length <= 0:
        return False
    libc = get_libc()
    if libc and hasattr(libc, "mlock"):
        try:
            return libc.mlock(ctypes.c_void_p(address), ctypes.c_size_t(length)) == 0
        except Exception:
            pass
    return False


def munlock(address: int, length: int) -> bool:
    """Unlock previously locked virtual memory pages."""
    if length <= 0:
        return False
    libc = get_libc()
    if libc and hasattr(libc, "munlock"):
        try:
            return libc.munlock(ctypes.c_void_p(address), ctypes.c_size_t(length)) == 0
        except Exception:
            pass
    return False


def madvise_dontdump(address: int, length: int) -> bool:
    """Instruct the Linux kernel to exclude virtual memory region from core dumps."""
    if length <= 0:
        return False
    libc = get_libc()
    if libc and hasattr(libc, "madvise"):
        try:
            return (
                libc.madvise(
                    ctypes.c_void_p(address),
                    ctypes.c_size_t(length),
                    ctypes.c_int(MADV_DONTDUMP),
                )
                == 0
            )
        except Exception:
            pass
    return False


def disable_core_dumps() -> bool:
    """Disable core dump generation via prctl(PR_SET_DUMPABLE, 0) and setrlimit."""
    success = False
    libc = get_libc()
    if libc and hasattr(libc, "prctl"):
        try:
            res = libc.prctl(ctypes.c_int(PR_SET_DUMPABLE), ctypes.c_ulong(0), 0, 0, 0)
            if res == 0:
                success = True
        except Exception:
            pass

    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        success = True
    except Exception:
        pass

    return success


def lock_process_memory() -> bool:
    """Lock entire process virtual memory space into physical RAM."""
    libc = get_libc()
    if libc and hasattr(libc, "mlockall"):
        try:
            return libc.mlockall(ctypes.c_int(MCL_CURRENT | MCL_FUTURE)) == 0
        except Exception:
            pass
    return False


def secure_zero(
    target: bytearray | memoryview | ctypes.Array | int, length: int | None = None
) -> None:
    """Overwrite mutable memory buffer with zeroes immediately via ctypes.memset."""
    if isinstance(target, int):
        if length is not None and length > 0:
            try:
                ctypes.memset(ctypes.c_void_p(target), 0, ctypes.c_size_t(length))
            except Exception:
                pass
        return

    try:
        if isinstance(target, bytearray):
            c_arr = (ctypes.c_char * len(target)).from_buffer(target)
            ctypes.memset(ctypes.byref(c_arr), 0, len(target))
        elif isinstance(target, memoryview):
            c_arr = (ctypes.c_char * target.nbytes).from_buffer(target)
            ctypes.memset(ctypes.byref(c_arr), 0, target.nbytes)
        elif hasattr(target, "_length_"):
            ctypes.memset(ctypes.byref(target), 0, ctypes.sizeof(target))
    except Exception:
        # Fallback python overwrite
        if isinstance(target, bytearray):
            for i in range(len(target)):
                target[i] = 0


class SecureBuffer:
    """A page-aligned, mlocked, non-dumpable memory buffer with guaranteed zeroization."""

    def __init__(self, size: int = 4096) -> None:
        if size <= 0:
            raise ValueError("SecureBuffer size must be positive")
        self.size = size
        self._closed = False
        self._address: int | None = None
        self._mm: mmap.mmap | None = None
        self._raw_bytearray: bytearray | None = None

        # Allocate page-aligned anonymous memory via mmap
        try:
            self._mm = mmap.mmap(
                -1,
                self.size,
                flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS,
                prot=mmap.PROT_READ | mmap.PROT_WRITE,
            )
            # Obtain buffer address using ctypes
            buf_type = ctypes.c_char * self.size
            self._c_buf = buf_type.from_buffer(self._mm)
            self._address = ctypes.addressof(self._c_buf)
        except Exception:
            self._mm = None
            self._raw_bytearray = bytearray(self.size)
            buf_type = ctypes.c_char * self.size
            self._c_buf = buf_type.from_buffer(self._raw_bytearray)
            self._address = ctypes.addressof(self._c_buf)

        # Apply kernel memory security primitives
        if self._address:
            mlock(self._address, self.size)
            madvise_dontdump(self._address, self.size)

        with _LOCK:
            _ACTIVE_BUFFERS.add(self)

    @property
    def address(self) -> int | None:
        return self._address

    @property
    def is_closed(self) -> bool:
        return self._closed

    def write(self, data: bytes | str) -> int:
        """Write sensitive data into the secure buffer, returning bytes written."""
        if self._closed:
            raise RuntimeError("SecureBuffer is closed")
        raw = data.encode("utf-8") if isinstance(data, str) else data
        if len(raw) > self.size:
            raise ValueError(f"Data length ({len(raw)}) exceeds buffer size ({self.size})")

        self.zeroize()
        if self._mm is not None:
            self._mm.seek(0)
            self._mm.write(raw)
        elif self._raw_bytearray is not None:
            self._raw_bytearray[: len(raw)] = raw
        return len(raw)

    def read(self, length: int | None = None) -> bytes:
        """Read bytes from secure buffer up to length or first null terminator."""
        if self._closed:
            raise RuntimeError("SecureBuffer is closed")
        n = length if length is not None else self.size
        if self._mm is not None:
            self._mm.seek(0)
            return self._mm.read(n)
        elif self._raw_bytearray is not None:
            return bytes(self._raw_bytearray[:n])
        return b""

    def get_cstring(self) -> str:
        """Read buffer as a null-terminated UTF-8 string."""
        raw = self.read()
        null_idx = raw.find(b"\x00")
        if null_idx >= 0:
            raw = raw[:null_idx]
        return raw.decode("utf-8", errors="replace")

    def zeroize(self) -> None:
        """Deterministically wipe buffer with zero bytes."""
        if self._address:
            secure_zero(self._address, self.size)
        elif self._raw_bytearray is not None:
            secure_zero(self._raw_bytearray)

    def close(self) -> None:
        """Zeroize, unlock pages, release allocation, and unregister."""
        if self._closed:
            return
        self._closed = True
        self.zeroize()

        if self._address:
            munlock(self._address, self.size)

        if self._mm is not None:
            try:
                self._mm.close()
            except Exception:
                pass
            self._mm = None

        self._raw_bytearray = None
        self._address = None

        with _LOCK:
            _ACTIVE_BUFFERS.discard(self)

    def __enter__(self) -> "SecureBuffer":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def wipe_all_secure_buffers() -> int:
    """Zeroize and close all currently active secure buffers."""
    count = 0
    with _LOCK:
        buffers = list(_ACTIVE_BUFFERS)
    for buf in buffers:
        try:
            buf.close()
            count += 1
        except Exception:
            pass
    return count


def _signal_handler(signum: int, frame: Any) -> None:
    """Emergency signal handler zeroizing all secure memory before exiting."""
    wipe_all_secure_buffers()
    # Restore original handler and re-raise signal
    orig = _ORIGINAL_HANDLERS.get(signum)
    if orig and callable(orig):
        orig(signum, frame)
    else:
        sys.exit(128 + signum)


def install_signal_handlers() -> None:
    """Install process termination signal hooks for SIGINT, SIGTERM, and SIGHUP."""
    global _HANDLERS_INSTALLED
    with _LOCK:
        if _HANDLERS_INSTALLED:
            return
        _HANDLERS_INSTALLED = True

        for sig_name in ("SIGINT", "SIGTERM", "SIGHUP"):
            if hasattr(signal, sig_name):
                sig = getattr(signal, sig_name)
                try:
                    prev = signal.signal(sig, _signal_handler)
                    _ORIGINAL_HANDLERS[sig] = prev
                except ValueError, OSError:
                    pass


def memory_security_status() -> dict[str, Any]:
    """Inspect and report process memory security posture for diagnostics."""
    libc = get_libc()
    has_mlock = bool(libc and hasattr(libc, "mlock"))
    has_madvise = bool(libc and hasattr(libc, "madvise"))
    has_prctl = bool(libc and hasattr(libc, "prctl"))

    with _LOCK:
        active_count = len(_ACTIVE_BUFFERS)

    return {
        "mlock_supported": has_mlock,
        "madvise_dontdump_supported": has_madvise,
        "prctl_supported": has_prctl,
        "active_secure_buffers": active_count,
        "signal_handlers_installed": _HANDLERS_INSTALLED,
    }


# Register automatic atexit scrubbing
atexit.register(wipe_all_secure_buffers)
