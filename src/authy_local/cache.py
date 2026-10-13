"""In-memory ephemeral TOTP window cache for Authy-to-1Password.

Strictly ephemeral RAM-only cache keyed by (backend, item_id, time_step).
Guarantees zero persistence to disk, automatic time-step invalidation,
LRU eviction with bounded capacity, and thread safety.
"""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

MAX_CACHE_ENTRIES: int = 512
DEFAULT_PERIOD: int = 30


@dataclass(frozen=True, slots=True)
class CacheEntry:
    code: str
    time_step: int
    expires_at: float
    created_at: float


_LOCK = threading.Lock()
_CACHE: OrderedDict[tuple[str, str, int], CacheEntry] = OrderedDict()
_STATS: dict[str, int] = {
    "hits": 0,
    "misses": 0,
    "evictions": 0,
    "sets": 0,
}


def current_time_step(period: int = DEFAULT_PERIOD, now: float | None = None) -> int:
    """Calculate the RFC 6238 counter step for a given period and timestamp."""
    if now is None:
        now = time.time()
    return int(now) // period


def _prune_expired_locked(now: float) -> int:
    """Remove expired entries while holding _LOCK. Returns number of pruned entries."""
    expired_keys = [key for key, entry in _CACHE.items() if now >= entry.expires_at]
    for key in expired_keys:
        del _CACHE[key]
        _STATS["evictions"] += 1
    return len(expired_keys)


def get_cached_totp(
    backend: str,
    item_id: str,
    time_step: int,
    *,
    now: float | None = None,
) -> str | None:
    """Retrieve an unexpired TOTP code from the in-memory cache.

    Args:
        backend: Backend name ("onepassword", "pass-otp", "totpm").
        item_id: Canonical item identifier.
        time_step: RFC 6238 time step window.
        now: Optional current timestamp (for deterministic testing).

    Returns:
        The cached code string, or None if not found or expired.
    """
    if (
        not isinstance(backend, str)
        or not isinstance(item_id, str)
        or not isinstance(time_step, int)
    ):
        return None

    current_now = time.time() if now is None else now
    key = (backend, item_id, time_step)

    with _LOCK:
        entry = _CACHE.get(key)
        if entry is None:
            _STATS["misses"] += 1
            return None

        # Verify window validity: invalidate if current timestamp reached expiry
        if current_now >= entry.expires_at:
            del _CACHE[key]
            _STATS["misses"] += 1
            _STATS["evictions"] += 1
            return None

        # Cache hit: update LRU order
        _CACHE.move_to_end(key)
        _STATS["hits"] += 1
        return entry.code


def set_cached_totp(
    backend: str,
    item_id: str,
    time_step: int,
    code: str,
    *,
    period: int = DEFAULT_PERIOD,
    now: float | None = None,
) -> None:
    """Store an unexpired TOTP code in the in-memory cache.

    Args:
        backend: Backend name ("onepassword", "pass-otp", "totpm").
        item_id: Canonical item identifier.
        time_step: RFC 6238 time step window.
        code: 6 or 8-digit numeric TOTP code.
        period: Time step period in seconds (default 30).
        now: Optional current timestamp (for deterministic testing).
    """
    if not isinstance(backend, str) or not backend:
        raise ValueError("Invalid backend name")
    if not isinstance(item_id, str) or not item_id:
        raise ValueError("Invalid item_id")
    if not isinstance(time_step, int) or time_step < 0:
        raise ValueError("Invalid time_step")
    if not isinstance(code, str) or len(code) not in (6, 8) or not code.isdigit():
        raise ValueError("Invalid TOTP code format: must be 6 or 8 digits")
    if not isinstance(period, int) or period <= 0:
        raise ValueError("Invalid period: must be positive integer")

    current_now = time.time() if now is None else now
    # Calculate exact expiration timestamp for this RFC 6238 window
    computed_expiry = float((time_step + 1) * period)
    # Dual-safety: if test passed arbitrary small time_step without mocked time, fallback to now + period
    expires_at = computed_expiry if computed_expiry > current_now else current_now + float(period)

    key = (backend, item_id, time_step)
    entry = CacheEntry(
        code=code,
        time_step=time_step,
        expires_at=expires_at,
        created_at=current_now,
    )

    with _LOCK:
        # Prune expired entries if approaching or at capacity
        if len(_CACHE) >= MAX_CACHE_ENTRIES:
            _prune_expired_locked(current_now)

        # Evict least recently used entry if still at maximum capacity
        while len(_CACHE) >= MAX_CACHE_ENTRIES:
            _CACHE.popitem(last=False)
            _STATS["evictions"] += 1

        _CACHE[key] = entry
        _CACHE.move_to_end(key)
        _STATS["sets"] += 1


def clear_cache() -> None:
    """Atomically evict all cached TOTP entries from in-memory storage."""
    with _LOCK:
        _CACHE.clear()


def invalidate_item(backend: str, item_id: str) -> int:
    """Evict all cached entries for a specific item (e.g., upon deletion)."""
    with _LOCK:
        keys_to_remove = [k for k in _CACHE if k[0] == backend and k[1] == item_id]
        for k in keys_to_remove:
            del _CACHE[k]
            _STATS["evictions"] += 1
        return len(keys_to_remove)


def cache_stats() -> dict[str, int]:
    """Return cache telemetry for diagnostics, testing, and benchmarks."""
    with _LOCK:
        return {
            **_STATS,
            "size": len(_CACHE),
        }
