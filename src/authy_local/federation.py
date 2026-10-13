"""Federated multi-vault resolver offering unified cross-backend token aggregation and search."""

import concurrent.futures
import re
from dataclasses import dataclass, field

from .errors import AppError

BACKEND_BADGES: dict[str, str] = {
    "onepassword": "1P",
    "bitwarden": "BW",
    "keepass": "KP",
    "pass-otp": "GPG",
    "totpm": "TPM",
    "keychain": "KC",
    "dpapi": "DP",
    "fido2": "FIDO2",
    "yubikey": "YUBI",
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

    def __post_init__(self) -> None:
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
    except Exception:
        pass
    return results


class FederatedResolver:
    """High-performance concurrent resolver aggregating accounts across all vaults."""

    def __init__(self, candidate_backends: list[str] | None = None) -> None:
        self.candidate_backends = candidate_backends or list(ALL_SUPPORTED_BACKENDS)

    def resolve_all(self, env: dict[str, str], timeout: float = 2.0) -> list[FederatedToken]:
        """Query all candidate backends concurrently and merge deduplicated tokens."""
        by_normalized: dict[str, FederatedToken] = {}

        # Concurrently fetch from all candidate backends
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(len(self.candidate_backends), 8)
        ) as executor:
            futures = {
                executor.submit(_fetch_records_for_backend, b, env): b
                for b in self.candidate_backends
            }
            done, _ = concurrent.futures.wait(futures.keys(), timeout=timeout)
            for fut in done:
                try:
                    recs = fut.result()
                    for backend, item_id, title in recs:
                        norm = title.lower().strip()
                        if norm in by_normalized:
                            existing = by_normalized[norm]
                            if backend not in existing.backends:
                                existing.backends.append(backend)
                        else:
                            by_normalized[norm] = FederatedToken(
                                key=item_id,
                                title=title,
                                backends=[backend],
                            )
                except Exception:
                    pass

        # Finalize badges and labels
        tokens: list[FederatedToken] = []
        for tok in by_normalized.values():
            short_badges = [BACKEND_BADGES.get(b, b.upper()) for b in tok.backends]
            tok.badge = f"[{'+'.join(short_badges)}]"
            tok.display_label = f"{tok.title} {tok.badge}"
            tokens.append(tok)

        return sorted(tokens, key=lambda t: t.title.lower())

    def search(self, query: str, env: dict[str, str], timeout: float = 2.0) -> list[FederatedToken]:
        """Search tokens across all vaults matching the given substring or fuzzy pattern."""
        all_tokens = self.resolve_all(env, timeout=timeout)
        if not query:
            return all_tokens
        q = query.lower().strip()
        matched = []
        for tok in all_tokens:
            if q in tok.title.lower() or q in tok.badge.lower():
                matched.append(tok)
        return matched

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
            try:
                if backend == "bitwarden":
                    from .backends import bitwarden

                    return bitwarden.bitwarden_code(token.key, env, timestamp=timestamp)
                elif backend == "keepass":
                    from .backends import keepass

                    return keepass.keepass_code(token.key, env, timestamp=timestamp)
                elif backend == "fido2":
                    from .backends import fido2

                    return fido2.fido2_code(token.key, env)
                elif backend == "keychain":
                    from .backends import keychain

                    return keychain.keychain_code(token.key, env, timestamp=timestamp)
                elif backend == "dpapi":
                    from .backends import dpapi

                    return dpapi.dpapi_code(token.key, env, timestamp=timestamp)
                elif backend == "yubikey":
                    from .backends import hardware

                    return hardware.yubikey_code(token.key, env)
                elif backend == "tpm2-totp":
                    from .backends import hardware

                    return hardware.tpm2_totp_code(token.key, env)
            except Exception:
                continue

        raise AppError(4)
