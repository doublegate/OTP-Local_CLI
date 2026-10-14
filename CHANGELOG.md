# Changelog

## [Unreleased]

## [2.0.1] - 2026-10-14

### Added

- CLI subcommands `otp-local list` (`--json`, `--backend`) and `otp-local search QUERY` (`--code`, `--copy`, `--json`, `--backend`) in `src/authy_local/cli.py` for non-interactive multi-vault querying and token retrieval.
- Daemon lifecycle subcommands `otp-local daemon restart` and `otp-local daemon clean` alongside root flag compatibility normalization (`--daemon`, `--status`, `--stop`, `--clean`, `--doctor`, `--pick`).
- Automated multi-distro Linux dependency remediation in `src/authy_local/doctor.py` (`otp-local doctor --install` / `--fix`) supporting `apt-get` (Debian/Ubuntu), `pacman` (Arch/CachyOS), and `dnf` (Fedora/RHEL) with automatic root/sudo privilege detection.
- Textual TUI enhancements in `src/authy_local/tui.py` and `src/authy_local/tui_items.py`: `TotpProgressBar` live countdown widget, 3-tier fuzzy match highlighting (`Exact`, `Prefix`, `Subsequence`), `CopyToast` notification banners, and `HelpModal` keyboard shortcut reference (`F1` / `?`).
- Comprehensive 7-target authentic microbenchmark suite in `benchmarks/run_all.py` (`benchmark_capabilities.py`, `benchmark_totp_cache.py`, `benchmark_ipc.py`, `benchmark_shm.py`, `benchmark_tui.py`, `benchmark_federation.py`) verifying concrete latency and speedup SLAs without mocks or synthetic sleeps.
- Strategic v2.1.0 – v3.0.0 LTS roadmap and specification architecture across `ROADMAP.md`, `to-dos/phase-13-*.md` through `to-dos/phase-22-*.md`, `to-dos/sprints/13.1.md` through `22.2.md` (allocating 80 tasks `T-AUTH-130`–`T-AUTH-227`), and `docs/specs/20-*.md` through `23-*.md`.
- Security architecture and dependency audit waiver specification in `docs/specs/06-security-architecture.md` (`WAIVER-2026-NPM-01`).
- Adversarial and stress verification test suites (`test_m1_challenger_wheel_security.py`, `test_m2_security_hardening.py`, `test_m2_challenger_adversarial.py`, `test_m2_r2_adversarial_memory_protection.py`, `test_adversarial_m2_stress_verification.py`, `test_m3_adversarial_stress.py`, `test_m4_adversarial_stress.py`, `test_m4_2_adversarial_vault_doctor.py`, `test_m5_challenger_tier5_adversarial.py`, `test_m5_adversarial_concurrency_e2e_packaging.py`), expanding the total automated suite to 1,258 tests (1,140 unit/integration + 118 opaque-box E2E).

### Changed

- Optimized `AsyncFederatedResolver` in `src/authy_local/async_core.py` to use `asyncio.as_completed` for early fast-return code retrieval and `executor.shutdown(wait=False, cancel_futures=True)` in `src/authy_local/federation.py` with per-backend item key tracking (`backend_keys`), achieving a verified 3.75x multi-vault speedup.
- Upgraded POSIX shared memory ring buffer (`src/authy_local/shm.py`) with atomic spinlock/flock write serialization, lockless seqlock read counters, and 16-slot linear collision probing, achieving ~2.2 us zero-copy reads with zero torn reads across 940,000+ concurrent queries.
- Upgraded UNIX domain socket IPC daemon (`src/authy_local/daemon.py`) to a 16-worker concurrent `ThreadPoolExecutor`, reducing IPC round-trip latency to ~31 us.
- Extracted 841 lines of legacy curses helpers from `src/authy_local/tui.py` into `src/authy_local/_curses_compat.py` and implemented debounced `OptionList` search population (~1.5 ms for 150 virtualized rows).
- Expanded subprocess stdout buffer caps to 2 MiB across Bitwarden (`src/authy_local/backends/bitwarden.py`), KeePassXC (`src/authy_local/backends/keepass.py`), and FIDO2 (`src/authy_local/backends/fido2.py`) backends to support large enterprise vaults without truncation.
- Upgraded `.github/workflows/ci.yml` to Node.js 22 LTS, added `libpam0g-dev` for native Linux PAM compilation, and added automated `dist/wheels/` wheelhouse staging.

### Fixed

- Resolved GitHub Actions CI `test_pam_integration` compilation failures on Ubuntu runners by installing `libpam0g-dev` and fixing Python 3 exception tuple syntax in `tests/test_pam_integration.py`.
- Resolved `test_installer` wheel validation failures by expanding the `Requires-Dist` allowlist regex in `src/authy_local/installer.py` to support `fido2` and `pluggy` alongside `textual` with header string coercion.
- Fixed KeePassXC backend (`src/authy_local/backends/keepass.py`) to filter out non-TOTP password/note entries during XML export parsing and prune `[DIR]` folder markers during directory listing.
- Fixed FIDO2 backend (`src/authy_local/backends/fido2.py`) to gracefully map USB device disconnects, missing `hmac-secret` extensions, and `EACCES` permission errors to `AppError(3)`.
- Eliminated container/sandbox `/proc/{pid}/stat` kernel thread PID collisions in `tests/test_regressions.py` by verifying process UID ownership and `/proc/{pid}/cmdline` identity.

### Security

- Eliminated TOCTOU symlink substitution races in `src/authy_local/importers.py` by opening source files atomically with `os.open(..., os.O_RDONLY | os.O_NOFOLLOW)` and verifying regular file descriptors via `os.fstat(fd)`.
- Prevented secret exposure in tracebacks, crash logs, and debug representations by adding `field(repr=False)` on `OtpParameters.secret` (`src/authy_local/enrollment.py`) and `Completed` subprocess results (`src/authy_local/processes.py`), backed by a top-level CLI exception shield in `src/authy_local/cli.py`.
- Hardened daemon PID file parsing across `daemon_start()`, `daemon_stop()`, `daemon_clean()`, and `daemon_status()` in `src/authy_local/daemon.py` to strictly reject `pid <= 0`, preventing POSIX process-group broadcast signaling (`os.kill(0, ...)` / `os.kill(-1, ...)`).
- Implemented RFC 8259 C JSON string escaping and `explicit_bzero` stack buffer zeroization in `pam/pam_otp_local.c`.
- Enforced strict alphanumeric account label validation (`LABEL`) in `src/authy_local/backends/hardware.py` and `0o600` file permissions on plugin allowlist configurations in `src/authy_local/plugins/manager.py`.
- Implemented deterministic credential zeroization upon Textual modal dismissal and unmount across `AddOtpModal`, `ScopeModal`, `ConfirmDeleteModal`, and `UnlockModal` in `src/authy_local/tui.py`, and guarded `daemon.py` `flush_cache()` against released shared memory buffers.
- Added npm `overrides` in `package.json` (`katex@^0.18.2`, `smol-toml@^1.9.0`) to remediate transitive documentation linter vulnerabilities.

## [2.0.0] - 2026-10-13

### Added

- Universal non-blocking asynchronous architecture in `src/authy_local/async_core.py` providing `AsyncBackend` abstract base class, `AsyncSyncAdapter` thread offloader, and `AsyncMockBackend` for high-throughput concurrency.
- Non-blocking concurrent multi-vault search engine `AsyncFederatedResolver` utilizing `asyncio.gather` with per-backend timeout caps, cross-vault deduplication, and composite origin badges (`[1P+BW]`, `[KP]`, `[GPG]`).
- Universal streaming JSON-RPC 2.0 / CBOR socket protocol over UNIX domain sockets and TCP streams with `AsyncJsonRpcServer` and `AsyncJsonRpcClient` supporting bi-directional notifications.
- Extensible hook-based plugin engine in `src/authy_local/plugins/` powered by `pluggy` with hook specifications for custom credential backends (`otp_local_register_backend`), token generation events (`otp_local_on_token_generated`), custom UI actions (`otp_local_custom_ui_action`), and custom security audit rules (`otp_local_audit_rule`).
- Fail-closed plugin security configuration in `~/.config/authy-local/plugins.json` enforcing explicit operator allowlists for third-party extensions.
- Frozen, semantically versioned public Python API under the `authy_local` namespace with 100% type annotation and strict deprecation warnings for v1.x symbols.
- Backward compatibility adapter layer in `src/authy_local/compat.py` maintaining seamless drop-in operation for existing v1.x scripts and shell wrappers.
- Automated concurrency benchmarks verifying over 3.0x throughput speedup during concurrent multi-vault queries.
- Comprehensive test suites in `tests/test_async_core.py` (10 tests), `tests/test_plugins.py` (7 tests), and `tests/test_benchmark_v2.py` (5 tests).

## [1.6.0] - 2026-10-13

### Added

- Runtime memory forensics module in `src/authy_local/security.py` providing operating-system-level physical RAM page locking (`mlock` / `munlock`), core dump exclusion (`madvise(MADV_DONTDUMP)`), core dump disablement (`prctl(PR_SET_DUMPABLE, 0)` and `setrlimit(RLIMIT_CORE, 0)`), and deterministic bytearray zeroization (`ctypes.memset`).
- Page-aligned `SecureBuffer` allocator and RAII context manager guaranteeing physical memory pinning, core dump protection, bounds validation, and immediate zeroization upon exit or destruction.
- Emergency process signal interception (`SIGINT`, `SIGTERM`, `SIGHUP`) registering global teardown handlers that automatically scrub and zeroize all active allocated buffers before process termination.
- Autonomous Security Auditor v2 in `src/authy_local/auditor.py` analyzing stored OTP credentials for entropy, hygiene, time drift, and environment exposure.
- Shannon entropy analysis (`calculate_shannon_entropy`) identifying repetitive patterns or predictable character distributions; flags low-entropy secrets (<2.5 bits/char) with rule `SEC-005`.
- Host time drift and NTP skew diagnostics (`check_time_drift`) measuring local clock offsets against RFC 6238 timing boundaries; flags offsets >= 1.0s with rule `SEC-006`.
- Process environment and history leak detector (`scan_environment_leaks`) auditing process environment variables, `/proc/$PID/environ`, command-line arguments (`/proc/$PID/cmdline`), and shell history logs (`.bash_history`, `.zsh_history`, `fish_history`); flags plaintext seeds with rule `SEC-007`.
- Guided secret rotation assistant (`generate_rotation_advice`) with CLI flag `otp-local audit --rotate` producing fresh 160-bit cryptographically secure Base32 seeds, algorithm upgrade guidance (SHA1 to SHA256), and valid `otpauth://` URIs.
- Diagnostic probe `memory-security` in `src/authy_local/doctor.py` and `otp-local doctor` reporting operational status of `mlock` page-locking and `madvise_dontdump` core dump exclusion.
- Comprehensive test suites in `tests/test_memory_security.py` (13 tests) and `tests/test_auditor_v2.py` (15 tests).

## [1.5.0] - 2026-10-13

### Added

- Bitwarden vault backend in `src/authy_local/backends/bitwarden.py` utilizing Bitwarden CLI (`bw`) and `BitwardenSessionManager` with secure volatile session caching, automatic expiration timeouts, item enumeration, search, and TOTP generation via `bw get totp` with fallback in-process TOTP generation.
- KeePassXC KDBX4 database engine in `src/authy_local/backends/keepass.py` supporting native `keepassxc-cli` and KDBX/XML fallback parsing with `KeePassSessionManager`, composite credentials (master passwords and keyfiles), item listing, TOTP retrieval, enrollment, and deletion.
- High-performance concurrent multi-vault federation engine in `src/authy_local/federation.py` with `FederatedResolver` querying candidate backends concurrently via `ThreadPoolExecutor`, cross-backend deduplication, origin badges (`[1P]`, `[BW]`, `[KP]`, `[GPG]`, `[TPM]`, `[BW+KP]`), and sub-100ms multi-vault aggregation.
- Unified cross-vault search and priority code retrieval with fail-closed fallback across all configured vaults in `FederatedResolver.search` and `FederatedResolver.retrieve_code`.
- Textual TUI integration for Bitwarden (hotkey `9`), KeePassXC (hotkey `K`), and Federated Multi-Vault (hotkey `0`) in `BackendSelectModal`, and enrollment checkboxes in `AddOtpModal`.
- CLI integration for `--backend bitwarden`, `--backend keepass`, and `--backend federated` across `show`, `copy`, `select`, `enroll`, and `pick`.
- System diagnostics (`otp-local doctor`) probing Bitwarden CLI (`bw`) vault lock status and KeePassXC database availability with automated package manager formulas (`bw`, `keepassxc`, `KeePassXCTeam.KeePassXC`).
- Comprehensive automated test suites in `tests/test_bitwarden_backend.py` (22 tests), `tests/test_keepass_backend.py` (18 tests), and `tests/test_federation.py` (12 tests).

## [1.4.0] - 2026-10-13

### Added

- Resident background authentication daemon (`otp-local daemon`) in `src/authy_local/daemon.py` with standard lifecycle controls (`start`, `stop`, `status`, `reload`), systemd user service generator, automatic cache timeouts, and memory page-locking (`mlockall`).
- High-speed binary CBOR IPC protocol over UNIX domain socket (`/run/user/$UID/otp-local.sock`) in `src/authy_local/ipc.py` with strict Linux `SO_PEERCRED` caller UID verification preventing local privilege escalation.
- Zero-copy POSIX shared-memory circular ring buffer (`/dev/shm/otp-local-$UID`, 64 KiB) in `src/authy_local/shm.py` with cache-line-aligned slots and atomic spinlocks achieving sub-0.01ms lookup latency.
- Native Linux PAM module (`pam/pam_otp_local.c` and `pam/Makefile`) implementing `pam_sm_authenticate` and `pam_sm_setcred` with conversation prompt handling, fail-closed socket integration, and security compiler hardening (`-fstack-protector-strong -D_FORTIFY_SOURCE=2 -fPIC`).
- Linux PAM configuration validator and diagnostic inspection tooling in `src/authy_local/pam_check.py` and CLI flag `otp-local doctor --pam`.

## [1.3.0] - 2026-10-13

### Added

- FIDO2 CTAP 2.1 hardware security key backend in `src/authy_local/backends/fido2.py` utilizing CTAP2 `hmac-secret` / WebAuthn PRF extensions and AES-256-GCM seed encryption.
- Multi-token enrollment architecture supporting primary and secondary backup hardware security keys with synchronized salt configurations (`fido2_add_backup_token`, candidate fallback loop in `fido2_code`).
- Textual TUI `Fido2TouchModal` featuring an interactive pulsing visual touch indicator and timeout countdown timer in `src/authy_local/tui.py`.
- Interactive backend provider selection for `fido2` via hotkey `8` in `BackendSelectModal` and direct token enrollment via `chk-fido2` in `AddOtpModal`.
- CLI enrollment extension via `--fido2` shortcut flag and `--backup-token` flag in `otp-local enroll`.
- Physical authenticator discovery, USB HID device enumeration, and optional user PIN verification for FIDO2 credentials.
- In-memory cryptographic zeroization of decrypted FIDO2 TOTP secrets via `ctypes.memset`.
- Integration of `--backend fido2` across CLI commands (`show`, `copy`, `select`, `enroll`, `pick`), deletion auditing, and `doctor` system diagnostics.

## [1.2.0] - 2026-10-13

### Added

- Native PowerShell 7+ integration module and completions in `shell/otp-local.ps1` with `Get-OtpCode`, `Copy-OtpCode`, `Select-OtpCode`, aliases (`otp`, `totp`, `otpc`), and argument completion.
- NuShell module in `shell/otp-local.nu` providing structured pipeline integration, `otp show`, `otp copy`, and `otp record` table records.
- WSL2 UNIX-to-named-pipe IPC bridge in `src/authy_local/wsl_bridge.py` allowing Linux guest environments to securely query host Windows DPAPI storage.
- Windows DPAPI and Credential Manager backend (`src/authy_local/backends/dpapi.py`) with memory zeroing (`ctypes.memset`) and user/machine entropy derivation.
- Windows diagnostic probing and automated package manager remediation (`winget` and `scoop`) in `otp-local doctor`.

## [1.1.0] - 2026-10-13

### Added

- Native macOS Keychain backend (`src/authy_local/backends/keychain.py`) utilizing `/usr/bin/security` to store, retrieve, enroll, and delete OTP tokens directly within the macOS Keychain.
- Apple Secure Enclave hardware presence detection in system diagnostics (`otp-local doctor`), supporting Apple Silicon Secure Enclave Processor (SEP) via `arm64`/`aarch64` and Intel Macs with T2 Security Chip via `sysctl hw.model` and `system_profiler SPControllerDataType`.
- Automated dependency remediation in `otp-local doctor` via `--install` and `--fix` CLI flags, automatically mapping missing capabilities (`fish`, `pass`, `oathtool`, `yubikey`, `fzf`, `qrencode`, `pinentry`) to Homebrew formulas on macOS.
- `not-applicable` diagnostic status categorization for platform-specific hardware: marks Linux-specific PC TPM 2.0 components (`totpm`, `tpm2-totp`, `tpm-device`) as `not-applicable` rather than `missing` on macOS Darwin.
- TUI `DoctorModal` support for `not-applicable` state with dedicated cyan badge styling (`— N/A`) and non-applicable count tracking in session status.
- CLI `--backend keychain` support across `show`, `copy`, `select`, `enroll`, and `delete` subcommands with zero seed leakage in process arguments.
- Textual TUI support for `keychain` backend across `BackendSelectModal` (numeric hotkey `6`), `AddOtpModal` (`chk-keychain`), `ScopeModal`, and token browsing.
- Deletion audit logging support for `keychain` backend deletions with tamper-evident audit ledger entries in `deletion-audit.log`.

### Fixed

- Expand bounded subprocess sink capacity in `otp-local doctor --install` from 64 bytes to 10 MB (`stdout_cap` and `stderr_cap`) with a 900-second deadline, resolving Homebrew installation failure (`AppError: buffer capacity exceeded`) during formula pouring.
- Exclude `not-applicable` capability lines in legacy curses TUI executor to maintain bounded single-page vertical display within standard 24-line terminal heights, preventing modal pagination traps.

### Changed

- Promoted package version to v1.1.0.
- Updated documentation and README with macOS Keychain performance benchmarks (8.4 ms mean latency), architecture diagrams, and PEP 668 compliant `uv tool` installation workflows.

## [1.0.0] - 2026-10-13

### Added

- Interactive 1Password CLI session unlock subcommand (`otp-local unlock [--account]`).
- Hardware credential backends: YubiKey OATH (`yubikey`) and TPM 2.0 (`tpm2-totp`) across CLI, TUI, and shell completions.
- Plaintext URI list bulk importer (`otp-local import SOURCE --format uri-list`) with comment stripping and account deduplication.
- Systemd socket-activated user daemon unit (`authy-local-agent.socket`) for on-demand zero-overhead activation.
- In-TUI interactive terminal QR code modal (`InteractiveQrModal`, shortcut `v`) and Credential Security Audit modal (`AuditReportModal`, shortcut `u`).
- Structured query modifiers in TUI search filter: `type:`, `tag:`, `algo:`, and `digits:`.
- Native shell completions for `fish`, `bash`, and `zsh` fully supporting all 14 subcommands, options, and hardware backends.
- Ephemeral session agent daemon (`otp-local agent`) over private Unix domain socket with auto-lock and cryptographic memory zeroing.
- Desktop quick-picker (`otp-local pick`) supporting `wofi`, `rofi`, and `fzf` with Wayland detection and notifications.
- Credential Security and Hygiene Auditor (`otp-local audit`) with duplicate seed, weak key, and algorithm checking.
- Terminal QR Code visualizer (`otp-local qr`) rendering compact UTF-8 Unicode half-block QR codes.
- In-process RFC 6238 TOTP and RFC 4226 HOTP calculation engines with Appendix D golden vector verification.
- Steam Guard 5-character alphanumeric token algorithm (`23456789BCDFGHJKMNPQRTVWXY`).
- Offline backup exporter (`otp-local export`) supporting Aegis JSON, line-delimited URIs, CSV, and optional GPG encryption.
- Background clipboard scrubber daemon clearing sensitive OTP codes after a configurable delay with overwrite detection.
- Bulk migration importer (`otp-local import`) supporting Google Authenticator migration payloads, Aegis JSON, and Bitwarden JSON vaults.
- Interactive OTP enrollment in Textual TUI (`AddOtpModal`) and CLI (`otp-local enroll`).
- High-performance Textual TUI migration with responsive bordered layout, action hierarchy, and live countdown timer.

### Fixed

- Prevent terminal locks and freezes on application quit ('q', 'Esc', 'Ctrl+C') by
  introducing global child process tracking, bounded 15-second subprocess execution,
  and instant child process termination on Textual app shutdown.
- Eliminate search latency bottlenecks in TUI token browser by caching search index
  and reusing pre-indexed entries across keystrokes.
- Retain the latest Doctor capability summary in TUI Session Status until the
  next explicit check, without treating it as authentication readiness.
- Preserve terminal session identity for 1Password calls so normal desktop CLI
  authorization can be reused; retain separate process groups for bounded cleanup.
- Remove the unsupported explicit UTF-8 encoding option from OTP retrieval and
  selection. Both use the CLI's UTF-8 default with inherited `OP_*` options removed.

### Changed

- Promoted package version from candidate to final v1.0.0 release.
- Reorder and sort TUI main menu items by operational use-case hierarchy:
  Token Retrieval (Browse and show [1], Browse and copy [2], Show code [3], Copy code [4]),
  Credential Onboarding (Add OTP entry [5]), Configuration & Scopes (Saved scope [6]),
  Diagnostics & System Health (Doctor [7]), and Setup, Maintenance & Guidance
  (Installation preview [8], Private migration guide [9]).
- Display current action category in the TUI detail workspace pane while preserving
  OptionList index navigation invariants.

- Credential Security and Hygiene Auditor (`otp-local audit`) inspecting vaults for
  duplicate seed re-use, weak keys (<80 bits or test vectors), non-standard digest algorithms,
  and metadata hygiene, with terminal reports and machine-readable `--json` output.
- Terminal QR Code visualizer (`otp-local qr`) rendering compact UTF-8 Unicode half-block QR
  codes directly to terminal standard output for rapid mobile scanner re-enrollment.
- RFC 4226 HOTP counter-based OTP algorithm engine with Appendix D golden vector verification,
  `hotp://` URI parsing/serialization, and Aegis JSON counter preservation.
- Enhanced system diagnostics in `otp-local doctor` with non-authenticating capability probes
  for `qrencode`, `pinentry`, and `gpg-agent` daemon socket reachability.
- Native in-process RFC 6238 TOTP computation engine supporting SHA-1, SHA-256,
  and SHA-512 algorithms with golden vector verification and sub-millisecond evaluation.
- Steam Guard 5-character alphanumeric token algorithm (`23456789BCDFGHJKMNPQRTVWXY`),
  `steam://` URI ingestion, and custom 5-digit / variable-period support.
- Offline backup exporter (`otp-local export`) supporting line-delimited RFC 6238 URIs,
  standard Aegis JSON, and CSV vaults, with enforced 0600 file modes and optional GPG encryption.
- Sub-second NTP clock drift measurement in `otp-local doctor` extracting exact millisecond
  offset from `timedatectl timesync-status`.
- Desktop integration assets: Freedesktop `.desktop` application entries (`authy-local.desktop`,
  `otp-pick.desktop`), systemd user service unit (`authy-local-agent.service`), and native
  shell completions for `fish`, `bash`, and `zsh`.
- Comprehensive Desktop and System Integration Guide in `docs/13-desktop-integration.md`.
- Ephemeral session agent daemon (`otp-local agent`) over private Unix domain socket
  with strict 0o700/0o600 file permissions, idle auto-lock, and cryptographic memory clearing.
- Native desktop quick-launcher (`otp-local pick`) supporting `wofi`, `rofi`, and `fzf`
  with automatic GUI display detection, desktop notifications, and `--stdout` pipeline support.
- Multi-term tokenized and subsequence fuzzy search ranking with ReDoS immunity and
  sub-millisecond evaluation across 5,000 items.
- Hierarchical folder and namespace navigation (`f` key) in TUI token browser with
  per-folder item counts and interactive selection modal.
- Automated background clipboard scrubber daemon clearing sensitive OTP codes after
  a configurable delay (default 45 seconds) with overwrite detection.
- Bulk migration importer (`otp-local import`) supporting Google Authenticator migration
  payloads (pure-Python protobuf varint decoder), Aegis JSON, and Bitwarden JSON vaults
  with preview `--dry-run` and verified `--apply` modes.
- Hardware key and TPM 2.0 support probing connected YubiKey OATH credentials (`ykman`)
  and `tpm2-totp` hardware devices in system diagnostics (`otp-local doctor`).

- Interactive OTP enrollment in Textual TUI (Action 5: "Add OTP entry", hotkeys `5`, `a`, `e`)
  supporting raw Base32 secret strings, `otpauth://totp/` URIs, and screen QR code capture.
- Secure QR code decoding via standard input streaming to `zbarimg` and Wayland native
  clipboard capture via `wl-paste`, avoiding unencrypted temporary file creation.
- Live real-time derived TOTP code preview with a dynamic 30-second countdown bar and
  "Copy Test Code" clipboard action for immediate service challenge verification.
- Multi-backend persistence targeting 1Password (Login category tagged `"OTP"`), GPG
  `pass-otp`, and hardware TPM `totpm`, with label sanitization and cryptographic memory zeroing.
- CLI enrollment extension via `otp-local enroll` supporting `--qr-image`, `--qr-clipboard`,
  `--title`, and `--tags` for 1Password, pass-otp, and totpm backends.
- Saved optional 1Password TUI metadata tag filter, defaulting to `OTP` for new
  and existing scopes; clearing the tag includes all scoped Login metadata.

- Confirmed single-entry deletion in local GPG/TPM TUI browsers, with private
  coarse intent auditing, cancellation safeguards and refreshed metadata.
- Resident private TUI backend scope and native searchable item browsing, with
  selected-item show/copy and explicit metadata refresh; CLI scope stays explicit.
- Dashboard TUI with bordered panes, backend selection, keyboard navigation,
  editable multi-field scope forms and scrolling results, inspired by btop/htop.
- Explicit pass-otp/GPG and totpm local-mode adapters, validated hidden CLI
  enrollment, bounded metadata selection and shared clipboard handling.
- Pinned native-runtime preview/apply with ownership checks; no key creation,
  TPM provisioning, package installation or account changes during apply.
- Public operator guides bundled in the wheel through `otp-local guide`.
- Official 1.0.0 release; final acceptance and migration remain operator gates.
- Phase 1 Python companion with non-authenticating capability reporting and
  explicitly scoped, validated OTP display.
- Bounded subprocess handling, static diagnostics and synthetic regression tests.
- Pinned developer tools, local validation gates and Phase 0 readiness templates.
- Scoped ephemeral fzf selection and explicit Wayland clipboard handoff.
- Fish wrappers and preview-first offline installation with ownership checks,
  rollback, conservative uninstall and isolated-home tests.
- Standard-library curses TUI integrating shared commands, installation preview
  and private migration guidance; dedicated sprint and architecture decision.
- Private synthetic acceptance, pilot and bounded-batch operator checklists.

Real-home installation and account migration require their operational checkpoints.
This development version is not a live readiness or migration-completion claim.
