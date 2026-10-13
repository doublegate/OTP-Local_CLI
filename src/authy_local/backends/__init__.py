"""Narrow read-only backend adapters."""

from .local import clear_capability_cache as clear_local_cache
from .onepassword import clear_probe_cache as clear_onepassword_cache


def clear_capability_caches() -> None:
    """Clear all backend capability caches across 1Password and local backends."""
    clear_onepassword_cache()
    clear_local_cache()


__all__ = [
    "clear_capability_caches",
    "clear_local_cache",
    "clear_onepassword_cache",
]
