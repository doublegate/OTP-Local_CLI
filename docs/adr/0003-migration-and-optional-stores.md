# ADR 0003: Re-enroll accounts individually and gate optional stores

- Status: Baseline accepted by operator, 2026-10-12; optional adoption undecided until phase 4
- Date: 2026-10-11

## Context

Authy desktop extraction examples age poorly as vendor APIs and attestation change.
Export diagnostics can disclose seeds or device credentials. A successful helper
test does not establish a working recovery path for any real service.

## Decision

Use provider-supported per-service re-enrollment as the baseline migration route.
Require independent recovery before each change and a fresh login afterward.
Retaining an old Authy entry is precautionary; seed rotation may invalidate it.

Adopt pass-otp or totpm only after stating the outage/recovery need, verifying a
selected release and passing synthetic compatibility and recovery checks. Do not
include unsupported Authy extraction in the implementation scope.

## Options considered

| Option | Tradeoff |
|---|---|
| Individual re-enrollment | More operator work; clear provider-supported verification boundary |
| Bulk export/import | Faster on paper; compatibility, diagnostic disclosure and recovery uncertainty |
| Mandatory duplicate stores | Extra availability; extra exposure and rotation work for every account |
| Optional duplicate stores | Bounded evaluation; baseline can finish without hardware/key dependencies |

## Consequences

Migration cannot be unattended. Some proprietary integrations may require Authy
to remain. Software completion, account reconciliation and Authy retirement are
reported separately. A TPM database backup alone is not treated as recovery.

## Actions

Execute [pilot and batches](../07-migration-and-recovery.md) only when authorized.
Record adopted/skipped optional decisions and apply the
[completion matrix](../09-operations-and-completion.md).
