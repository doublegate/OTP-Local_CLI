# Phase 4–5 software verification — 2026-10-12

This report separates delivered software from private operational acceptance.
Both optional stores and the dashboard are implemented. Phase 4–5 operational
closure remains open for dedicated-key recovery, physical TPM use, selected real
adoption, full inventory reconciliation and recovery/privacy attestations.
Authy is retained. No commit, tag, push, publication or real account action occurred.

## Delivered candidate

Version: `1.0.0rc1`. Wheel SHA-256:
`5539af5026aa7c0b4eebaf2733f783e5e9bb7ccf0c9cecb68899d34c8997bcc4`.

- Explicit pass-otp/GPG and totpm local-mode show/copy/select, shared bounded
  output/clipboard handling and no automatic backend fallback.
- Confirmed hidden CLI enrollment with explicit `--apply`, ready-backend checks
  before input, no overwrite and no secret in argv/environment/diagnostics.
- btop/htop-inspired stdlib curses dashboard, backend picker, multi-field hidden
  forms, validation/editing, resize handling and scrolling results.
- Public guides available through `otp-local guide`, including setup and exact
  private acceptance commands (`guide acceptance`); their
  generated bundle is checked against authored specs before building.
- Pinned native assets and licenses with separate private ownership manifest,
  collision refusal, resumable apply and no key/TPM/account provisioning.

The [installation record](2026-10-12-candidate-installation.md) fixes the concrete
footprint. The previous development wheel is archived under `dist/archive/` and
installed rollback inputs are retained. Native stores/assets remain independent
of helper rollback/uninstall.

## Automated and native evidence

The implemented gate is `bash scripts/check.sh`. The latest complete test run
passed **177 tests**, with **94% branch-inclusive aggregate coverage** and **100%**
for scope/code validation plus the 1Password adapter. Ruff lint and format,
ShellCheck and Markdown lint passed. Local links, 52 task IDs, the unchanged
reference hash and isolated wheel smoke also pass. Final installation checks
are recorded below.

Native integration used public synthetic credentials only:

| Check | Result and limits |
| --- | --- |
| Actual pass/GPG enrollment and generation | Passed using staged pass 1.7.4, oath 2.6.14 and hardened extension; independent HMAC/time oracle |
| Actual oathtool secret transport | Interceptor verified `-` stdin operand and absence of seed/URI from actual argv; native generation still matched oracle |
| Actual GPG backup/import/restore | Passed with a newly created disposable test key and separate scratch keyring; no operator key or backup read |
| Actual totpm 0.1.2 with swtpm | Enrollment, exact metadata selection and independent oracle passed in a loopback emulator |
| Unavailable TPM | Stopping only that emulator made retrieval fail closed with static exit 4 |
| Full native extension regression | Safe stdin on synthetic 2.6.14/2.10.0; old 2.6.4 refused despite inherited safe flag; HOTP refused without counter mutation |
| Installed dashboard/fish | 80×24 controlling PTY startup, q exit 0 and terminal restoration passed; three installed fish wrapper help/syntax checks passed |
| 1Password session reuse | Session-preservation regressions pass; prior private operator test confirmed second same-terminal Show had no additional GUI prompt |

Native integration scripts and disposable state are under
`/tmp/Authy-to-1Password_Local/local-integration/`; they are local evidence, not
portable CI fixtures. The default suite has repeatable synthetic native extension
fixtures. Neither emulator nor test-key results prove physical TPM access,
real operator recovery, service login or security against same-user malware/root.

## Security review and corrected findings

Reviewed fixed subprocess arguments, stdin secret transport, static diagnostics,
selection index mapping, clipboard handoff, installed ownership/collision rules
and local scope validation. Review coverage is these implemented paths, not a
third-party dependency audit or whole-host security clearance.

The upstream pass-otp version sort used `sort -n`, misclassifying oath 2.6.14 and
selecting a seed-in-argv fallback. The dedicated extension now uses version sort,
clears inherited safe-state flags, requires safe stdin support and removes all
generation argv fallbacks. It rejects HOTP before generation/counter mutation.
The adapter rejects original upstream bytes and accepts only the hardened hash.
The upstream source and GPL license remain attributed in public test fixtures;
the native installation retains GPL and MIT licenses. Exact pins and transformations
are in [setup](2026-10-12-optional-setup.md).

Other corrected validation failures: installer tests depended on a stale/missing
wheel, so the gate now builds current source before testing; dynamic test imports
hid native setup coverage, so tests use the real package module and restore
fixture patches; two files needed formatting. Native home apply also exposed a
directory-policy mismatch: the shared application parent is 0755, while only the
dedicated optional tree needs 0700. Regression tests now accept the existing
owned non-writable shared parent without chmod and reject public optional trees
or writable ancestors. No key or TPM state was created by these repairs.

## Host and operator gates

The operator installed pass/oath-toolkit; read-only verification found versions
1.7.4-7 and 2.6.14-4.1. The physical TPM device is root:tss 0660; the current
session lacks effective access. The operator chose membership in the existing
tss group and a fresh login. Execution/new-session access remains unverified.

Remaining private commands and aggregate attestation format are in
[Phase 4–5 acceptance](2026-10-12-phase-4-5-operator-checkpoints.md). Pilot-001
remains one migrated account on operator attestation. Its dated external ledger
confirmation and the full account inventory are not yet reconciled here.

1Password approval is reused per account and terminal while its authorization
is valid. App unlock alone does not prevent the vendor's 10-minute inactivity
expiry or 12-hour hard limit. There is no keepalive, automated click or credential
cache. [Official authorization model](https://www.1password.dev/cli/app-integration-security).

## Final integration results

The final wheel above is installed. Repeat installer preview reports all four
launcher/fish targets unchanged; repeat native apply reports unchanged. Installed
doctor detects pass/GPG/oathtool/totpm, and keeps authentication/TPM readiness
unknown. The final installed controlling-PTY dashboard and fish checks pass.
Earlier rollback preview passed; no live uninstall or rollback was applied.
Software readiness does not close the private acceptance tasks listed above,
and no Authy retirement is claimed. Plans record 37 complete / 15 pending tasks.
