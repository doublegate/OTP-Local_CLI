# Optional local stores

Neither option is required for the 1Password baseline. A second copy of a seed
adds recovery value only if its availability, confidentiality and maintenance are
independent enough to meet a stated need. It also adds exposure and rotation work.
Both capabilities are selected. Operator adoption and recovery evidence remain
separate gates in sprints 4.1 and 4.2. Authy remains retained.

## Common adoption gate

Define the outage being addressed, supported account subset and recovery owner.
Verify the installed release's algorithm/digits/period behavior with synthetic
fixtures and an independent standard vector. Confirm safe secret entry, sanitized
errors, permissions, backups and restore before enrolling anything real.

The companion now supports explicit `--backend pass-otp` and `--backend totpm`
for show/copy/select and explicit hidden CLI enrollment. 1Password remains default;
there is no automatic fallback or export. See [ADR 0005](adr/0005-explicit-local-backends.md)
and [setup preview](2026-10-12-optional-setup.md). The TUI only reads and guides.

## pass-otp design

Upstream [pass-otp](https://github.com/pass-extension/pass-otp) extends `pass` with
encrypted OTP records. Its documented hidden-entry flow includes `pass otp insert
NAME`, generation `pass otp NAME`, and clipboard generation `pass otp -c NAME`.
The companion uses the reviewed fixed `pass otp code` path instead of native
clipboard/URI-display commands. Verify native compatibility before adoption.

Requirements for adoption:

- A suitable GPG encryption key, protected private key and independently recoverable
  key backup; agent cache/locking behavior reviewed by the operator.
- Private password-store directory and non-sensitive entry naming policy. Do not
  enable a Git remote or synchronization by default.
- Interactive URI entry; no URI/seed in argv, environment, history or fixture files.
- Sanitized failure handling during enrollment as well as generation.
- Restore drill with synthetic data in an isolated store; later operator recovery
  verification without revealing actual seed material to agents.

The [upstream implementation](https://github.com/pass-extension/pass-otp/blob/develop/otp.bash)
can include the URI in parse diagnostics, and older oathtool paths can place a seed
in argv. Require a verified safe installed path (including oathtool ≥2.6.5) and
recheck the actual package source; version alone is not proof of wrapper safety.
The companion requires the locally hardened extension in the setup guide; the
original pinned file is rejected. Its unsafe version sort and seed-in-argv
fallbacks are corrected, and HOTP is rejected before counter mutation.
Do not use URI/QR display features in captured terminals.

Rotation must update every adopted copy before reconciliation. GPG ciphertext and
private keys have different backup requirements; copying the store alone does not
prove recovery. Do not list existing keys or records into project evidence.

## totpm design

[totpm upstream](https://github.com/koditoriet/totpm) describes TPM 2.0 storage on
x86_64 Linux, with system and local installation modes. Names/metadata in its
SQLite database are a separate confidentiality concern from protected seeds.
The host has TPM 2.0 capability. Current operator-attested physical generation
and recovery results are recorded in [project status](../PROJECT-STATUS.md).

The pinned 0.1.2 release has been reviewed for:

- Exact enrollment/generation CLI and algorithm/digits/period support.
- Local versus system authorization model, privilege needs and same-user exposure.
- Safe entry and diagnostic behavior, database permissions and update compatibility.
- Device-loss, motherboard replacement and software-upgrade recovery behavior.

Local mode is selected. System mode's dedicated user and
setuid installation require a separate security decision. Do not clear the TPM,
change firmware/PCR policy, modify boot security or install setuid binaries as an
automatic prerequisite. A database backup alone is not a portable recovery plan;
maintain an independent factor and rehearse hardware-loss recovery.

The [dated setup guide](2026-10-12-optional-setup.md) records the reviewed build,
exact initialization preview and remaining hardware/recovery acceptance. A
successful emulator test does not close those operator gates.

## Unsupported export and other stores

Re-enrollment is the normal migration route. Twilio's desktop EOL guidance does
not offer an Authy export path. Community export tools are outside this baseline:
archived/broken projects and sensitive diagnostics make historical examples poor
evidence of current compatibility. No API impersonation or diagnostic capture is
needed to complete the standard migration.

KeePassXC and other stores in the original reference are alternatives, not another
implementation branch. Add an ADR and bounded plan only if the operator chooses
one. Avoid expanding the project into several competing password managers.

## Companion command contract

Use absolute dedicated store/key-home/configuration paths. They must exist, be
owned by the current user, have no group/other access, and contain no symlink
components. Flat opaque labels contain 1–64 ASCII letters/digits/dot/underscore/
hyphen, start with a letter/digit, and never encode private service identities.
Private `.gpg-id` is required. Do not use a pass Git repository or nested entries.

```text
otp-local show --backend pass-otp --store STORE --key-home KEY_HOME --entry LABEL
otp-local copy --backend pass-otp --store STORE --key-home KEY_HOME --entry LABEL
otp-local select --backend pass-otp --store STORE --key-home KEY_HOME [--copy]
otp-local show --backend totpm --config CONFIG --service LABEL --account LABEL
otp-local copy --backend totpm --config CONFIG --service LABEL --account LABEL
otp-local select --backend totpm --config CONFIG [--copy]
otp-local enroll --backend pass-otp --store STORE --key-home KEY_HOME --entry LABEL --apply
otp-local enroll --backend totpm --config CONFIG --service LABEL --account LABEL --apply
```

Enrollment requires a controlling terminal, explicit `--apply`, repeated hidden
input and a ready backend. pass-otp accepts a validated TOTP URI and canonicalizes
its label to the opaque entry. URI algorithm/digits/period take precedence over
`--digits`/`--period` defaults. totpm takes a canonical unpadded uppercase Base32
secret; optional `--digits 6|8` and `--period SECONDS` specify its SHA-1 enrollment.
Periods are 1–86400 seconds. Unsupported inputs and existing targets fail closed.
No seed or URI belongs in command arguments or environment variables.

Generation accepts exact six/eight-digit output only. All backends share terminal,
clipboard, timeout and static error handling. Selecting a backend never generates
or synchronizes a seed. Native metadata is bounded and sanitized before selection.

## Authorization expectations

1Password requires an initial desktop approval per account/terminal session.
Authorization reuse is preserved; there is no hidden keepalive or automated click.
The [vendor](https://www.1password.dev/cli/app-integration-security) expires authorization after 10 minutes of inactivity or 12 hours total,
and revokes it when the app locks. Local stores do not contact 1Password; GPG may
require pinentry and its own cache policy. Neither local mode promises permanent
unlock or bypasses another tool's authentication policy.

## Confirmed local deletion

The [TUI](11-tui.md) supports removal of one selected local entry after typed
confirmation. GPG removal unlinks the exact private ciphertext file. TPM removal
uses an exact transaction against the pinned local database schema; native
substring-matching deletion is not used. Keys, configuration and independent
recovery copies remain intact. See [ADR 0007](adr/0007-confirmed-local-item-deletion.md).
