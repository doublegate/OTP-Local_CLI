# Phase 12: Universal Async Architecture, Extensible Plugin Engine, and v2.0.0 Freeze

Status: Planned for release v2.0.0. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Deliver the long-term stable (LTS) v2.0.0 architecture by executing a complete non-blocking asynchronous core rewrite (`asyncio`), implementing an extensible hook-based plugin engine (`pluggy`), establishing a high-performance headless daemon mode with JSON-RPC / CBOR streaming, and formalizing the frozen public Python API and CLI contracts.

## Entry Conditions and Dependencies

- All prior capability phases (Phase 0–11) completed and verified.
- Full test suite passing across all supported operating systems (Linux, macOS, Windows).
- Documentation, ADRs, and verification reports aligned with v1.6.0 baselines.

## Sprint Sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-12.1](sprints/12.1.md) | Universal async engine and fast streaming JSON-RPC / CBOR protocol | See sprint entry gate |
| [S-AUTH-12.2](sprints/12.2.md) | Extensible plugin hook architecture and v2.0.0 LTS public API freeze | S-AUTH-12.1 |

All tasks in each sprint must have automated synthetic test verification before closing.

## Deliverables and Evidence

- Core async architecture rewrite in `src/authy_local/async_core.py` providing non-blocking backend queries and concurrent multi-vault searches.
- Universal JSON-RPC / CBOR streaming protocol over local IPC sockets.
- Plugin hook management system in `src/authy_local/plugins/` defining entry points for storage backends, authenticators, and UI renderers.
- Frozen, semantically versioned public API for `authy_local` with 100% type annotation and docstring coverage.
- Backward compatibility adapter layer for legacy v1.x scripts and shell wrappers.
- Unit, concurrency, and performance benchmark test suites: `tests/test_async_core.py`, `tests/test_plugins.py`, and `tests/test_benchmark_v2.py`.
- Architectural decision record [ADR 0014](../docs/adr/0014-v2-async-core-and-plugin-system.md) and [Specification](../docs/specs/19-v2-architecture.md).

## Exit Criteria

- Zero regression in all existing v1.x CLI commands and Textual TUI workflows.
- Minimum 3x throughput improvement in multi-account code generation benchmarks.
- Clean public API freeze with documented deprecation and stability guarantees.
