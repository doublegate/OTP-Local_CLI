# ADR 0012: Enterprise Multi-Vault Federation and Open Password Formats

- Status: Proposed for release v1.5.0 (Phase 10)
- Supersedes: None; extends Default Store (ADR 0001) and Explicit Local Backends (ADR 0005)

## Context

Operators and enterprise organizations often maintain credentials across disjoint systems: personal items in 1Password or Bitwarden, organizational credentials in Vaultwarden, and offline air-gapped backups in KeePassXC `.kdbx4` databases. Navigating multiple distinct CLIs and GUIs increases cognitive overhead and risks desynchronization.

## Decision

1. Implement `BitwardenBackend` in `src/authy_local/backends/bitwarden.py` wrapping the official `bw` CLI and caching session tokens safely in protected RAM.
2. Implement direct reading and writing of KeePassXC `.kdbx4` databases in `src/authy_local/backends/keepass.py` supporting Argon2 KDF, AES/ChaCha20 encryption, keyfiles, and hardware keys.
3. Implement a federated multi-vault resolver in `src/authy_local/federation.py` that queries configured backends concurrently and presents an aggregated, deduplicated catalog.
4. Display origin badges in the Textual TUI (`[1P]`, `[BW]`, `[KP]`, `[GPG]`, `[TPM]`, `[KC]`).
5. Provide cross-vault synchronization audit reports detecting identical seeds across backends or conflicting configurations.

## Consequences

- Eliminates tool fragmentation by creating a single unified terminal view across all password manager systems.
- Adds full support for the open-source KeePass KDBX4 format, providing true offline, air-gapped credential storage without vendor lock-in.
- Strictly confines vault master keys and session tokens to their respective backend boundaries with zero cross-store leakage.
