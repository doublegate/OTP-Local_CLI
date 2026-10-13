# ADR 0011: Resident Socket Daemon, Shared Memory IPC, and Native Linux PAM Module

- Status: Proposed for release v1.4.0 (Phase 9)
- Supersedes: None; extends System Architecture (ADR 0002)

## Context

Running CLI commands by spawning separate child processes introduces process startup overhead (typically 40ms to 200ms in Python). Furthermore, administrative workflows (e.g. running `sudo` or authenticating SSH sessions) require two-factor authentication without manually switching terminals, running a CLI command, and pasting the code.

## Decision

1. Implement a resident background daemon (`otp-local daemon --start`) maintaining decrypted caches in page-locked RAM.
2. Establish local IPC over a UNIX domain socket at `/run/user/$UID/otp-local.sock` utilizing binary CBOR serialization.
3. Implement a POSIX shared-memory circular ring buffer (`/dev/shm/otp-local-$UID`) delivering sub-millisecond (<0.1ms) code generation.
4. Enforce strict UID ownership checks using `SO_PEERCRED` on socket connections.
5. Implement a native Linux PAM module `pam_otp_local.so` in C (with Python test harness) to verify TOTP tokens during `sudo`, SSH, and system authentication events.
6. Enforce fail-closed design: If the daemon is unreachable or timed out, authentication attempts fail safely without locking the user out of fallback password paths.

## Consequences

- Lowers code generation latency by orders of magnitude (<0.1ms via shared memory).
- Enables seamless 2FA protection for local developer commands (`sudo`) and remote sessions (`sshd`).
- Zero network exposure: Daemons communicate exclusively via local UNIX domain sockets and POSIX shared memory.
