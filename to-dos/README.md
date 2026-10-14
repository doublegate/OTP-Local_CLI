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
| [7: Windows DPAPI](phase-7-windows-dpapi.md) | [7.1](sprints/7.1.md), [7.2](sprints/7.2.md) | Windows DPAPI backend, PowerShell/NuShell wrappers, and WSL2 interop |
| [8: FIDO2 CTAP2.1](phase-8-fido2-ctap2.md) | [8.1](sprints/8.1.md), [8.2](sprints/8.2.md) | FIDO2 hardware token HMAC-secret derivation and touch presence |
| [9: IPC & PAM](phase-9-pam-low-latency-ipc.md) | [9.1](sprints/9.1.md), [9.2](sprints/9.2.md) | Low-latency UNIX socket daemon, shared memory, and Linux PAM module |
| [10: federation](phase-10-vault-federation.md) | [10.1](sprints/10.1.md), [10.2](sprints/10.2.md) | Bitwarden CLI, KeePassXC KDBX4 direct engine, and multi-vault resolver |
| [11: security v2](phase-11-security-auditor-v2.md) | [11.1](sprints/11.1.md), [11.2](sprints/11.2.md) | Memory forensics hardening (mlock/MADV_DONTDUMP) and security auditor v2 |
| [12: v2 architecture](phase-12-v2-architecture.md) | [12.1](sprints/12.1.md), [12.2](sprints/12.2.md) | Universal async core, plugin hook engine, and v2.0.0 public API freeze |
| [13: secret service & biometrics](phase-13-secret-service-biometrics.md) | [13.1](sprints/13.1.md), [13.2](sprints/13.2.md) | Freedesktop Secret Service (D-Bus) and platform biometrics (v2.1.0) |
| [14: specialized protocols](phase-14-specialized-otp-protocols.md) | [14.1](sprints/14.1.md), [14.2](sprints/14.2.md) | Steam Guard, Blizzard, Yandex, and RFC 4226 HOTP counter sync (v2.2.0) |
| [15: encrypted sync & backup](phase-15-encrypted-backup-sync.md) | [15.1](sprints/15.1.md), [15.2](sprints/15.2.md) | Sovereign Age/Argon2id encrypted vault and WebDAV / S3 sync (v2.3.0) |
| [16: universal migrators](phase-16-universal-importers-exporters.md) | [16.1](sprints/16.1.md), [16.2](sprints/16.2.md) | Aegis, 2FAS, Ente, Google Protobuf, and password manager importers (v2.4.0) |
| [17: desktop launchers](phase-17-desktop-launchers.md) | [17.1](sprints/17.1.md), [17.2](sprints/17.2.md) | Waybar/Polybar streaming, Raycast, Alfred, and Rofi/Wofi pickers (v2.5.0) |
| [18: cloud vaults](phase-18-enterprise-cloud-vaults.md) | [18.1](sprints/18.1.md), [18.2](sprints/18.2.md) | HashiCorp Vault, AWS, GCP, and Azure Key Vault federation (v2.6.0) |
| [19: hardware key admin](phase-19-hardware-key-management.md) | [19.1](sprints/19.1.md), [19.2](sprints/19.2.md) | YubiKey OATH touch policy enforcement and virtual CTAP2 CI loopback (v2.7.0) |
| [20: native accelerator](phase-20-native-accelerator.md) | [20.1](sprints/20.1.md), [20.2](sprints/20.2.md) | PyO3 native Rust cryptographic engine and zero-copy IPC ring buffer (v2.8.0) |
| [21: nextgen TUI](phase-21-tui-nextgen.md) | [21.1](sprints/21.1.md), [21.2](sprints/21.2.md) | Textual TUI 2.0 with circular countdown rings, tags, and webcam QR (v2.9.0) |
| [22: passkey bridge](phase-22-passkey-bridge-v3.md) | [22.1](sprints/22.1.md), [22.2](sprints/22.2.md) | FIDO2 Passkey software authenticator and WebAuthn assertion bridge (v3.0.0) |

Phase 4 is optional. Neither pass-otp nor totpm is required for the 1Password-only base.
The existing [foundation checklist](00-foundation.md) is a milestone-level preflight aid;
the detailed phase/sprint plans define the ordered work. T-AUTH-001, T-AUTH-002, and
T-AUTH-003 remain milestone aliases, distinct from task IDs T-AUTH-010 through T-AUTH-227.

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
