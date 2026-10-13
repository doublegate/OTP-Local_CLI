# ADR 0007: Resident scope and confirmed local item deletion

- Status: Accepted by explicit operator requests, 2026-10-12
- Supersedes: per-operation ephemeral account/vault scope in ADR 0006 and the
  prior read-only local-store TUI boundary; retains all enrollment boundaries

## Context

The operator requested saved backend scope, item browsing and then deletion of
selected GPG and TPM entries. Deletion must identify exactly one local record;
removing a whole store, key or service recovery method is outside the request.

The pinned totpm 0.1.2 native deletion command uses substring matching through
SQL LIKE before selecting a row. A recheck followed by that command cannot
ensure the confirmed tuple remains its target under concurrent changes.
See [pinned deletion](https://github.com/koditoriet/totpm/blob/6789ed7f8616e4d90e8d6670f04fe815bd34462b/src/commands/del.rs)
and [database implementation](https://github.com/koditoriet/totpm/blob/6789ed7f8616e4d90e8d6670f04fe815bd34462b/src/db/mod.rs).

## Decision

Store only validated scope IDs/paths in a private profile. Keep item inventories
and codes transient. Offer deletion only within local-backend browsers, with the
selected entry displayed and exact typed `DELETE` confirmation required.

Unlink one validated flat GPG ciphertext using an anchored directory descriptor.
For the pinned TPM local format, open the existing private SQLite database,
validate its schema/version and reject unexpected objects. Use a bounded
transaction and exact binary service/account equality; require one matching row.
Never invoke substring-based native deletion or read/decrypt seed blobs.

Before attempting removal, durably append a private audit entry containing UTC,
UID, backend and coarse action/scope only. Audit failure blocks deletion.

## Consequences

Database compatibility is deliberately restricted to the reviewed schema;
upgrades need renewed review. File/transaction checks reduce accidental wrong-item
removal but do not isolate the application from malware acting as its own user.
Deletion is local record removal, without a secure-erasure or seed-revocation
claim. Independent backups, other stores, GPG keys and the TPM key remain intact.
1Password deletion, bulk removal, enrollment and account/service changes remain
outside this TUI capability. Existing Authy retention remains in force.
