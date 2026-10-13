# Low-Latency IPC and Linux PAM Integration Specification

Status: Planned for release v1.4.0.
Extends [Architecture](02-architecture.md), [CLI Specification](03-cli-specification.md), and [Security and Data](04-security-and-data.md).

## 1. Overview and Requirements

High-performance environments and administrative workflows require sub-millisecond TOTP generation and native integration into the host operating system's authentication subsystem.

Key requirements:

1. Sub-millisecond response (<0.1ms) for high-frequency queries.
2. Background resident daemon (`otp-local daemon`) managing active credential caches in locked memory.
3. IPC over UNIX domain sockets with binary CBOR serialization.
4. POSIX shared-memory circular ring buffer for zero-copy bulk lookups.
5. Native Linux Pluggable Authentication Module (`pam_otp_local.so`) for `sudo`, SSH, and system logins.

## 2. IPC Architecture & Shared Memory

### 2.1 UNIX Domain Socket Contract

- Path: `/run/user/$UID/otp-local.sock` (mode `0600`).
- Credentials check: Server inspects `SO_PEERCRED` on Linux and `LOCAL_PEERCRED` on macOS/BSD. Requests from non-matching UIDs are terminated immediately.
- Protocol framing: 4-byte big-endian length prefix followed by CBOR payload.
- Request payload:
  `{"action": "get_totp", "service": "github", "account": "alice", "timestamp": 1776000000}`
- Response payload:
  `{"status": "ok", "code": "849201", "valid_until": 1776000030, "remaining_seconds": 18}`

### 2.2 POSIX Shared Memory Ring Buffer (`src/authy_local/shm.py`)

- Shared memory object: `/dev/shm/otp-local-$UID` (size 64 KiB, mode `0600`).
- Structure:
  - Header: 64-byte control block with atomic spinlock, sequence number, and active token count.
  - Slots: 64-byte fixed-size slots containing service hash, current 6-digit code, expiry timestamp, and epoch counter.
- Read latency: ~50–80 nanoseconds per lookup using memory-mapped atomic reads, bypassing kernel context switches entirely.

## 3. Linux PAM Module (`pam_otp_local.so`)

### 3.1 Design & Execution Flow

The C module `pam/pam_otp_local.c` implements the standard PAM authentication interface:

1. Invoked by PAM during `auth required pam_otp_local.so` in `/etc/pam.d/sudo` or `/etc/pam.d/sshd`.
2. Locates the caller's resident daemon socket `/run/user/$UID/otp-local.sock`.
3. Issues a PAM conversation prompt: `"Enter OTP-Local code for <service>: "`.
4. Connects to the local daemon and verifies the provided code within a 1-step window (±30s).
5. Returns `PAM_SUCCESS` on match, or `PAM_AUTH_ERR` on failure.

### 3.2 Failsafe and Security Controls

- Fail-closed: If the daemon is unreachable, the module safely returns `PAM_AUTHINFO_UNAVAIL` without hanging.
- Rate limiting: Rejects brute-force attempts with exponential delays (3 failed attempts lock authentication for 60 seconds).
- Replay prevention: Tracks the last verified timestamp; identical codes within the same 30-second window are rejected.

## 4. Diagnostics and Health Checks

The command `otp-local doctor --pam` validates:

- Presence of `/lib/security/pam_otp_local.so` or `/usr/local/lib/security/pam_otp_local.so`.
- Socket permissions and active daemon process state.
- Systemd user service status: `systemctl --user status otp-local.service`.
