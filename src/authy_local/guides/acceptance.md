# Phase 4–5 private operator acceptance — 2026-10-12

Software validation uses public synthetic credentials only. These remaining
checks need your private key choices, recovery media and account access; agents
must not perform them or receive their output. Authy remains retained. Keep
service identities, fingerprints, seeds, backups and codes outside this repo.
Use a private fish terminal. Report only the aggregate template at the end.

## A. Native prerequisites and dedicated GPG setup

Review your normal Arch update policy and the package transaction first:

```fish
sudo pacman -S --needed pass oath-toolkit
otp-local doctor
umask 077
set optional_root "$HOME/.local/share/authy-local/optional"
set otp_store "$optional_root/pass-store"
set otp_keys "$optional_root/gnupg"
mkdir -p "$otp_keys"
chmod 700 "$otp_keys"
env GNUPGHOME="$otp_keys" gpg --full-generate-key
```

The reviewed native runtime must already be installed following
[setup](2026-10-12-optional-setup.md). Use a new encryption-capable key protected
by a passphrase. Select its fingerprint privately, without listing your normal
keyring. The following variables remain only in your private terminal:

```fish
read --silent --prompt-str 'Dedicated encryption key fingerprint: ' otp_key
env GNUPGHOME="$otp_keys" PASSWORD_STORE_DIR="$otp_store" pass init "$otp_key"
chmod 600 "$otp_store/.gpg-id"
otp-local enroll --backend pass-otp --store "$otp_store" \
    --key-home "$otp_keys" --entry acceptance-001 --apply
```

For this disposable enrollment only, enter the public RFC test value twice at
the hidden prompt:
`otpauth://totp/acceptance-001?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ`.
It is intentionally public and must never protect an actual account.

```fish
otp-local show --backend pass-otp --store "$otp_store" \
    --key-home "$otp_keys" --entry acceptance-001
printf 'generation exit=%s\n' $status
```

Verify the disposable result locally with an independent TOTP implementation.
Do not report the code. Refusal of an existing enrollment is expected; use a
new opaque disposable label instead of overwriting a record.

## B. GPG backup and restore

Privately choose an external encrypted backup directory with an independently
usable unlocking method. Do not choose the repo, its scratch folder, or a medium
whose only recovery depends on this key. Review the backup directory permissions.

```fish
read --prompt-str 'External encrypted backup directory: ' otp_backup
env GNUPGHOME="$otp_keys" gpg --armor \
    --output "$otp_backup/authy-local-secret-key.asc" --export-secret-keys "$otp_key"
env GNUPGHOME="$otp_keys" gpg --export-ownertrust > "$otp_backup/authy-local-ownertrust.txt"
cp -a "$otp_store" "$otp_backup/authy-local-pass-store"
set otp_restore (mktemp -d "$HOME/.local/state/authy-local/restore-check.XXXXXX")
mkdir -m 700 "$otp_restore/keys"
cp -a "$otp_backup/authy-local-pass-store" "$otp_restore/store"
env GNUPGHOME="$otp_restore/keys" gpg --import "$otp_backup/authy-local-secret-key.asc"
env GNUPGHOME="$otp_restore/keys" gpg --import-ownertrust "$otp_backup/authy-local-ownertrust.txt"
otp-local show --backend pass-otp --store "$otp_restore/store" \
    --key-home "$otp_restore/keys" --entry acceptance-001
printf 'restore exit=%s\n' $status
```

These commands refuse pre-existing GPG output files; preserve earlier backups.
Compare independent generation in the same TOTP window. Record the restore date
and backup reference in the private ledger. Review and deliberately dispose of
the disposable restored keyring later; no automatic broad deletion is provided.
This drill proves the synthetic restore path, not every future real account.

## C. Physical TPM acceptance

Check effective device access without changing permissions:

```fish
test -r /dev/tpmrm0; and test -w /dev/tpmrm0
printf 'TPM device access exit=%s\n' $status
```

Stop if this fails. Do not clear the TPM, evict unrelated keys or grant broad
device permissions. If the config already exists, preserve it and review it
privately instead of initializing again. With independent recovery ready, the
selected local-mode initialization creates a persistent TPM key:

The host check found root:tss ownership and mode 0660. You selected membership
in the existing tss group. Run the following admin change yourself, then log out
and back in before repeating the access check. Selection of this option is not
evidence that the command or fresh login has completed:

```fish
sudo usermod -aG tss $USER
```

```fish
set otp_tpm_config "$HOME/.config/authy-local/totpm.conf"
set otp_tpm_state "$HOME/.local/state/authy-local/totpm"
mkdir -p "$HOME/.config/authy-local" "$otp_tpm_state/system" "$otp_tpm_state/user"
chmod 700 "$HOME/.config/authy-local" "$otp_tpm_state" \
    "$otp_tpm_state/system" "$otp_tpm_state/user"
"$optional_root/bin/totpm" --config "$otp_tpm_config" init --local \
    --tpm device:/dev/tpmrm0 --system-data-path "$otp_tpm_state/system" \
    --user-data-path "$otp_tpm_state/user" --presence-verification none
chmod 600 "$otp_tpm_config"
otp-local enroll --backend totpm --config "$otp_tpm_config" \
    --service acceptance-001 --account acceptance-001 --apply
otp-local show --backend totpm --config "$otp_tpm_config" \
    --service acceptance-001 --account acceptance-001
printf 'TPM generation exit=%s\n' $status
```

Enter the public RFC Base32 test value from A at the hidden prompts. Compare the
result privately with an independent TOTP implementation. Local mode uses no
fingerprint prompt and does not isolate secrets from malware acting as you.
Rehearse loss of workstation access using your separate recovery device/factor;
do not destroy the TPM key to simulate it. TPM database backup is not seed recovery.

## D. Selected real adoption, recovery and closure

Only after A–C pass, choose the small real-account subset privately. Enroll
through official service instructions, use hidden companion input, verify fresh
login and all required devices, and test independent recovery. Never export from
Authy/1Password through an agent. Retaining an old Authy entry does not prove it
still works after seed rotation. Record outcomes in the external ledger.

Complete [Phase 3 batches](2026-10-12-phase-3-operator-checkpoints.md), date the
pilot ledger record and reconcile the full inventory. Review disk/swap protection,
lock screen, terminal recording, core dumps, clipboard history, backup ownership
and temporary artifacts. Rehearse unavailable workstation, locked 1Password,
lost mobile access and optional-store failure without disrupting working access.
The [completion matrix](../specs/09-operations-and-completion.md) controls final acceptance.
The delivered 1.0.0rc1 is a candidate until these operator gates pass. Retaining
Authy is the selected disposition; retirement is not authorized by this checklist.

```text
Pilot ledger dated: pass/pending
Full inventory reconciled: pass/pending
Native packages installed: pass/pending
Dedicated GPG key and independent backup: pass/pending
Synthetic GPG restore: pass/pending
Physical TPM local-mode synthetic check: pass/pending/blocked
Independent machine-loss recovery: pass/pending
Selected real optional enrollments and fresh login: pass/pending
Recovery scenarios and host privacy review: pass/pending
Temporary-artifact and backup review: pass/pending
Authy: retained
Unresolved blocker categories: none/or non-identifying categories
```

No accounts, keys, codes or detailed native output should accompany the report.
