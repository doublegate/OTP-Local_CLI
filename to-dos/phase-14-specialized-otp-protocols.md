# Phase 14: Specialized OTP Protocols and Algorithmic Diversity (v2.2.0)

Status: Planned; milestone for release v2.2.0. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Expand cryptographic OTP generator engines beyond RFC 6238 TOTP to support specialized proprietary and counter-based algorithms, including Steam Guard (5-character alphanumeric token), Blizzard Mobile Authenticator (8-digit TOTP with restoration keys), Yandex OTP, and RFC 4226 counter-based HOTP with persistent counter state synchronization and recovery windows.

## Entry Conditions and Dependencies

- Phase 13 completed and verified.
- RFC 6238 core engine in `src/authy_local/models.py` and async core operational.

## Sprint Sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-14.1](sprints/14.1.md) | Specialized algorithmic engines (Steam Guard, Blizzard, Yandex) | Entry gate |
| [S-AUTH-14.2](sprints/14.2.md) | RFC 4226 HOTP counter-based engine and desync recovery | S-AUTH-14.1 |

All tasks in each sprint must have automated synthetic test verification before closing.

## Deliverables and Evidence

- Specialized algorithm module in `src/authy_local/specialized_otp.py` implementing Steam Guard character mapping (`23456789BCDFGHJKMNPQRTVWXY`), Blizzard restoration key derivation, and Yandex PIN hashing.
- Counter-based HOTP engine in `src/authy_local/hotp.py` with atomic counter persistence and bounded lookahead verification window (RFC 4226 Section 7.4).
- Textual TUI and CLI support for manual counter advancement (`otp-local next <account>`) and HOTP trigger badges (`[HOTP]`, `[STEAM]`).
- Comprehensive automated test suite in `tests/test_specialized_otp.py` and `tests/test_hotp.py`.
- Architectural specification in [docs/specs/21-specialized-otp-protocols.md](../docs/specs/21-specialized-otp-protocols.md).

## Exit Criteria

- 100% test vector parity against official Steam, Blizzard, and RFC 4226 test vectors.
- Atomic counter state writes preventing replay or counter rollback across system restarts.
- Zero regression in standard TOTP token generation pipelines.
