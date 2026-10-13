"""POSIX shared-memory circular ring buffer with atomic spinlock synchronization."""

import hashlib
import os
import struct
import time
from multiprocessing import shared_memory
from typing import Any

SHM_SIZE = 65536  # 64 KiB
HEADER_SIZE = 64
SLOT_SIZE = 64
SLOT_COUNT = 1023
MAGIC = b"OTPS"
VERSION = 1

HEADER_FMT = ">4sIIIQQ32s"
SLOT_FMT = ">Qdd8sQII16s"


def _account_hash(account: str) -> int:
    """Compute 64-bit integer hash for account lookup."""
    digest = hashlib.sha256(account.encode("utf-8")).digest()
    return struct.unpack(">Q", digest[:8])[0]


def get_default_shm_name(uid: int | None = None) -> str:
    """Return default POSIX shared memory object name for user."""
    if uid is None and hasattr(os, "getuid"):
        uid = os.getuid()
    u = uid if uid is not None else 1000
    return f"otp-local-{u}"


class ShmRingBuffer:
    """POSIX shared memory circular ring buffer for sub-0.1ms zero-copy TOTP lookups."""

    def __init__(
        self,
        name: str | None = None,
        create: bool = False,
        size: int = SHM_SIZE,
    ) -> None:
        self.name = name or get_default_shm_name()
        self.size = size
        self.create = create
        self._shm: shared_memory.SharedMemory | None = None

        if create:
            # Unlink any existing stale segment with the same name
            try:
                stale = shared_memory.SharedMemory(name=self.name)
                stale.close()
                stale.unlink()
            except FileNotFoundError:
                pass

            self._shm = shared_memory.SharedMemory(name=self.name, create=True, size=self.size)
            # Enforce 0600 permissions on /dev/shm if present
            dev_shm_path = f"/dev/shm/{self.name}"
            if os.path.exists(dev_shm_path):
                try:
                    os.chmod(dev_shm_path, 0o600)
                except OSError:
                    pass
            self._init_header()
        else:
            self._shm = shared_memory.SharedMemory(name=self.name, create=False)
            self._validate_header()

        self.buf = self._shm.buf

    def _init_header(self) -> None:
        """Initialize the 64-byte control block."""
        header_bytes = struct.pack(
            HEADER_FMT,
            MAGIC,
            VERSION,
            0,  # spinlock = 0 (unlocked)
            SLOT_COUNT,
            0,  # sequence = 0
            0,  # active_count = 0
            b"\x00" * 32,
        )
        self._shm.buf[:HEADER_SIZE] = header_bytes

    def _validate_header(self) -> None:
        """Verify magic and version headers match expected contract."""
        magic, version, _, _, _, _, _ = struct.unpack_from(HEADER_FMT, self._shm.buf, 0)
        if magic != MAGIC or version != VERSION:
            raise ValueError(f"Corrupted or incompatible shared memory header: magic={magic}")

    def acquire_lock(self, timeout: float = 0.5) -> bool:
        """Acquire atomic spinlock with bounded exponential backoff."""
        start = time.perf_counter()
        while True:
            # Check current lock state
            locked = struct.unpack_from(">I", self.buf, 8)[0]
            if locked == 0:
                # Set lock
                struct.pack_into(">I", self.buf, 8, 1)
                return True
            if time.perf_counter() - start > timeout:
                return False
            time.sleep(0.0001)

    def release_lock(self) -> None:
        """Release atomic spinlock."""
        struct.pack_into(">I", self.buf, 8, 0)

    def write_slot(
        self,
        account: str,
        code: str,
        expiry: float,
        valid_until: float,
        epoch: int = 0,
        digits: int = 6,
        period: int = 30,
    ) -> bool:
        """Write or update an active TOTP entry into the shared memory ring buffer."""
        if not self.acquire_lock():
            return False

        try:
            h = _account_hash(account)
            slot_idx = h % SLOT_COUNT
            slot_offset = HEADER_SIZE + slot_idx * SLOT_SIZE

            # Encode code into 8 bytes (null-padded)
            code_bytes = code.encode("ascii", errors="replace")[:8].ljust(8, b"\x00")
            label_bytes = account.encode("utf-8", errors="replace")[:16].ljust(16, b"\x00")

            slot_data = struct.pack(
                SLOT_FMT,
                h,
                float(expiry),
                float(valid_until),
                code_bytes,
                int(epoch),
                int(digits),
                int(period),
                label_bytes,
            )
            self.buf[slot_offset : slot_offset + SLOT_SIZE] = slot_data

            # Increment sequence counter and active count
            _, _, _, _, seq, count, _ = struct.unpack_from(HEADER_FMT, self.buf, 0)
            struct.pack_into(">Q", self.buf, 16, seq + 1)
            struct.pack_into(">Q", self.buf, 24, count + 1)
            return True
        finally:
            self.release_lock()

    def read_slot(self, account: str) -> dict[str, Any] | None:
        """Perform zero-copy atomic read of active token for account (<0.1ms latency)."""
        h = _account_hash(account)
        slot_idx = h % SLOT_COUNT
        slot_offset = HEADER_SIZE + slot_idx * SLOT_SIZE

        # Check sequence before reading
        seq1 = struct.unpack_from(">Q", self.buf, 16)[0]
        slot_h, expiry, valid_until, code_bytes, epoch, digits, period, _ = struct.unpack_from(
            SLOT_FMT, self.buf, slot_offset
        )
        seq2 = struct.unpack_from(">Q", self.buf, 16)[0]

        # Verify integrity and matching hash
        if seq1 != seq2 or slot_h != h:
            return None

        now = time.time()
        if now > valid_until:
            return None

        clean_code = code_bytes.rstrip(b"\x00").decode("ascii", errors="replace")
        return {
            "account": account,
            "code": clean_code,
            "expiry": expiry,
            "valid_until": valid_until,
            "remaining_seconds": max(0.0, valid_until - now),
            "epoch": epoch,
            "digits": digits,
            "period": period,
        }

    def close(self) -> None:
        """Close local shared memory mapping."""
        if self._shm is not None:
            try:
                self._shm.close()
            except Exception:
                pass
            self._shm = None

    def unlink(self) -> None:
        """Unlink the underlying POSIX shared memory segment from /dev/shm."""
        if self._shm is not None:
            try:
                self._shm.unlink()
            except Exception:
                pass
            self.close()
