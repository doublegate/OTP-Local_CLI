# Offline installer implementation — 2026-10-12

The separate installer is available through the prepared project environment:

```bash
.venv/bin/python scripts/install.py install --wheel dist/authy_local-1.0.0rc1-py3-none-any.whl
.venv/bin/python scripts/install.py rollback
.venv/bin/python scripts/install.py uninstall
```

These commands preview without creating directories, locks or state. Add `--apply`
only after reviewing the concrete paths. An incomplete journal causes preview to
refuse; an applied operation first restores the previous owned file state.

The installed package also exposes `RELEASE/bin/python -I -B -m
authy_local.installer` with the same arguments. Use the concrete installed release
path for `RELEASE`. `-B` prevents new bytecode caches from changing the immutable
release tree. Installation previews include the local wheel path and SHA256.

## Footprint and ownership

`--home` selects the target home. Default targets are `.local/bin/otp-local`,
`.config/fish/functions/otp1p.fish`, `otp1pc.fish`, `otp1pf.fish`,
`.local/share/authy-local/releases/WHEEL_SHA256/` and
`.local/state/authy-local/` beneath that home. Explicit absolute XDG configuration,
data and state roots are supported only within the selected home; external roots
are refused. No shell startup or PATH modifications occur.

The generic `otp.fish` wrapper is installed only with `--generic-alias`. Changing
that choice requires uninstall and a new installation. A named function file
check cannot establish whether other live aliases/functions exist; the operator
must check those privately in a fresh terminal.

The manifest records schema version, wheel digest, release file hashes and each
owned target's bytes, mode and digest. Original bytes for approved collisions are
stored only in the private state directory. No scope or authentication data is
requested. State is mode 0700 and owned by the current user; state files are 0600.
The launcher is 0755 and fish function files are 0600.

Unexpected symlinks, escaped paths, nonregular targets, malformed ownership state,
release changes and modified owned targets are refused. An unowned regular-file
collision requires `--backup /absolute/exact/target`, repeated for every selected
target. Backup choices do not authorize overwriting modified owned files.

## Activation, rollback and recovery

The installer creates a dedicated Python environment from a bounded local wheel,
installs with `--no-index --no-deps --no-compile`, and smoke-tests package help
without invoking a backend. It does not fetch dependencies or modify system Python.
A prepared-release manifest allows retry after a complete staged release failed
to activate. A matching wheel reinstallation is a verified no-op.

A nonblocking advisory file lock serializes installer operations. Before target
writes, a durable journal stores original and intended snapshots. Fish files land
before the launcher, which is activated by atomic rename. The manifest and journal
are updated using flushed writes and directory synchronization. Recovery restores
only files matching the journal's before/after snapshots. Any concurrent edit
blocks recovery rather than being overwritten.

Rollback verifies the previous release and all current targets before exchanging
the active and previous manifests. Uninstall restores approved collision backups
or removes unchanged owned files. Modified files remain with ownership evidence
for private resolution and a clear preserved-file result. Complete that partial
uninstall before reinstalling; repairing a preserved file does not make the
already-removed targets installed again.

Completed releases are retained as inert rollback inputs. Only one previous
release is offered by `rollback`; older directories are not automatically deleted.
An interrupted environment build before its prepared-release manifest exists
leaves an unowned directory and is refused on retry. Preserve it for inspection;
the installer does not recursively delete unproven content. This is a conservative
recovery limitation, distinct from activation-journal recovery.

This installer protects against mistaken paths, stale ownership and ordinary
interruptions. A malicious process running as the same OS user can tamper with
state or race filesystem operations; the manifest is not a cryptographic trust
boundary against that principal. It does not establish live fish resolution,
desktop integration, synthetic-item compatibility or successful account migration.
