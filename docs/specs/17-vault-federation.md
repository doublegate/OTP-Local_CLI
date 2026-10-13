# Enterprise Multi-Vault Federation Specification

Status: Planned for release v1.5.0.
Extends [Architecture](02-architecture.md), [Optional Backends](08-optional-backends.md), and [Textual TUI](11-tui.md).

## 1. Overview and Requirements

Enterprises and advanced operators frequently distribute credentials across multiple password management systems. This specification establishes a unified multi-vault federation architecture integrating Bitwarden/Vaultwarden CLI (`bw`), direct KeePassXC `.kdbx4` encrypted databases, 1Password (`op`), GPG (`pass-otp`), and hardware TPM/Keychain stores.

Key requirements:

1. Bitwarden / Vaultwarden integration via official `bw` CLI tool.
2. Direct native KeePassXC `.kdbx4` database parsing and generation without requiring GUI utilities.
3. Federated resolver: Single unified search query aggregates items across all active vaults.
4. Source badges in Textual TUI (`[1P]`, `[BW]`, `[KP]`, `[GPG]`, `[TPM]`, `[KEYCHAIN]`).
5. Cross-vault audit and deduplication: Detect duplicate seeds, conflicting configurations, and synchronization drift.

## 2. Bitwarden / Vaultwarden Backend (`BitwardenBackend`)

### 2.1 Execution & Session Model

- Interfacing binary: `/usr/bin/bw`.
- Session Management:
  - Supports `BW_SESSION` environment variable.
  - Interactive unlock: When locked, prompts via system pinentry or Textual modal for master password/PIN and caches session token in protected RAM.
  - Auto-lock timeout: Configurable timer (default 15 minutes) zeroes out session tokens.
- Item Retrieval:
  - Uses `bw list items --search <query>` with JSON parsing.
  - Extracts TOTP code using `bw get totp <item-id>`.

## 3. KeePassXC KDBX4 Direct Backend (`KeePassBackend`)

### 3.1 Direct KDBX4 Database Processing

- File format: Standard KeePass 2.x KDBX4 file format.
- Encryption algorithms: AES-256 or ChaCha20 cipher; Argon2d/Argon2id key derivation function.
- Authentication modes:
  - Master password.
  - Keyfile (`.key` or `.keyx`).
  - Composite credentials (password + keyfile).
- TOTP parsing: Reads RFC 6238 standard attributes (`otp`, `TOTP Seed`, `TimeOtp-Secret-Base32`).

## 4. Federated Multi-Vault Resolver (`src/authy_local/federation.py`)

### 4.1 Aggregation & Conflict Resolution

The federated resolver iterates over all configured backends:

1. Enumerates items concurrently using worker threads or coroutines.
2. Normalizes service and account names.
3. Applies source attribution badges:
   - `[1P]`: 1Password
   - `[BW]`: Bitwarden / Vaultwarden
   - `[KP]`: KeePassXC
   - `[GPG]`: pass-otp
   - `[TPM]`: totpm
   - `[KC]`: macOS Keychain
4. Deduplication: Flags identical accounts present in multiple vaults.
   - If seeds match: Marked as `"Synchronized (redundant)"`.
   - If seeds differ: Marked as `"Conflicting Seeds (Action Required)"`.

## 5. Security & Isolation

- Vault credentials and master keys are never cross-pollinated or shared across stores.
- Master keys for KDBX databases are held only in page-locked memory and zeroed immediately after database sync.
- Read-only default: Multi-vault federation is read-only unless explicit write operations are invoked.
