# Phase 9: Ultra-Low-Latency Local IPC and System Authentication Engine

Status: Planned for release v1.4.0. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Deliver sub-millisecond TOTP code generation (<0.1ms) and deep operating system authentication integration by implementing a resident local UNIX domain socket daemon with shared-memory ring buffers, coupled with a native Linux Pluggable Authentication Module (`pam_otp_local.so`) enabling direct TOTP two-factor verification for `sudo`, SSH, and system login prompts against locally enrolled tokens.

## Entry Conditions and Dependencies

- Base CLI and enrollment engine operational (Phase 0–8 completed).
- Linux PAM development headers (`libpam0g-dev` / `pam-devel`) available on build hosts.
- POSIX shared memory (`shm_open`) and UNIX domain sockets supported on the operating system.

## Sprint Sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-9.1](sprints/9.1.md) | Resident UNIX socket daemon and shared-memory IPC ring buffer | See sprint entry gate |
| [S-AUTH-9.2](sprints/9.2.md) | Linux PAM integration module for sudo and SSH | S-AUTH-9.1 |

All tasks in each sprint must have automated synthetic test verification before closing.

## Deliverables and Evidence

- Resident daemon manager in `src/authy_local/daemon.py` supporting lifecycle controls (`start`, `stop`, `status`, `reload`).
- High-performance IPC client and server in `src/authy_local/ipc.py` communicating over `/run/user/$UID/otp-local.sock` with binary CBOR payloads.
- POSIX shared-memory circular ring buffer implementation in `src/authy_local/shm.py` achieving <0.1ms response times.
- Native C PAM module `pam/pam_otp_local.c` with accompanying `pam/Makefile` and Python test harness.
- Systemd user service unit definition `systemd/otp-local.service`.
- Unit and synthetic integration test suites: `tests/test_daemon_ipc.py` and `tests/test_pam_integration.py`.
- Architectural decision record [ADR 0011](../docs/adr/0011-pam-module-and-low-latency-ipc.md) and [Specification](../docs/specs/16-pam-and-ipc.md).

## Exit Criteria

- Sub-millisecond code retrieval benchmarked and verified under high concurrency.
- Zero socket credential spoofing: strict `SO_PEERCRED` / `LOCAL_PEERCRED` UID verification on all socket connections.
- PAM module fails closed safely on timeout or missing credentials without hanging authentication pipelines.
