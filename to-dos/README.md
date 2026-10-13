# Delivery plans

These plans take the project from design through tested helper delivery, human-operated
migration, and evidence-based closure. Phases 0–2 are complete; Phase 3 awaits private operator checkpoints in
[PROJECT-STATUS.md](../PROJECT-STATUS.md). [ROADMAP.md](../ROADMAP.md) allocates stable task IDs.

## Sequence

| Phase | Sprints | Completion outcome |
|---|---|---|
| [0: foundation](phase-0-foundation.md) | [0.1](sprints/0.1.md), [0.2](sprints/0.2.md) | Reviewed design and human readiness |
| [1: core](phase-1-core.md) | [1.1](sprints/1.1.md), [1.2](sprints/1.2.md) | Tested doctor and scoped show |
| [2: UX and rollout](phase-2-ux-rollout.md) | [2.1](sprints/2.1.md), [2.2](sprints/2.2.md), [2.3](sprints/2.3.md) | Selection, clipboard, fish, reversible installer, cohesive TUI |
| [3: migration](phase-3-migration.md) | [3.1](sprints/3.1.md), [3.2](sprints/3.2.md) | Pilot and reconciled service dispositions |
| [4: optional backends](phase-4-optional-extensions.md) | [4.1](sprints/4.1.md), [4.2](sprints/4.2.md) | Selected backend evidence or explicit skips |
| [5: completion](phase-5-completion.md) | [5.1](sprints/5.1.md), [5.2](sprints/5.2.md) | Recovery, hardening, and conditional retirement |
| [6: enrollment](phase-6-otp-enrollment.md) | [6.1](sprints/6.1.md), [6.2](sprints/6.2.md) | Interactive addition from secret string or screen QR code |

Phase 4 is optional. Neither pass-otp nor totpm is required for the 1Password-only base.
The existing [foundation checklist](00-foundation.md) is a milestone-level preflight aid;
the detailed phase/sprint plans define the ordered work. T-AUTH-001, T-AUTH-002, and
T-AUTH-003 remain milestone aliases, distinct from task IDs T-AUTH-010 through T-AUTH-061.

## Execution discipline

1. Read the relevant [derived specifications](../docs/00-index.md), sprint, and current status.
2. Resolve entry blockers and obtain action-specific authorization where required.
3. Implement with failing synthetic tests first; human tasks use private operator evidence.
4. Run the affected checks, then the implemented local gate; retain honest fail/skip results.
5. Review exit conditions and update aggregate status only when the evidence supports it.

Use scratch sprint notes under /tmp/Authy-to-1Password_Local/; durable plans stay here.
The original reference is immutable. Add dated corrections and sync derived specifications.

## Scope and stopping points

Current authorization covers Phase 4–5 software implementation, both native
backends, the dashboard redesign and local package integration. Private human
MFA/key/TPM operations remain operator-only. Authy is retained. No real OTP
access, commit, tag, push or publication is authorized.

Development uses synthetic subprocess fixtures; no production vault or network is a test dependency.
Keep account identities, item IDs, recovery codes, seed material, and private progress outside this tree.
Record only aggregate counters and non-secret attestations in repository status/evidence.

Completion has three separate claims: helper delivery, supported-account migration, and
full Authy retirement. Proprietary exceptions can permit closure with retained Authy use;
they cannot support a false claim that Authy is fully retired. Seed rotation may invalidate
old Authy codes, so retaining an entry is never sufficient recovery evidence.

## Estimates

Each sprint gives an active-effort estimate for one developer/operator. Human availability,
service-specific recovery, approval prompts, and batch size can dominate elapsed time.
Use the estimates to choose bounded work sessions; no date is a deadline or authorization.
