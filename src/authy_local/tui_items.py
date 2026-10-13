"""Ephemeral item metadata and validated arguments for the resident TUI browser."""

from . import interaction
from .backends import local
from .errors import AppError
from .models import Scope
from .tui_profiles import valid_tag


def _values(profile: dict[str, str], names: tuple[str, ...]) -> list[str]:
    if not isinstance(profile, dict) or any(
        not isinstance(profile.get(name), str) or not profile[name] for name in names
    ):
        raise AppError(2)
    return [profile[name] for name in names]


def _local_scope(backend: str, profile: dict[str, str]) -> local.LocalScope:
    if backend == "pass-otp":
        store, key_home = _values(profile, ("store", "key_home"))
        return local.LocalScope(backend, store=store, key_home=key_home)
    if backend == "totpm":
        (config,) = _values(profile, ("config",))
        return local.LocalScope(backend, config=config)
    raise AppError(2)


def records(backend: str, profile: dict[str, str], env: dict[str, str]) -> list[tuple[str, str]]:
    """Fetch metadata only for one configured scope; never fetch item secrets."""
    if backend == "onepassword":
        account, vault = _values(profile, ("account", "vault"))
        tag = profile.get("tag", "OTP")
        if not valid_tag(tag):
            raise AppError(2)
        return interaction.list_items(account, vault, env, tag=tag)
    if backend == "yubikey":
        from .backends import hardware

        return hardware.yubikey_records(env)
    if backend == "tpm2-totp":
        from .backends import hardware

        return hardware.tpm2_totp_records(env)
    if backend == "keychain":
        from .backends import keychain

        return keychain.keychain_records(env)
    if backend == "dpapi":
        from .backends import dpapi

        return dpapi.dpapi_records(env)
    if backend == "fido2":
        from .backends import fido2

        return fido2.fido2_records(env)
    if backend == "bitwarden":
        from .backends import bitwarden

        return bitwarden.bitwarden_records(env)
    if backend == "keepass":
        from .backends import keepass

        return keepass.keepass_records(env)
    if backend == "federated":
        from .federation import FederatedResolver

        resolver = FederatedResolver()
        tokens = resolver.resolve_all(env)
        return [(t.key, t.display_label) for t in tokens]
    return local.records(_local_scope(backend, profile), env)


def arguments(backend: str, profile: dict[str, str], key: str) -> list[str]:
    """Build a validated show/copy scope for exactly one browser selection."""
    if not isinstance(key, str):
        raise AppError(2)
    if backend == "onepassword":
        account, vault = _values(profile, ("account", "vault"))
        Scope(key, account, vault)
        return [key, "--account", account, "--vault", vault]
    if backend in (
        "yubikey",
        "tpm2-totp",
        "keychain",
        "dpapi",
        "fido2",
        "bitwarden",
        "keepass",
        "federated",
    ):
        return ["--backend", backend, "--account", key]
    scope = _local_scope(backend, profile)
    if backend == "pass-otp":
        local.LocalScope(backend, store=scope.store, key_home=scope.key_home, entry=key)
        return [
            "--backend",
            backend,
            "--store",
            scope.store,
            "--key-home",
            scope.key_home,
            "--entry",
            key,
        ]
    parts = key.split(":")
    if len(parts) != 2:
        raise AppError(2)
    service, account = parts
    local.LocalScope(backend, config=scope.config, service=service, account=account)
    return [
        "--backend",
        backend,
        "--config",
        scope.config,
        "--service",
        service,
        "--account",
        account,
    ]


def remove(backend: str, profile: dict[str, str], key: str, env: dict[str, str]) -> None:
    """Delete one confirmed local selection after a non-identifying audit entry."""
    from dataclasses import replace
    from pathlib import Path

    from . import deletion_audit

    if backend == "keychain":
        arguments(backend, profile, key)
        from .backends import keychain

        deletion_audit.record(backend, Path(env["HOME"]) if env.get("HOME") else None)
        keychain.keychain_delete(key, env)
        return
    if backend == "dpapi":
        arguments(backend, profile, key)
        from .backends import dpapi

        deletion_audit.record(backend, Path(env["HOME"]) if env.get("HOME") else None)
        dpapi.dpapi_delete(key, env)
        return
    if backend == "fido2":
        arguments(backend, profile, key)
        from .backends import fido2

        deletion_audit.record(backend, Path(env["HOME"]) if env.get("HOME") else None)
        fido2.fido2_delete(key, env)
        return
    if backend == "bitwarden":
        arguments(backend, profile, key)
        from .backends import bitwarden

        deletion_audit.record(backend, Path(env["HOME"]) if env.get("HOME") else None)
        bitwarden.bitwarden_delete(key, env)
        return
    if backend == "keepass":
        arguments(backend, profile, key)
        from .backends import keepass

        deletion_audit.record(backend, Path(env["HOME"]) if env.get("HOME") else None)
        keepass.keepass_delete(key, env)
        return
    if backend not in {"pass-otp", "totpm"}:
        raise AppError(2)
    arguments(backend, profile, key)
    scope = _local_scope(backend, profile)
    if backend == "pass-otp":
        scope = replace(scope, entry=key)
    else:
        service, account = key.split(":")
        scope = replace(scope, service=service, account=account)
    deletion_audit.record(backend, Path(env["HOME"]) if env.get("HOME") else None)
    local.delete(scope, env)


def _subsequence_score(query: str, target: str, q_len: int, t_len: int) -> int | None:
    """Score a verified subsequence match based on adjacency, word boundaries, and span."""
    q_idx = 0
    first_match = -1
    last_match = -1
    consecutive_count = 0
    consecutive_bonus = 0
    boundary_count = 0
    prev_match_idx = -2

    for i, ch in enumerate(target):
        if ch == query[q_idx]:
            if first_match == -1:
                first_match = i
            last_match = i

            if i == prev_match_idx + 1:
                consecutive_count += 1
                consecutive_bonus += consecutive_count * 30
            else:
                consecutive_count = 0

            # Word boundary bonus (start of string or preceded by non-alphanumeric character)
            if i == 0 or not target[i - 1].isalnum():
                boundary_count += 1

            prev_match_idx = i
            q_idx += 1
            if q_idx == q_len:
                break

    if q_idx < q_len:
        return None

    span = last_match - first_match + 1
    score = (
        5_000 + consecutive_bonus + (boundary_count * 150) - (span * 10) - (first_match * 5) - t_len
    )
    return max(score, 1)


class SearchIndex:
    """Pre-indexed item structure providing sub-millisecond ranked fuzzy search.

    Pre-computes casefold normalization, character sets, and string lengths
    to enable fast set-based non-match rejection and ranked subsequence scoring.
    """

    __slots__ = ("_entries", "_rows")

    def __init__(self, rows: list[tuple[str, str]]):
        self._rows = list(rows)
        self._entries = [
            (
                key,
                label,
                (norm := label.casefold()),
                frozenset(norm),
                len(norm),
            )
            for key, label in rows
        ]

    def filter(self, query: str) -> list[tuple[str, str]]:
        """Filter pre-indexed entries by query and return ranked (key, label) pairs."""
        q = query.strip().casefold()
        if not q:
            return list(self._rows)

        tokens = [w for w in q.split() if w]
        filter_modifiers = {}
        words = []
        for t in tokens:
            if ":" in t:
                prefix, val = t.split(":", 1)
                filter_modifiers[prefix] = val
            else:
                words.append(t)

        def matches_modifiers(norm: str) -> bool:
            for k, v in filter_modifiers.items():
                if k in ("type",):
                    if v == "hotp" and "hotp" not in norm:
                        return False
                    if v == "totp" and "hotp" in norm:
                        return False
                elif k in ("tag", "algo", "digits", "b", "backend"):
                    if v not in norm:
                        return False
                else:
                    if v not in norm:
                        return False
            return True

        if not words:
            return [
                (key, label) for key, label, norm, _, _ in self._entries if matches_modifiers(norm)
            ]

        scored: list[tuple[int, int, str, str]] = []

        if len(words) > 1:
            q_chars = frozenset("".join(words))
            for idx, (key, label, norm, char_set, n_len) in enumerate(self._entries):
                if not matches_modifiers(norm):
                    continue
                if not (q_chars <= char_set):
                    continue
                all_matched = True
                term_scores = 0
                for w in words:
                    sub_idx = norm.find(w)
                    if sub_idx != -1:
                        is_boundary = sub_idx == 0 or not norm[sub_idx - 1].isalnum()
                        bonus = 15_000 if is_boundary else 0
                        term_scores += 20_000 + bonus - (sub_idx * 10)
                    else:
                        it = iter(norm)
                        if all(c in it for c in w):
                            s_score = _subsequence_score(w, norm, len(w), n_len)
                            if s_score is not None:
                                term_scores += s_score
                            else:
                                all_matched = False
                                break
                        else:
                            all_matched = False
                            break
                if all_matched:
                    scored.append((term_scores - n_len, -idx, key, label))
        else:
            single_word = words[0]
            q_len = len(single_word)
            q_set = frozenset(single_word)
            for idx, (key, label, norm, char_set, n_len) in enumerate(self._entries):
                if not matches_modifiers(norm):
                    continue
                # Fast rejection: if any query character is missing from candidate, skip immediately
                if not (q_set <= char_set):
                    continue

                # Tier 1: Exact match
                if norm == single_word:
                    scored.append((100_000, -idx, key, label))
                    continue

                # Tier 2: Prefix match
                if norm.startswith(single_word):
                    scored.append((50_000 - n_len, -idx, key, label))
                    continue

                # Tier 3: Word boundary / Substring match
                sub_idx = norm.find(single_word)
                if sub_idx != -1:
                    is_boundary = sub_idx == 0 or not norm[sub_idx - 1].isalnum()
                    bonus = 15_000 if is_boundary else 0
                    score = 25_000 + bonus - (sub_idx * 20) - n_len
                    scored.append((score, -idx, key, label))
                    continue

                # Tier 4: Subsequence match
                it = iter(norm)
                if all(c in it for c in single_word):
                    sub_score = _subsequence_score(single_word, norm, q_len, n_len)
                    if sub_score is not None:
                        scored.append((sub_score, -idx, key, label))

        # Native C tuple sort (score desc, -idx desc) avoiding lambda overhead
        scored.sort(reverse=True)
        return [(key, label) for _, _, key, label in scored]


def fuzzy_filter(rows: list[tuple[str, str]], query: str) -> list[tuple[str, str]]:
    """One-shot fuzzy filter function matching PROJECT.md interface contract.

    Accepts list of (key, label) tuples and returns filtered & ranked list.
    Safely handles empty queries, Unicode characters, and special symbols.
    """
    q = query.strip().casefold()
    if not q:
        return list(rows)

    q_len = len(q)
    q_set = frozenset(q)
    scored: list[tuple[int, int, str, str]] = []

    for idx, (key, label) in enumerate(rows):
        norm = label.casefold()
        n_len = len(norm)
        char_set = frozenset(norm)

        # Fast set rejection
        if not (q_set <= char_set):
            continue

        # Tier 1: Exact match
        if norm == q:
            scored.append((100_000, -idx, key, label))
            continue

        # Tier 2: Prefix match
        if norm.startswith(q):
            scored.append((50_000 - n_len, -idx, key, label))
            continue

        # Tier 3: Substring match
        sub_idx = norm.find(q)
        if sub_idx != -1:
            is_boundary = sub_idx == 0 or not norm[sub_idx - 1].isalnum()
            bonus = 15_000 if is_boundary else 0
            score = 25_000 + bonus - (sub_idx * 20) - n_len
            scored.append((score, -idx, key, label))
            continue

        # Tier 4: Subsequence match
        it = iter(norm)
        if all(c in it for c in q):
            sub_score = _subsequence_score(q, norm, q_len, n_len)
            if sub_score is not None:
                scored.append((sub_score, -idx, key, label))

    # Native C tuple sort (score desc, -idx desc) avoiding lambda overhead
    scored.sort(reverse=True)
    return [(key, label) for _, _, key, label in scored]
