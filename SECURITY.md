# Security Policy

## Security Baseline and Principles

Authy-to-1Password Local is a privacy-first, local-only terminal companion designed for
secure, offline TOTP authentication and migration. The application enforces several
non-negotiable security invariants:

1. **Local and Offline Execution**: The application makes zero outbound network connections.
   No telemetry, no remote APIs, and no external tracking are permitted.
2. **Strict File Permissions & Symlink Defense**: Exported credential vaults, plugin allowlists,
   and configuration files are enforced with `0600` file modes inside `0700` state/config
   directories. Importers open files atomically using `os.open(..., os.O_NOFOLLOW)` and verify
   regular-file inodes via `os.fstat(fd)` to prevent TOCTOU symlink substitution.
3. **Fail-Closed Architecture & Input Bounds**: Malformed input, untrusted scopes, invalid tokens,
   non-positive daemon PIDs (`pid <= 0`), or missing cryptographic dependencies result in
   immediate fail-closed termination. Hardware account labels are restricted to strict
   `[A-Za-z0-9][A-Za-z0-9_.:@-]{0,63}\Z` bounds, and native C PAM requests apply RFC 8259 JSON
   escaping with stack zeroization (`explicit_bzero`).
4. **Runtime Memory Forensics & Zeroization**: Process memory is protected via `mlockall`,
   `prctl(PR_SET_DUMPABLE, 0)`, `setrlimit(RLIMIT_CORE, (0, 0))`, and `madvise(MADV_DONTDUMP)`
   on mutable bytearray `SecureBuffer` instances. Secret buffers and Textual modal credential
   widgets are deterministically overwritten via `ctypes.memset` upon modal dismissal/unmount,
   session lock, or process termination signals (`SIGINT`, `SIGTERM`, `SIGHUP`).
5. **Zero Diagnostic Leakage**: Sensitive fields (`OtpParameters.secret`, subprocess outputs)
   enforce `field(repr=False)` masking, and a top-level CLI exception shield intercepts
   unhandled exceptions so tracebacks never leak decrypted secrets to standard output or error.

See [Security Architecture & Vulnerability Mitigation](docs/specs/06-security-architecture.md)
for detailed runtime boundary specifications and dependency audit records.

## Supported Versions

| Version | Supported |
| --- | --- |
| 2.0.x (LTS) | Yes |
| 1.x | Security fixes only |
| < 1.0.0 | No |

## Reporting a Vulnerability

If you discover a security vulnerability or potential credential leakage flaw, please report
it responsibly rather than opening a public issue.

1. **Email Contact**: Send vulnerability reports directly to the maintainer via GitHub security advisories or repository contact channels.
2. **Details to Include**:
   - Description of the vulnerability and its potential blast radius.
   - Exact steps or minimal reproducible script demonstrating the behavior with synthetic keys.
   - Operating system and environment details (Linux distribution, Python version).
3. **Safety Notice**: Never include real vault seeds, authentic OTP secrets, or production
   credentials in any security report. Always substitute synthetic test vectors (e.g. `JBSWY3DPEHPK3PXP`).
