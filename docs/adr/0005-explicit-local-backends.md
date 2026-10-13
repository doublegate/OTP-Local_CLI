# ADR 0005: Explicit local backends and private adoption

- Status: Accepted by operator, 2026-10-12
- Supersedes: optional adoption undecided in ADR 0003; preserves 1Password default

## Context

The operator selected both pass-otp and totpm for the cohesive CLI/TUI, a dedicated
GPG key, totpm local mode and a privately selected account subset. Authy remains
retained throughout development. Migration batches and private recovery evidence
are not implied by implementation authorization.

## Decision

Use explicit backend selection. Keep 1Password as default and never automatically
retry an operation against another store. Maintain flat opaque labels, dedicated
private directories and strict six/eight-digit output validation. Enrollment is
an explicit CLI action with hidden confirmed input and suppressed diagnostics;
the TUI cannot enroll, apply installation or retire accounts.

Pin pass-otp's reviewed stdin-safe extension and compatible oathtool behavior.
Use totpm 0.1.2 local mode, built from the reviewed revision without bulk import.
Require exact unique metadata matches before its partial-name generation call.
Support SHA-1 only for totpm; unsupported algorithms remain explicit exceptions.

Keep every adopted duplicate current during service rotation. There is no seed
export, synchronization or automated copying from 1Password. Dedicated GPG backup
and restore and independent TPM-loss recovery require private operator evidence.

## Consequences

Local totpm binds seeds to hardware but offers no protection against another
process executing as the same user. A TPM database is not a portable seed backup.
The pass store and its private GPG key need independently recoverable protection.
Store directories remain outside application uninstall ownership.

Development and local release readiness can advance independently of account
migration. Phase 5 operational closure still requires genuine recovery and
reconciliation evidence. Authy retirement is explicitly deferred.
