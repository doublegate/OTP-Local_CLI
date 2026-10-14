# Phase 15: Zero-Knowledge Encrypted Backup and Cross-Platform Sync (v2.3.0)

Status: Planned; milestone for release v2.3.0. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Deliver sovereign, zero-knowledge encrypted backup and cross-platform synchronization by establishing an open Age-encrypted vault container format (`.otpbackup` / `.age`) with Argon2id password-based key derivation, paired with non-blocking sync adapters for self-hosted WebDAV (Nextcloud / ownCloud) and S3-compatible object storage (MinIO / AWS S3).

## Entry Conditions and Dependencies

- Phase 14 completed and verified.
- Memory protection primitives in `src/authy_local/security.py` active.

## Sprint Sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-15.1](sprints/15.1.md) | Sovereign encrypted vault container (Age / Argon2id) | Entry gate |
| [S-AUTH-15.2](sprints/15.2.md) | Decentralized sync transports (WebDAV, S3, conflict resolution) | S-AUTH-15.1 |

All tasks in each sprint must have automated synthetic test verification before closing.

## Deliverables and Evidence

- Encrypted backup engine in `src/authy_local/backup.py` implementing Age container encryption with Argon2id parameters (m=64MB, t=3, p=4) and authenticated payload checksums.
- Sync transport module in `src/authy_local/sync.py` implementing WebDAV and S3 client adapters with etag tracking and three-way conflict merging.
- CLI subcommands `otp-local backup export`, `otp-local backup import`, and `otp-local sync`.
- Textual TUI backup & sync management modal with status indicators.
- Comprehensive automated test suite in `tests/test_backup.py` and `tests/test_sync.py`.
- Architectural specification in [docs/specs/22-encrypted-backup-and-sync.md](../docs/specs/22-encrypted-backup-and-sync.md).

## Exit Criteria

- Vault backup archives decryptable using standard command-line `age` utility with user passphrase.
- Zero plaintext seed leakage during sync transfers or temporary file generation.
- Three-way merge resolution tested against simultaneous remote and local credential modifications.
