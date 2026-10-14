# Phase 18: Enterprise Cloud Vault Federation (v2.6.0)

Status: Planned; milestone for release v2.6.0. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Deliver enterprise-grade cloud vault federation by implementing high-security, authenticated client adapters for HashiCorp Vault (TOTP and Transit secrets engines), AWS Secrets Manager & KMS, Google Cloud Secret Manager & KMS, and Azure Key Vault with Managed Identity authentication.

## Entry Conditions and Dependencies

- Phase 17 completed and verified.
- Async federated resolver (`src/authy_local/async_core.py`) and memory protection operational.

## Sprint Sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-18.1](sprints/18.1.md) | HashiCorp Vault integration (TOTP engine and Transit decryption) | Entry gate |
| [S-AUTH-18.2](sprints/18.2.md) | Cloud provider secrets engines (AWS, GCP, Azure Key Vault) | S-AUTH-18.1 |

All tasks in each sprint must have automated synthetic test verification before closing.

## Deliverables and Evidence

- HashiCorp Vault backend in `src/authy_local/backends/vault.py` supporting token, AppRole, and mTLS client authentication with auto-renewing leases.
- Cloud secrets module in `src/authy_local/backends/cloud_vaults.py` supporting:
  - AWS Secrets Manager with AWS KMS envelope encryption.
  - Google Cloud Secret Manager with Cloud KMS envelope decryption.
  - Azure Key Vault with Azure Managed Identity and Service Principal authentication.
- CLI backend switches `--backend vault`, `--backend aws`, `--backend gcp`, `--backend azure`.
- Comprehensive automated mock test suites in `tests/test_vault_backend.py` and `tests/test_cloud_vaults.py`.
- Architectural documentation in `docs/specs/18-enterprise-cloud-vaults.md`.

## Exit Criteria

- Zero hardcoded cloud credentials or tokens; strict authentication via environment variables or native cloud metadata services.
- Resilient retry logic with exponential backoff on transient cloud API throttling.
- Memory zeroization of cloud API response buffers immediately following TOTP generation.
