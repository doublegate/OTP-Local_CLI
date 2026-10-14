# 22. Specification: Zero-Knowledge Encrypted Backup and Sync

## 1. Overview

This specification establishes an open, sovereign container format for zero-knowledge vault backups using Age encryption and Argon2id key derivation, alongside decentralized synchronization protocols for WebDAV and S3-compatible endpoints.

## 2. Vault Backup Container Specification (.otpbackup / .age)

### 2.1 Encryption Layer

- Cipher: Age encryption format (X25519, ChaCha20-Poly1305).
- Key Derivation Function: Argon2id.
  - Memory Cost: 64 MiB ($m = 65536$).
  - Time Cost: 3 iterations ($t = 3$).
  - Parallelism: 4 threads ($p = 4$).
  - Salt: 16 cryptographically random bytes.

### 2.2 Payload Schema

- Serialized JSON payload containing version headers, vault metadata, account tokens, and SHA256 integrity digest.
- Files written with atomic rename and strict `0o600` permissions.

## 3. Decentralized Synchronization Protocols

### 3.1 WebDAV Sync

- Target: Nextcloud, ownCloud, or custom Apache/Nginx WebDAV.
- Method: Conditional `PUT` and `GET` using HTTP `If-Match` and `ETag` headers.

### 3.2 S3-Compatible Sync

- Target: MinIO, AWS S3, Cloudflare R2, Backblaze B2.
- Authentication: AWS Signature Version 4 (SigV4).

### 3.3 Conflict Resolution

- Three-way merge engine comparing local, remote, and base state vectors.
- Non-destructive conflict resolution: differing account versions are preserved with conflict timestamps rather than dropped.

## 4. Security Guarantees

- Encryption and decryption occur strictly on the local client machine.
- Cloud endpoints store exclusively opaque Age-encrypted ciphertexts.
