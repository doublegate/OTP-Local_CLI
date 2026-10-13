# ADR 0014: Universal Async Core, Extensible Plugin Hook Engine, and v2.0.0 API Freeze

- Status: Proposed for release v2.0.0 (Phase 12)
- Supersedes: None; extends System Architecture (ADR 0002) and Cohesive Terminal Interface (ADR 0004)

## Context

As OTP-Local CLI expands to federate multiple external tools, remote socket connections, hardware authenticators, and high-frequency PAM requests, synchronous blocking subprocess calls create performance bottlenecks and UI latency. Furthermore, third-party developers require a clean, supported mechanism to introduce custom stores and hooks without modifying core project source files.

## Decision

1. Execute a complete non-blocking asynchronous core rewrite (`asyncio`) in `src/authy_local/async_core.py`, upgrading backend queries and vault synchronization to coroutines.
2. Implement an extensible plugin hook architecture using `pluggy` with hook specifications for backends, life-cycle events, and TUI widgets.
3. Freeze the public API within the `authy_local` namespace, committing to strict semantic versioning (SemVer) and backwards compatibility guarantees for all v2.x releases.
4. Provide a synchronous legacy adapter layer so that existing shell scripts and v1.x commands run without modification.
5. Standardize on JSON-RPC 2.0 / CBOR streaming for all daemon IPC interactions.

## Consequences

- Delivers a minimum 3x throughput speedup during multi-vault synchronization and batch OTP lookups.
- Enables clean third-party plugin integration via standard Python entry points.
- Establishes a rock-solid, production-grade API baseline with LTS stability guarantees.
