# Phase 20: Native Rust Cryptographic Acceleration (v2.8.0)

Status: Planned; milestone for release v2.8.0. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Maximize operational performance, throughput, and cryptographic memory safety by implementing an optional native Rust extension (`authy_local_rust`) built with PyO3. The engine provides SIMD-accelerated HMAC-SHA1/SHA256, constant-time Base32 decoding, kernel-level memory pinning, and zero-copy shared-memory ring buffers, while preserving a pure-Python fallback.

## Entry Conditions and Dependencies

- Phase 19 completed and verified.
- Memory forensics (`src/authy_local/security.py`) and POSIX shared-memory (`src/authy_local/shm.py`) operational.

## Sprint Sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-20.1](sprints/20.1.md) | Native Rust cryptographic engine (PyO3, SIMD HMAC, constant-time Base32) | Entry gate |
| [S-AUTH-20.2](sprints/20.2.md) | High-throughput zero-copy IPC ring buffer and fallback verification | S-AUTH-20.1 |

All tasks in each sprint must have automated synthetic test verification before closing.

## Deliverables and Evidence

- Rust crate `crates/authy_local_rust` with PyO3 bindings:
  - SIMD-accelerated HMAC-SHA1, HMAC-SHA256, and HMAC-SHA512.
  - Constant-time Base32 decoding preventing side-channel cache attacks.
  - Memory-safe `mlock` / `munlock` page pinning with compiler-barrier zeroization.
- High-throughput zero-copy shared-memory ring buffer reading and writing in under 500 nanoseconds.
- Transparent dynamic loader in `src/authy_local/accelerator.py` falling back to pure Python when native wheels are absent.
- Multi-arch wheel building workflow in `.github/workflows/wheels.yml` (maturin).
- Automated benchmark and correctness test suite in `tests/test_accelerator.py`.
- Architectural documentation in `docs/specs/20-native-accelerator.md`.

## Exit Criteria

- Minimum 5x throughput improvement over pure Python in batch TOTP calculation benchmarks (>50,000 codes/sec).
- 100% test parity between native Rust engine and pure-Python fallback implementations.
- Zero crashes, memory leaks, or segfaults verified under Valgrind and AddressSanitizer (ASan).
