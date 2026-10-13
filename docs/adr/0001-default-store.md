# ADR 0001: Use 1Password as the default TOTP store

- Status: Accepted by operator, 2026-10-12
- Date: 2026-10-11

## Context

The reference contains several possible stores and overlapping helper conventions.
The project guidance prefers one authoritative seed accessible through desktop,
mobile, browser and CLI. Maintaining duplicate stores increases exposure and
rotation/recovery obligations.

## Decision

Use 1Password for ordinary TOTP accounts and retrieve codes through its existing
CLI. Keep enrollment in native UI. Treat pass-otp and totpm as independent optional
branches requiring a demonstrated need and separate recovery evidence.

This is an architecture choice, not authorization to read a vault or change MFA.

## Options considered

| Option | Tradeoff |
|---|---|
| 1Password default | Existing cross-device experience; relies on provider/app availability |
| Independent GPG store default | Local control; additional key backup and synchronization burden |
| TPM store default | Hardware-bound protection; device-loss and portability constraints |
| Multiple defaults | More copies and conflicting authority; harder rotation reconciliation |

## Consequences

The baseline contains no seed exporter or duplicate seed synchronization. Optional
stores can be skipped without blocking helper completion. Proprietary Authy
integrations remain explicit exceptions rather than forced conversions.

## Actions

Scope confirmed at the phase-0 gate; verify companion use through a later human pilot.
See [ADR 0002](0002-implementation-boundary.md) and
[ADR 0003](0003-migration-and-optional-stores.md).
