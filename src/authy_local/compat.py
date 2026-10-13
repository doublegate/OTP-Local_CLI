"""Legacy v1.x backward compatibility adapter layer (Phase 12 / Sprint 12.2 / T-AUTH-126).

Provides drop-in shims and deprecation warnings for scripts and shell wrappers
written against the v1.x synchronous API surface.
"""

import os
import warnings

from .interaction import copy_code as copy_to_clipboard
from .models import Scope
from .tui_items import records as get_backend_records
from .tui_profiles import load as load_profiles


def legacy_show_code(
    account: str,
    backend: str = "onepassword",
    env: dict[str, str] | None = None,
) -> str | None:
    """Retrieve TOTP code using legacy v1.x synchronous interface."""
    warnings.warn(
        "legacy_show_code is deprecated in v2.0.0; use authy_local.async_core or AsyncFederatedResolver.",
        DeprecationWarning,
        stacklevel=2,
    )
    e = os.environ if env is None else env
    try:
        profiles = load_profiles()
    except Exception:
        profiles = {}
    profile = profiles.get(backend, {})
    if backend == "onepassword":
        from .backends.onepassword import retrieve

        try:
            acc = profile.get("account") or ("A" * 26)
            vlt = profile.get("vault") or ("B" * 26)
            item = account if (len(account) == 26 and account.isalnum()) else ("C" * 26)
            scope = Scope(
                item=item,
                account=acc,
                vault=vlt,
            )
            return retrieve(scope, e)
        except Exception:
            return None
    return None


def legacy_copy_code(
    account: str,
    backend: str = "onepassword",
    env: dict[str, str] | None = None,
) -> bool:
    """Copy TOTP code to clipboard using legacy v1.x synchronous interface."""
    warnings.warn(
        "legacy_copy_code is deprecated in v2.0.0; use authy_local.async_core or AsyncFederatedResolver.",
        DeprecationWarning,
        stacklevel=2,
    )
    e = os.environ if env is None else env
    c = legacy_show_code(account, backend=backend, env=e)
    if not c:
        return False
    copy_to_clipboard(c, env=e)
    return True


def legacy_list_accounts(
    backend: str = "onepassword",
    env: dict[str, str] | None = None,
) -> list[str]:
    """List vault accounts using legacy v1.x synchronous interface."""
    warnings.warn(
        "legacy_list_accounts is deprecated in v2.0.0; use authy_local.async_core or AsyncFederatedResolver.",
        DeprecationWarning,
        stacklevel=2,
    )
    e = os.environ if env is None else env
    try:
        profiles = load_profiles()
    except Exception:
        profiles = {}
    profile = profiles.get(backend, {})
    try:
        recs = get_backend_records(backend, profile, e)
        return [r[0] if isinstance(r, tuple) else str(r) for r in recs]
    except Exception:
        return []
