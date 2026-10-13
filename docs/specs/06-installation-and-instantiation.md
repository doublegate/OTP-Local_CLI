# Installation and instantiation

Status: operator procedure backed by the offline installer. This document does
not authorize host changes. See [implementation and commands](../operations/2026-10-12-installer.md).

## Readiness stages

| Stage | Required evidence | Owner |
|---|---|---|
| Host | Supported Linux/Python, Wayland, tools, synchronized clock | Read-only doctor and host checks |
| Desktop | Native app unlocked through system authentication; CLI integration enabled | Human in 1Password settings |
| Scope | Intended account/vault IDs selected without disclosing inventory | Human |
| Software | Offline gates pass; installer preview reviewed | Developer |
| Pilot | Disposable synthetic item works through UI and companion | Human |

Current observations are in [research evidence](10-research-and-host-evidence.md).
Presence of `op` is not proof of authentication. An unavailable sandbox session bus
is not proof the host clock or desktop is broken.

The upstream [desktop integration guide](https://www.1password.dev/cli/app-integration)
describes Linux system authentication and CLI integration. The operator enables
the appropriate settings through the native app and checks the Polkit agent if
authorization fails. Do not modify authentication services automatically.

## Installation footprint

| Location | Content |
|---|---|
| `~/.local/share/authy-local/releases/WHEEL_SHA256/` | Immutable installed CLI/TUI package and private runtime environment |
| `~/.local/bin/otp-local` | Launcher selecting the activated release |
| `~/.config/fish/functions/otp1p.fish` | Thin show wrapper |
| `~/.config/fish/functions/otp1pc.fish` | Thin copy wrapper |
| `~/.config/fish/functions/otp1pf.fish` | Thin selector wrapper |
| `~/.local/state/authy-local/` | Install manifest and rollback files; no vault metadata |

Use XDG equivalents where explicitly configured within the selected home;
external XDG roots are conservatively refused. The installer resolves and
display concrete targets during preview. No root access, system packages, system
Python modifications, shell startup edits or automatic PATH modification.
The generic `otp` alias is opt-in after collision checks.

Selected native assets have a separate ownership manifest and are retained by
helper uninstall/rollback. See [optional setup](../operations/2026-10-12-optional-setup.md) and
[private Phase 4–5 acceptance](../operations/2026-10-12-phase-4-5-operator-checkpoints.md).

## Installer contract

The installer defaults to dry-run. An explicit apply option is needed to
write. Preview lists source/target paths, existing conflicts and proposed hashes,
without reading unrelated user configuration or invoking authentication.

Before apply, validate source artifacts and all target parents. Refuse unexpected
symlinks/path escapes and existing files not owned by the manifest. Detect named
fish files and ask the operator to check live functions/aliases; absence of a file
does not prove absence of a function defined elsewhere.

Serialize updates with a local lock. Create state directories mode 0700 and files
with restrictive permissions; executable launchers need executable mode. Back up
every owned file being replaced, recording original bytes, mode and checksum.
Stage a complete new release, validate it, then atomically activate its launcher.
Record version, target, installed hash and rollback input in a versioned manifest.
Never store arguments, scope IDs, codes or item lists in that manifest.

An interrupted installation must leave either the previous usable release or the
new verified release active. On failure, restore only session-owned changes whose
current hashes still match the installer output. Report user modifications as
conflicts; never overwrite them during rollback.

## Upgrade and uninstall

Upgrade previews changes, runs offline gates and offers one verified previous
release for rollback. Older release directories are retained inert, rather than
automatically pruned. Interrupted staging before ownership is recorded requires
private inspection; retries refuse that unowned release directory. Recheck the
backend contract after an `op` update. Do not
silently fetch latest dependencies during activation.

Uninstall removes only manifest-owned files still matching recorded hashes.
Modified files remain, with a clear report and recovery path. Restore backed-up
files only if their destination is safe and unchanged. Never remove packages,
vault items, GPG stores, TPM state or unrelated fish functions.

## Instantiation checklist

1. Resolve the repository policy and planning ADRs in sprint 0.1.
2. Complete read-only readiness and operator desktop setup in sprint 0.2.
3. Develop and validate phases 1–2 before installing helpers.
4. Review installer preview; apply only under explicit installation authorization.
5. Open a new fish terminal and confirm wrapper resolution and exit propagation.
6. Run the human CLI/TUI synthetic-item check; record aggregate results and versions.
7. Start the separately authorized migration pilot in phase 3.

If a prerequisite fails, stop at that stage. Package installation, desktop settings,
account enrollment and migration are distinct actions, not automatic doctor repairs.
