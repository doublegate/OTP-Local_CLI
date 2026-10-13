# Autonomous Security Auditor v2 and Memory Forensics Specification

Status: Planned for release v1.6.0.
Extends [Security and Data](04-security-and-data.md) and [Development and Testing](05-development-and-testing.md).

## 1. Overview and Requirements

Credential management tools represent high-value targets for memory forensics, cold-boot attacks, and process inspection. This specification defines runtime memory hardening and the autonomous security auditing engine for OTP-Local CLI.

Key requirements:

1. Memory locking (`mlock`): Pin sensitive memory pages into physical RAM, prohibiting operating system paging to unencrypted swap space.
2. Core dump exclusion (`madvise(MADV_DONTDUMP)`): Exclude secret buffers from application crash dumps.
3. Cryptographic memory zeroization: Secure bytearrays scrubbed via `ctypes.memset` on exit or signal interruption.
4. Security Auditor v2: Analyze seed Shannon entropy, token length, weak hashing algorithms, and clock drift.
5. Process environment scanning: Audit `/proc/$PID/environ`, command line arguments, and shell history files for leaked credentials.

## 2. Memory Forensics Hardening Architecture (`src/authy_local/security.py`)

### 2.1 Syscall Integration via ctypes

The runtime interacts with POSIX `libc`:

- `mlock(void *addr, size_t len)`: Pins memory pages into physical RAM.
- `munlock(void *addr, size_t len)`: Unpins memory pages upon buffer release.
- `madvise(void *addr, size_t len, int advice)`: Invoked with `MADV_DONTDUMP` (value `16` on Linux).

```python
# Page-aligned buffer allocation
buffer_type = ctypes.c_char * 4096
buf = buffer_type()
addr = ctypes.addressof(buf)
libc.mlock(addr, 4096)
libc.madvise(addr, 4096, 16)  # MADV_DONTDUMP
```

### 2.2 Signal Interception & Teardown

- Registered signal handlers: `SIGINT`, `SIGTERM`, `SIGHUP`.
- Handler execution: Iterates over all registered active secure buffers, executes `ctypes.memset(addr, 0, len)`, unpins pages, and terminates process cleanly.

## 3. Autonomous Security Auditor v2 (`src/authy_local/auditor.py`)

### 3.1 Shannon Entropy & Seed Strength Analysis

The auditor evaluates each stored secret:

- Shannon Entropy calculation: evaluates bits of entropy per character.
- Warnings issued for:
  - Entropy < 3.2 bits/character (indicating non-random or repetitive seeds).
  - Seed length < 128 bits (16 Base32 characters).
  - Use of deprecated algorithms (e.g. SHA-1 instead of SHA-256/SHA-512 where supported).

### 3.2 Time Drift Diagnostics

- Compares host monotonic clock and wall clock against local NTP sync state.
- Flags clock offsets exceeding ±5 seconds to prevent token generation desynchronization.

### 3.3 Process & Environment Leak Scanner

- Checks `/proc/self/cmdline` for exposed seed arguments.
- Checks `/proc/self/environ` for exposed `*_SECRET` or `*_SEED` keys.
- Audits shell history files (`~/.bash_history`, `~/.zsh_history`, `~/.local/share/fish/fish_history`) for accidental secret leakage.

## 4. Secret Rotation Engine

- Invoked via `otp-local audit --rotate <service>`.
- Provides an interactive step-by-step wizard to replace an existing seed with a fresh high-entropy key, verify the challenge code, and update all target backends atomically.
