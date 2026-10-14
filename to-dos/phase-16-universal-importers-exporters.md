# Phase 16: Universal Authenticator Ecosystem Importers and Exporters (v2.4.0)

Status: Planned; milestone for release v2.4.0. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Provide seamless migration to and from all major mobile and desktop authenticator ecosystems by implementing zero-knowledge decoders for Aegis Authenticator (encrypted JSON), 2FAS (encrypted backup), Ente Auth, Google Authenticator (`otpauth-migration://` protobuf QR streams), 1Password (1PUX), and Bitwarden.

## Entry Conditions and Dependencies

- Phase 15 completed and verified.
- Protobuf decoding and AES-GCM / SCrypt decryption utilities.

## Sprint Sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-16.1](sprints/16.1.md) | Mobile authenticator ingestion (Aegis, 2FAS, Ente, Google Protobuf) | Entry gate |
| [S-AUTH-16.2](sprints/16.2.md) | Password manager interoperability (1Password, Bitwarden, KeePassXC) | S-AUTH-16.1 |

All tasks in each sprint must have automated synthetic test verification before closing.

## Deliverables and Evidence

- Migration engine in `src/authy_local/migration.py` with modular format parsers:
  - Aegis encrypted JSON parser with SCrypt / AES-256-GCM decryption.
  - 2FAS encrypted backup reader.
  - Google Authenticator `otpauth-migration://` protobuf QR batch decoder.
  - 1Password 1PUX zip and Bitwarden json/csv importers.
- CLI subcommand `otp-local migrate import --format <fmt> <file>` and `--dry-run` inspection flag.
- Textual TUI visual migration wizard with batch confirmation modal.
- Automated fixture-based test suites in `tests/test_migration_importers.py` and `tests/test_migration_exporters.py`.
- Architectural documentation and format matrix in `docs/operations/migration-formats.md`.

## Exit Criteria

- Successful batch import of 100+ sample accounts across all supported format fixtures.
- Strict schema validation rejecting corrupted, malformed, or untrusted payload injections.
- In-memory secret scrubbing following import completion.
