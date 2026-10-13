"""Narrow read-only backend adapters."""

from .bitwarden import session_manager as bitwarden_session_manager
from .keepass import session_manager as keepass_session_manager
from .local import clear_capability_cache as clear_local_cache
from .onepassword import clear_probe_cache as clear_onepassword_cache


def clear_capability_caches() -> None:
    """Clear all backend capability caches across 1Password, Bitwarden, KeePass, and local backends."""
    clear_onepassword_cache()
    clear_local_cache()
    bitwarden_session_manager.clear_session()
    keepass_session_manager.clear()


__all__ = [
    "bitwarden_session_manager",
    "clear_capability_caches",
    "clear_local_cache",
    "clear_onepassword_cache",
    "keepass_session_manager",
]
