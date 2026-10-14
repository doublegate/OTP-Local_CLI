"""Federated multi-vault resolver offering unified cross-backend token aggregation and search."""

import concurrent.futures
import re
from dataclasses import dataclass, field
from pathlib import Path

from .errors import AppError

BACKEND_BADGES: dict[str, str] = {
    "onepassword": "1P",
    "bitwarden": "BW",
    "keepass": "KP",
    "pass-otp": "PASS",
    "totpm": "TOTP",
    "keychain": "KC",
    "dpapi": "DP",
    "fido2": "FIDO2",
    "yubikey": "YK",
    "tpm2-totp": "TPM2",
}

ALL_SUPPORTED_BACKENDS = [
    "fido2",
    "keychain",
    "dpapi",
    "keepass",
    "bitwarden",
    "pass-otp",
    "totpm",
    "onepassword",
    "yubikey",
    "tpm2-totp",
]


@dataclass
class FederatedToken:
    """A unified token representation resolved across one or more vault backends."""

    key: str
    title: str
    backends: list[str] = field(default_factory=list)
    badge: str = ""
    display_label: str = ""
    backend_keys: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.backend_keys and self.backends:
            self.backend_keys = {self.backends[0]: self.key}
        elif self.backend_keys and not self.backends:
            self.backends = list(self.backend_keys.keys())

        if not self.badge and self.backends:
            short_badges = [BACKEND_BADGES.get(b, b.upper()) for b in self.backends]
            self.badge = f"[{'+'.join(short_badges)}]"
        if not self.display_label:
            self.display_label = f"{self.title} {self.badge}".strip()


def _normalize_title(raw_title: str) -> str:
    """Normalize token title by stripping trailing backend indicators and brackets."""
    cleaned = re.sub(r"\s*\[[^\]]+\]\s*$", "", raw_title).strip()
    return cleaned


def _fetch_records_for_backend(backend: str, env: dict[str, str]) -> list[tuple[str, str, str]]:
    """Fetch records for a single backend, returning (backend, item_id, title) tuples."""
    results: list[tuple[str, str, str]] = []
    try:
        if backend == "bitwarden":
            from .backends import bitwarden

            records = bitwarden.bitwarden_records(env)
            for item_id, label in records:
                results.append((backend, item_id, _normalize_title(label)))
        elif backend == "keepass":
            from .backends import keepass

            records = keepass.keepass_records(env)
            for item_id, label in records:
                results.append((backend, item_id, _normalize_title(label)))
        elif backend == "fido2":
            from .backends import fido2

            records = fido2.fido2_records(env)
            for item_id, label in records:
                results.append((backend, item_id, _normalize_title(label)))
        elif backend == "keychain":
            from .backends import keychain

            records = keychain.keychain_records(env)
            for item_id, label in records:
                results.append((backend, item_id, _normalize_title(label)))
        elif backend == "dpapi":
            from .backends import dpapi

            records = dpapi.dpapi_records(env)
            for item_id, label in records:
                results.append((backend, item_id, _normalize_title(label)))
        elif backend == "yubikey":
            from .backends import hardware

            records = hardware.yubikey_records(env)
            for item_id, label in records:
                results.append((backend, item_id, _normalize_title(label)))
        elif backend == "tpm2-totp":
            from .backends import hardware

            records = hardware.tpm2_totp_records(env)
            for item_id, label in records:
                results.append((backend, item_id, _normalize_title(label)))
        elif backend == "onepassword":
            from .backends import onepassword
            from .interaction import list_items
            from .tui_profiles import load as load_profiles

            if hasattr(onepassword, "onepassword_records"):
                records = onepassword.onepassword_records(env)
            else:
                home = Path(env["HOME"]) if "HOME" in env else None
                try:
                    profiles = load_profiles(home=home)
                except Exception:
                    profiles = {}
                prof = profiles.get("onepassword", {})
                account = prof.get("account") or env.get("OP_ACCOUNT")
                vault = prof.get("vault") or env.get("OP_VAULT")
                tag = prof.get("tag", "OTP")
                records = list_items(account, vault, env, tag=tag) if account and vault else []
            for item_id, label in records:
                results.append((backend, item_id, _normalize_title(label)))
        elif backend == "pass-otp":
            from .backends import local
            from .tui_profiles import load as load_profiles

            if hasattr(local, "pass_otp_records"):
                records = local.pass_otp_records(env)
            else:
                home = Path(env["HOME"]) if "HOME" in env else None
                try:
                    profiles = load_profiles(home=home)
                except Exception:
                    profiles = {}
                prof = profiles.get("pass-otp", {})
                store = prof.get("store") or env.get("PASSWORD_STORE_DIR")
                key_home = prof.get("key_home") or env.get("GNUPGHOME")
                records = (
                    local.records(
                        local.LocalScope(backend="pass-otp", store=store, key_home=key_home), env
                    )
                    if store and key_home
                    else []
                )
            for item_id, label in records:
                results.append((backend, item_id, _normalize_title(label)))
        elif backend == "totpm":
            from .backends import local
            from .tui_profiles import load as load_profiles

            if hasattr(local, "totpm_records"):
                records = local.totpm_records(env)
            else:
                home = Path(env["HOME"]) if "HOME" in env else None
                try:
                    profiles = load_profiles(home=home)
                except Exception:
                    profiles = {}
                prof = profiles.get("totpm", {})
                config = prof.get("config") or env.get("TOTPM_CONFIG")
                records = (
                    local.records(local.LocalScope(backend="totpm", config=config), env)
                    if config
                    else []
                )
            for item_id, label in records:
                results.append((backend, item_id, _normalize_title(label)))
    except Exception:
        pass
    return results


class FederatedResolver:
    """High-performance concurrent resolver aggregating accounts across all vaults."""

    def __init__(self, candidate_backends: list[str] | None = None) -> None:
        self.candidate_backends = candidate_backends or list(ALL_SUPPORTED_BACKENDS)

    def resolve_all(self, env: dict[str, str], timeout: float = 5.0) -> list[FederatedToken]:
        """Query all candidate backends concurrently and merge deduplicated tokens."""
        by_normalized: dict[str, FederatedToken] = {}
        if not self.candidate_backends:
            return []

        # Concurrently fetch from all candidate backends with non-blocking lifecycle management
        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, min(len(self.candidate_backends), 8))
        )
        try:
            futures = {
                executor.submit(_fetch_records_for_backend, b, env): b
                for b in self.candidate_backends
            }
            done, not_done = concurrent.futures.wait(futures.keys(), timeout=timeout)
            for fut in not_done:
                fut.cancel()

            for fut in done:
                try:
                    recs = fut.result()
                    for backend, item_id, title in recs:
                        norm = title.lower().strip()
                        if norm in by_normalized:
                            existing = by_normalized[norm]
                            if backend not in existing.backends:
                                existing.backends.append(backend)
                            existing.backend_keys[backend] = item_id
                        else:
                            by_normalized[norm] = FederatedToken(
                                key=item_id,
                                title=title,
                                backends=[backend],
                                backend_keys={backend: item_id},
                            )
                except Exception:
                    pass
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        # Finalize badges and labels
        tokens: list[FederatedToken] = []
        for tok in by_normalized.values():
            short_badges = [BACKEND_BADGES.get(b, b.upper()) for b in tok.backends]
            tok.badge = f"[{'+'.join(short_badges)}]"
            tok.display_label = f"{tok.title} {tok.badge}"
            tokens.append(tok)

        return sorted(tokens, key=lambda t: t.title.lower())

    def search(self, query: str, env: dict[str, str], timeout: float = 5.0) -> list[FederatedToken]:
        """Search tokens across all vaults matching the given key, substring, or fuzzy pattern."""
        all_tokens = self.resolve_all(env, timeout=timeout)
        if not query:
            return all_tokens
        q = query.lower().strip()
        exact_matched = []
        fuzzy_matched = []
        for tok in all_tokens:
            if (
                q == tok.key.lower()
                or q == tok.title.lower()
                or q == tok.display_label.lower()
                or any(q == str(k).lower() for k in tok.backend_keys.values())
            ):
                exact_matched.append(tok)
            elif (
                q in tok.title.lower()
                or q in tok.badge.lower()
                or q in tok.key.lower()
                or any(q in str(k).lower() for k in tok.backend_keys.values())
            ):
                fuzzy_matched.append(tok)
        return exact_matched if exact_matched else fuzzy_matched

    def retrieve_code(
        self,
        token: FederatedToken,
        env: dict[str, str],
        preferred_backend: str | None = None,
        timestamp: float | None = None,
    ) -> str:
        """Retrieve TOTP code from the first succeeding backend associated with token."""
        ordered_backends = list(token.backends)
        if preferred_backend and preferred_backend in ordered_backends:
            ordered_backends.remove(preferred_backend)
            ordered_backends.insert(0, preferred_backend)

        for backend in ordered_backends:
            backend_key = token.backend_keys.get(backend, token.key)
            try:
                if backend == "bitwarden":
                    from .backends import bitwarden

                    return bitwarden.bitwarden_code(backend_key, env, timestamp=timestamp)
                elif backend == "keepass":
                    from .backends import keepass

                    return keepass.keepass_code(backend_key, env, timestamp=timestamp)
                elif backend == "fido2":
                    from .backends import fido2

                    return fido2.fido2_code(backend_key, env)
                elif backend == "keychain":
                    from .backends import keychain

                    return keychain.keychain_code(backend_key, env, timestamp=timestamp)
                elif backend == "dpapi":
                    from .backends import dpapi

                    return dpapi.dpapi_code(backend_key, env, timestamp=timestamp)
                elif backend == "yubikey":
                    from .backends import hardware

                    return hardware.yubikey_code(backend_key, env)
                elif backend == "tpm2-totp":
                    from .backends import hardware

                    return hardware.tpm2_totp_code(backend_key, env)
                elif backend == "onepassword":
                    from .backends import onepassword

                    if hasattr(onepassword, "onepassword_code"):
                        return onepassword.onepassword_code(backend_key, env, timestamp=timestamp)
                    from .models import Scope
                    from .tui_profiles import load as load_profiles

                    home = Path(env["HOME"]) if "HOME" in env else None
                    try:
                        profiles = load_profiles(home=home)
                    except Exception:
                        profiles = {}
                    prof = profiles.get("onepassword", {})
                    account = prof.get("account") or env.get("OP_ACCOUNT")
                    vault = prof.get("vault") or env.get("OP_VAULT")
                    if not account or not vault:
                        raise AppError(2)
                    scope = Scope(backend_key, account, vault)
                    return onepassword.retrieve(scope, env)
                elif backend == "pass-otp":
                    from .backends import local

                    if hasattr(local, "pass_otp_code"):
                        return local.pass_otp_code(backend_key, env, timestamp=timestamp)
                    from .tui_profiles import load as load_profiles

                    home = Path(env["HOME"]) if "HOME" in env else None
                    try:
                        profiles = load_profiles(home=home)
                    except Exception:
                        profiles = {}
                    prof = profiles.get("pass-otp", {})
                    store = prof.get("store") or env.get("PASSWORD_STORE_DIR")
                    key_home = prof.get("key_home") or env.get("GNUPGHOME")
                    if not store or not key_home:
                        raise AppError(2)
                    scope = local.LocalScope(
                        backend="pass-otp", store=store, key_home=key_home, entry=backend_key
                    )
                    return local.retrieve(scope, env)
                elif backend == "totpm":
                    from .backends import local

                    if hasattr(local, "totpm_code"):
                        return local.totpm_code(backend_key, env, timestamp=timestamp)
                    from .tui_profiles import load as load_profiles

                    home = Path(env["HOME"]) if "HOME" in env else None
                    try:
                        profiles = load_profiles(home=home)
                    except Exception:
                        profiles = {}
                    prof = profiles.get("totpm", {})
                    config = prof.get("config") or env.get("TOTPM_CONFIG")
                    if not config:
                        raise AppError(2)
                    if ":" in backend_key:
                        service, account = backend_key.split(":", 1)
                    else:
                        service, account = backend_key, backend_key
                    scope = local.LocalScope(
                        backend="totpm", config=config, service=service, account=account
                    )
                    return local.retrieve(scope, env)
            except Exception:
                continue

        raise AppError(4)
