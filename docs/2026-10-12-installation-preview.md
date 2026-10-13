# Concrete installation preview — 2026-10-12

Status: preview passed; the operator approved this exact footprint and confirmed
live names did not conflict. Applied and non-authenticating checks passed on
2026-10-12. Human disposable CLI/TUI/fish acceptance subsequently passed on operator attestation.

## Reviewed artifact and footprint

Source: `dist/authy_local-0.1.0.dev0-py3-none-any.whl`.

SHA-256: `3241b22f839dfa1be15cb25456699326a9548549929e0ea6c1744c9319cf3ee2`.

| Target under `$HOME/` | Action |
| --- | --- |
| `.local/share/authy-local/releases/3241b22f839dfa1be15cb25456699326a9548549929e0ea6c1744c9319cf3ee2/` | Create private offline runtime with reviewed wheel |
| `.local/bin/otp-local` | Create launcher, mode 0755 |
| `.config/fish/functions/otp1p.fish` | Create show wrapper, mode 0600 |
| `.config/fish/functions/otp1pc.fish` | Create copy wrapper, mode 0600 |
| `.config/fish/functions/otp1pf.fish` | Create selector wrapper, mode 0600 |
| `.local/state/authy-local/` | Create private ownership, prepared-release and recovery state, mode 0700 |

No collisions were reported. No collision backups or generic `otp` alias are
selected. No PATH/startup-file edits, system package changes, network dependency
installation, authentication or account operations are included.

The operator must check existing live functions/aliases privately; absence of
named files is not proof that another startup source defines these functions.
An approval must include confirmation that these names do not conflict.

## Apply and verification gate

Recheck the wheel digest and rerun the same preview before apply. Any artifact,
target or conflict change requires renewed review. The exact prepared command is:

```bash
.venv/bin/python scripts/install.py install --wheel dist/authy_local-0.1.0.dev0-py3-none-any.whl --apply
```

After authorized apply, manifest ownership, installed help/version and
preview-only repeat installation passed without invoking a backend. The human next
opens a new fish terminal and performs the private CLI/TUI disposable acceptance
in [operator checkpoints](2026-10-12-phase-3-operator-checkpoints.md).

Rollback/uninstall remain preview-first as described in the
[installer guide](2026-10-12-installer.md). Inert releases are retained; no recursive
cleanup or account retirement is part of this installation.

## Checkpoint A encoding repair

The operator's private diagnostic established that CLI 2.39.0 rejects explicit
`--encoding UTF-8`. Retrieval and selection now omit that option and use the
vendor default. Synthetic backend fixtures reject the unsupported flag;
all 114 tests, lint, documentation checks, build and isolated wheel smoke pass.

The corrected wheel SHA-256 is
`d33c71c5b570501fc7f5ec801cb322fe2fbb651644db9c2362279791a88bcacd`.
Its preview uses the same four owned targets and a new digest-named runtime under
the existing releases directory. Applied as a repair to the existing installation;
the previous runtime is retained for rollback. No account operations were run.
Checkpoint A subsequently passed on operator attestation; pilot and batches remain pending.

## Terminal authorization reuse repair

The operator requested a repair for repeated desktop approval prompts. All three
1Password call sites now retain the terminal session and controlling terminal,
while using a separate owned process group for deadline and cancellation cleanup.
The selector and clipboard retain their established process policies.

The wheel SHA-256 is
`511458e5f82fa17d816b9076cc56490537fdbfd8f25ccef3cc3703213a94a7e2`.
Preview confirmed the same four owned targets, unchanged wrapper contents and a
new digest-named runtime. The full gate passes: 117 tests, 96% coverage, lint,
documentation, build and isolated package smoke. The operator subsequently confirmed
two successful TUI Show requests in the same terminal with no second GUI prompt.
Approval reuse passed this private check; lock and expiry controls remain enabled
and were not separately retested.
Applied under the operator's repair request; installed help/version and repeat
preview passed without backend access. The previous runtime remains for rollback.

After installation, privately run scoped show twice in the same terminal within
ten minutes, approving the first request if needed. Compare codes privately and
report only exit statuses and whether the second request prompted. Repeat through
TUI Show using the same scope. A locked app, expired authorization or changed
account may require a fresh approval under the
[official authorization model](https://www.1password.dev/cli/app-integration-security).
