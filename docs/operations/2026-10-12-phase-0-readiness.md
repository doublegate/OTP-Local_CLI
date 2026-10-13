# Phase 0 readiness evidence — 2026-10-12

Status: Phase 0 complete. Read-only prerequisites were refreshed, and the operator
attested that all four private readiness checks passed on 2026-10-12. The agent
did not independently verify authenticated access. This evidence does not establish
live companion OTP retrieval, helper installation or account migration.

## Observation boundary

Checks ran at `2026-10-12T01:10:25-04:00` from the project tool sandbox.
Only executable versions, package metadata, CLI help, session type and the
reference checksum were inspected. No credential/configuration file, account
inventory, vault, clipboard content or authenticated CLI result was read.

| Check | Current result | Interpretation |
| --- | --- | --- |
| Python executable | 3.14.7 | Runtime available |
| 1Password CLI executable | 2.39.0 | Present; authentication unknown |
| Desktop package | 8.12.40-31 | Installed; unlock/configuration unknown |
| CLI package | 2.39.0-1 | Matches executable |
| Python package | 3.14.7-2 | Matches executable |
| fish | Executable 4.9.3; package 4.9.3-1 | Phase 2 wrapper target available |
| fzf package | 0.74.5-1.1 | Future selector dependency available |
| wl-clipboard package | 1:2.3.0-1.1 | Future copy dependency available |
| Ruff executable | 0.17.0 | Development tool available |
| Session type | Wayland | Target desktop session reported |
| Clock, sandbox | Bus access denied | Visibility limited |
| Clock, host | NTP and synchronization yes; New York | Snapshot only |
| Git, host | Standalone initial `main`; no commit/remote | Initialized |

The clock command was:

```sh
timedatectl show --property=NTP --property=NTPSynchronized --property=Timezone
```

It returned `Operation not permitted` in the sandbox. The primary agent then
repeated this narrow read-only query with host access and observed the enabled
NTP and synchronization states above. This supersedes the
[previous clock snapshot](../specs/10-research-and-host-evidence.md); recheck before live
use if the host clock or execution environment changes.

The primary agent verified the underlying Git metadata before initializing the
authorized standalone local repository on `main`, without template hooks,
staging, a commit or a remote. The sandbox still exposes an empty read-only
`.git` mount and may resolve ordinary Git commands to the parent workspace.
Use the host-level verification as evidence; an empty sandbox status is not
proof that project files are tracked.

Local `op --help`, `op item get --help` and `op whoami --help` confirm explicit
account selection, vault scoping, OTP-only retrieval, no-color, output-format
and cache controls. Help confirms syntax, not successful authentication or
response compatibility. The companion must not use `whoami` in `doctor`.

## Human desktop and CLI attestation

Perform these steps privately, outside this conversation and agent tool output.
Do not send screenshots, command results, IDs, seed material or recovery data.

1. Open the native 1Password app and verify access to the intended account.
2. Confirm Linux system authentication unlock and CLI integration in the native
   settings. The [official integration guide](https://www.1password.dev/cli/app-integration)
   describes the Linux Polkit agent requirement and these settings. Do not
   install or reconfigure authentication services as an automatic repair.
3. Use a private local terminal. Inspect authentication override **names**
   privately and remove service-account, Connect and session-token overrides
   from that terminal before testing desktop integration. Never print values.
4. In that terminal, enter the intended account selector at an interactive
   prompt, keeping its value out of command history. Run a read-only
   `op whoami --account "$account" --no-color --cache=false` with both stdout
   and stderr redirected to `/dev/null`; inspect only its exit status.
5. Witness the desktop CLI authorization prompt and approve the intended
   terminal/account. A zero exit alone does not prove the desktop path; cached
   authorization or another authentication method may avoid a new prompt.
   Do not remove accounts or change global authorization to force a prompt.
6. Record only dated pass/fail/pending attestations for desktop unlock, witnessed
   CLI approval and intended account selection. Keep the actual selector private.
7. Verify independently recoverable account access using the
   [private-ledger checklist](../templates/private-ledger-template.md). Do not reveal recovery
   contents, and do not start service enrollment changes during this check.

No OTP is needed for this attestation. Cancellation or failure remains pending;
it does not authorize retries through other authentication modes. Vendor-local
CLI activity records may retain account metadata independently of this project.

## Operator attestation and later gates

On 2026-10-12 the operator reported **all four checks passed**: desktop unlock,
scoped CLI approval, private ledger location and independent-recovery checklist.
That attestation closes the Phase 0 human tasks. Agents did not inspect the
private ledger, account identifiers, recovery material or authenticated results.
The procedural steps above remain instructions for future revalidation.

- Recheck host clock synchronization before later live use if environment changes.
- Human readiness passed by attestation; revalidate if the environment changes.
- Intended account/vault selection stays outside the project.
- Live account-selector compatibility and synthetic-item compatibility before
  real companion use; offline tests alone cannot establish them.

Report only aggregate gate status in [project status](../../PROJECT-STATUS.md).
Phase 1 offline validation is separate from the later live-companion acceptance.

## Reference preservation

The original runbook checksum remains:

```text
d4ae68a822ee2652c690aa155e071adce43561984826c0462bd5d01748e0faca
```

The original reference was not edited.
