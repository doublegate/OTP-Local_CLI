"""POSIX shared-memory circular ring buffer with atomic spinlock and seqlock synchronization."""

import hashlib
import os
import struct
import threading
import time
from multiprocessing import shared_memory
from typing import Any

try:
    import fcntl
except ImportError:
    fcntl = None  # Non-POSIX fallback

SHM_SIZE = 65536  # 64 KiB
HEADER_SIZE = 64
SLOT_SIZE = 64
SLOT_COUNT = 1023
MAX_PROBE = 16
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
        self._instance_lock = threading.Lock()

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
            0,  # sequence = 0 (even)
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
        """Acquire atomic lock with bounded exponential backoff across processes and threads."""
        start = time.perf_counter()
        if not self._instance_lock.acquire(timeout=timeout):
            return False

        remaining = timeout - (time.perf_counter() - start)
        if remaining <= 0:
            self._instance_lock.release()
            return False

        fd = getattr(self._shm, "_fd", None) if self._shm else None
        backoff = 0.00005
        max_backoff = 0.002

        while True:
            locked = False
            if fcntl is not None and fd is not None and fd >= 0:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                except BlockingIOError, OSError:
                    locked = False
            else:
                cur = struct.unpack_from(">I", self.buf, 8)[0]
                if cur == 0:
                    locked = True

            if locked:
                try:
                    struct.pack_into(">I", self.buf, 8, 1)
                except Exception:
                    pass
                return True

            if time.perf_counter() - start >= timeout:
                self._instance_lock.release()
                return False

            time.sleep(backoff)
            backoff = min(backoff * 1.5, max_backoff)

    def release_lock(self) -> None:
        """Release atomic lock."""
        try:
            struct.pack_into(">I", self.buf, 8, 0)
        except Exception:
            pass

        fd = getattr(self._shm, "_fd", None) if self._shm else None
        if fcntl is not None and fd is not None and fd >= 0:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass

        if self._instance_lock.locked():
            try:
                self._instance_lock.release()
            except RuntimeError:
                pass

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
            base_idx = h % SLOT_COUNT

            # Collision probing (linear probing up to MAX_PROBE)
            target_idx = None
            first_empty_idx = None
            oldest_expired_idx = None
            oldest_expiry = float("inf")
            now = time.time()

            for probe in range(MAX_PROBE):
                idx = (base_idx + probe) % SLOT_COUNT
                offset = HEADER_SIZE + idx * SLOT_SIZE
                slot_h, _, s_valid = struct.unpack_from(">Qdd", self.buf, offset)
                if slot_h == h:
                    target_idx = idx
                    break
                if slot_h == 0 and first_empty_idx is None:
                    first_empty_idx = idx
                elif s_valid < now and s_valid < oldest_expiry:
                    oldest_expired_idx = idx
                    oldest_expiry = s_valid

            is_new_slot = False
            if target_idx is not None:
                slot_idx = target_idx
            elif first_empty_idx is not None:
                slot_idx = first_empty_idx
                is_new_slot = True
            elif oldest_expired_idx is not None:
                slot_idx = oldest_expired_idx
            else:
                slot_idx = base_idx

            slot_offset = HEADER_SIZE + slot_idx * SLOT_SIZE

            # Seqlock Protocol: Step 1 - Make sequence ODD before write
            seq = struct.unpack_from(">Q", self.buf, 16)[0]
            seq_odd = seq + 1 if (seq % 2 == 0) else seq + 2
            struct.pack_into(">Q", self.buf, 16, seq_odd)

            # Step 2: Write slot buffer data
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

            # Step 3: Increment active count only on newly claimed slots
            if is_new_slot:
                count = struct.unpack_from(">Q", self.buf, 24)[0]
                struct.pack_into(">Q", self.buf, 24, min(count + 1, SLOT_COUNT))

            # Seqlock Protocol: Step 4 - Make sequence EVEN after write
            seq_even = seq_odd + 1
            struct.pack_into(">Q", self.buf, 16, seq_even)
            return True
        finally:
            self.release_lock()

    def read_slot(self, account: str) -> dict[str, Any] | None:
        """Perform zero-copy atomic read of active token for account (<0.1ms latency)."""
        h = _account_hash(account)
        base_idx = h % SLOT_COUNT

        for _ in range(3):  # Retry up to 3 times on seqlock collision
            # Seqlock Check: Sequence MUST be even before reading
            seq1 = struct.unpack_from(">Q", self.buf, 16)[0]
            if seq1 % 2 != 0:
                time.sleep(0.00005)
                continue

            for probe in range(MAX_PROBE):
                slot_idx = (base_idx + probe) % SLOT_COUNT
                slot_offset = HEADER_SIZE + slot_idx * SLOT_SIZE

                slot_h = struct.unpack_from(">Q", self.buf, slot_offset)[0]
                if slot_h == 0:
                    return None  # Unoccupied slot, account definitely not present

                if slot_h == h:
                    (
                        _,
                        expiry,
                        valid_until,
                        code_bytes,
                        epoch,
                        digits,
                        period,
                        _,
                    ) = struct.unpack_from(SLOT_FMT, self.buf, slot_offset)

                    # Seqlock Check: Sequence MUST match seq1 and be even after reading
                    seq2 = struct.unpack_from(">Q", self.buf, 16)[0]
                    if seq1 != seq2 or seq2 % 2 != 0:
                        break  # Write occurred during read, retry outer loop

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
            time.sleep(0.00005)

        return None

    @property
    def sequence(self) -> int:
        """Return current seqlock sequence counter."""
        return struct.unpack_from(">Q", self.buf, 16)[0]

    @property
    def active_count(self) -> int:
        """Return current active slot count."""
        return struct.unpack_from(">Q", self.buf, 24)[0]

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
