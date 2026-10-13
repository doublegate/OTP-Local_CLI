# Security Policy

## Security Baseline and Principles

Authy-to-1Password Local is a privacy-first, local-only terminal companion designed for
secure, offline TOTP authentication and migration. The application enforces several
non-negotiable security invariants:

1. **Local and Offline Execution**: The application makes zero outbound network connections.
   No telemetry, no remote APIs, and no external tracking are permitted.
2. **Strict File Permissions**: Exported credential vaults and configuration files are
   enforced with `0600` file modes (read/write only by the user). State directories and
   cache roots are created with `0700` directory modes.
3. **Fail-Closed Architecture**: Malformed input, untrusted scopes, invalid tokens, or
   missing cryptographic dependencies result in immediate fail-closed termination.
4. **Memory Hygiene**: In-memory secret buffers, keys, and session representations are
   explicitly zeroed and cleared upon modal dismissal or session agent auto-lock.
5. **Zero Diagnostic Leakage**: Child process errors, backtraces, and exceptions must never
   contain decrypted secrets, seeds, or private parameters in standard output or error streams.

## Supported Versions

| Version | Supported |
| --- | --- |
| 1.0.x | Yes |
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
