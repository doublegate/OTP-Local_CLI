# ADR 0013: Runtime Memory Forensics Hardening and Process Isolation

- Status: Proposed for release v1.6.0 (Phase 11)
- Supersedes: None; extends Security and Data (ADR 0003) and Interactive OTP Enrollment (ADR 0008)

## Context

Standard Python applications do not protect heap allocations from operating system swapping or unprivileged process core dumping. If an unencrypted swap partition is enabled, decrypted TOTP seeds could be written to disk. Furthermore, unexpected crashes could generate core dump files containing sensitive keys in plaintext.

## Decision

1. Implement page-locked memory allocations in `src/authy_local/security.py` using `mlock()` and `munlock()` via standard `libc` ctypes calls.
2. Mark all secure memory pages with `madvise(MADV_DONTDUMP)` to ensure they are excluded from core dumps in the event of an unhandled crash or segmentation fault.
3. Enforce deterministic memory scrubbing using `ctypes.memset` across all mutable bytearrays upon transaction completion, modal dismissal, or receipt of termination signals (`SIGINT`, `SIGTERM`, `SIGHUP`).
4. Upgrade the security auditor to v2, evaluating seed Shannon entropy, RFC 6238 clock drift, and scanning `/proc/$PID/environ` and shell histories for leaked credentials.

## Consequences

- Hardens the runtime against memory scraping, core dump extraction, and cold-boot physical inspection.
- Protects systems with active swap spaces from inadvertently writing secrets to non-volatile storage.
- Signal interceptors guarantee that interrupting the CLI or TUI (`Ctrl+C`) immediately scrubs sensitive buffers before process termination.
