# Security Architecture & Vulnerability Mitigation

## Architectural Overview

OTP-Local provides local-first, zero-knowledge, multi-vault authentication across
Linux, macOS, and Windows environments. The runtime environment isolates
cryptographic secrets across five defense-in-depth boundaries:

1. **Memory Isolation**: Core dump generation is disabled at process initialization
   via Linux `prctl(PR_SET_DUMPABLE, 0)` and POSIX `setrlimit(RLIMIT_CORE, (0, 0))`.
   Process address space pages are locked into physical RAM using `mlockall(MCL_CURRENT | MCL_FUTURE)`
   to prevent swapping to persistent storage.
2. **Buffer Zeroization**: Sensitive cryptographic secrets, decrypted payloads, and
   ephemeral shared memory buffers are pinned in `SecureBuffer` instances marked with
   `madvise(MADV_DONTDUMP)`. Buffers are overwritten in-place with null bytes via
   `ctypes.memset` in `finally` blocks and signal handlers (`SIGINT`, `SIGTERM`, `SIGHUP`).
3. **Strict Input Boundaries**: Account identifiers, vault scopes, and token labels are
   validated against strict alphanumeric allowlists (`LABEL = [A-Za-z0-9][A-Za-z0-9_.:@-]{0,63}\Z`)
   prior to passing to command-line utilities, eliminating command-line option injection.
4. **Filesystem Integrity**: Importer pipelines enforce atomic file descriptor operations
   using `os.O_NOFOLLOW` and `os.fstat(fd)` to prevent Time-Of-Check to Time-Of-Use
   (TOCTOU) symlink substitution. Configuration files are created with explicit `0o600`
   permissions inside `0o700` parent directories.
5. **Traceback & Diagnostic Shields**: Top-level exception barriers intercept unhandled
   exceptions and emit static diagnostic strings, preventing stack traces from leaking
   sensitive data to standard error.

---

## Security Audit Waiver: GHSA-vfj7-8cjw-p6xm (braces <= 3.0.3)

| Parameter | Specification |
|---|---|
| Waiver ID | WAIVER-2026-NPM-01 |
| Package | `braces` (versions `<= 3.0.3`) |
| Advisory | [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) / CVE-2026-93687 |
| Severity | High (CWE-674: Uncontrolled Recursion / Stack Exhaustion) |
| Hierarchy | `markdownlint-cli2@0.23.3` -> `globby` -> `fast-glob` -> `micromatch` -> `braces@3.0.3` |
| Scope | Development-only linting tool invoked during `scripts/check.sh` and CI documentation checks. |

### Technical Analysis & Risk Assessment

- **Zero Runtime Exposure**: `markdownlint-cli2` is defined exclusively under `devDependencies`
  in `package.json`. It is never packaged into production wheel distributions (`dist/wheels/`),
  native PAM shared objects (`pam_otp_local.so`), or standalone executables.
- **Controlled Input Space**: The stack-exhaustion vulnerability in `braces` requires parsing
  deeply nested, adversarial brace patterns (such as `{1..{1..{1..1000}}}}`). In this repository,
  all glob patterns processed by `markdownlint-cli2` are static, hardcoded configuration entries
  defined in `.markdownlint-cli2.jsonc`. No untrusted user or network input is evaluated by `braces`.
- **Upstream Patch Status**: Upstream maintainers of `micromatch/braces` have not published a patched
  release on the npm registry (`first_patched_version: null`). Issue `micromatch/braces#73` remains
  open with pull requests #72 and #82 awaiting merge.
- **Forced Downgrade Hazard**: Running `npm audit fix --force` would downgrade `markdownlint-cli2`
  to legacy versions (such as `0.21.0`), which introduces multiple critical vulnerabilities in
  `js-yaml` and `markdown-it`.
- **Mitigation & Expiration**: Transitive dependencies `katex` and `smol-toml` are pinned to
  patched versions (`katex@^0.18.2`, `smol-toml@^1.9.0`) via `overrides` in `package.json`.
  This waiver remains active until an official `braces >= 3.0.4` release is published upstream,
  at which point the lockfile will be regenerated via `npm update braces`.
