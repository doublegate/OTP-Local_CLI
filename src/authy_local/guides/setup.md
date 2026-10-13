# Optional backend setup preview — 2026-10-12

This supplements [the optional-backend specification](../specs/08-optional-backends.md).
The operator selected both local stores. Authy remains retained. Installing
software and passing synthetic tests do not prove real enrollment or recovery.

## Preview and footprint

Run from the checkout:

```sh
.venv/bin/python scripts/prepare_optional.py
```

This emits JSON describing proposed paths, modes, pinned sources, build arguments
and the hardware initialization command. By default it creates nothing and
inspects no keys or accounts. The same shipped entry point is available after
installation as `python -m authy_local.optional_setup` using the installed runtime
Python. Review existing target paths privately before creating them; preserve
collisions instead of overwriting them.
The main application's ownership-aware installer does not own these independent
stores or native dependencies and must not remove them during rollback/uninstall.

An explicit runtime apply installs only the exact reviewed totpm binary and
a locally hardened pass-otp extension derived from exact reviewed upstream bytes,
the exact upstream GPL license alongside that extension, and the MIT license
alongside the totpm binary. All four assets are hash-owned by the manifest.
It creates private parents and a 0600 ownership manifest at
`~/.local/state/authy-local/optional-runtime.json`. It refuses symlinks, unowned
collisions, foreign ownership, public dedicated directories and modified owned
files. A pending manifest preserves resumable ownership evidence if interrupted;
repeating a completed installation returns unchanged. It never creates GPG keys,
initializes the TPM, installs packages, edits PATH or enrolls an account.

After source/binary review, the explicit invocation is:

```sh
.venv/bin/python scripts/prepare_optional.py --apply-runtime \
    --pass-source /tmp/Authy-to-1Password_Local/pass-otp-source \
    --totpm-binary /tmp/Authy-to-1Password_Local/totpm-source/target/release/totpm
```

Runtime bytes and encrypted stores are retained on application uninstall. Native
runtime removal is deliberately manual and separately scoped so that key material
or a password-store tree cannot be deleted as application cleanup.

| Purpose | Dedicated path under the operator's home | Mode |
| --- | --- | --- |
| Optional root and native binary directory | `.local/share/authy-local/optional/{,bin}` | 0700 |
| totpm MIT license | `.local/share/authy-local/optional/bin/totpm-LICENSE` | 0600 |
| Encrypted pass entries | `.local/share/authy-local/optional/pass-store` | 0700 |
| Reviewed executable extension | `pass-store/.extensions/otp.bash` under that root | 0700 |
| Upstream extension license | `pass-store/.extensions/pass-otp-LICENSE` under that root | 0600 |
| Dedicated GPG keyring | `.local/share/authy-local/optional/gnupg` | 0700 |
| TPM configuration | `.config/authy-local/totpm.conf` | 0600 |
| TPM authorization and encrypted database | `.local/state/authy-local/totpm/{system,user}` | 0700 |

Use private 0700 directories and a 0077 umask during setup. Do not change existing
unrelated GPG homes, password stores, shell startup files or TPM permissions.

## Dependencies and reviewed pins

Read-only host inspection found GnuPG 2.4.9, tpm2-tss 4.2.0, pkgconf 3.0.7,
Rust/cargo and swtpm available. pass and oathtool were absent. The configured
package repositories offered pass 1.7.4-7, pass-otp 1.2.0-4 and oath-toolkit
2.6.14-4.1. These dated observations are not future version guarantees.

The concrete native dependency command, for a separately reviewed system package
transaction, is:

```sh
sudo pacman -S --needed pass oath-toolkit gnupg tpm2-tss pkgconf dbus sqlite
```

Do not use `pacman -Sy` alone on Arch. Review the package manager transaction and
system update requirements. The distro pass-otp package is intentionally omitted:
the adapter requires the exact hardened extension below and a compatible
oathtool version supporting secret input through stdin. The reviewed upstream
extension misorders version 2.6.14 against 2.6.5 using `sort -n`, which can put the
seed in argv. Never install the unmodified upstream file as the companion's
extension. [Upstream implementation](https://github.com/pass-extension/pass-otp/blob/7bb50dbc4b6073f12f40be66a5ee371b9652a646/otp.bash)
and [oathtool manual](https://man.archlinux.org/man/oathtool.1.en).

| Artifact | Reviewed pin | SHA-256 |
| --- | --- | --- |
| Upstream pass-otp `otp.bash`, input only | `7bb50dbc4b6073f12f40be66a5ee371b9652a646` | `8b7533e02dc37816dd8ed472a5b852ea7bdaf878ec32a233350c444ec7a33460` |
| Hardened pass-otp, installed | Exact transformations below | `4a700b3fa54ffb12c134d202b1f23fe74b4e1b4b942670fb54a766857d6c9b68` |
| Upstream pass-otp LICENSE, installed | Same reviewed source revision | `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986` |
| totpm Cargo.lock | 0.1.2 / `6789ed7f8616e4d90e8d6670f04fe815bd34462b` | `f75f384ee838304e85d1592b6060644dc32e0f9a8d7c8bb63f9b3d103d7c088b` |
| Locally staged totpm binary | Same revision, release build below | `5c166307a1441fa028bc676afadea8e364aa57248b2d6658b03c63a498b3f547` |
| totpm MIT LICENSE, installed | Same reviewed source revision | `94a10fc212f0c58a58cef3f8914cb43a20cce7c98a689016c94090bd39f5c55b` |

The binary checksum records this particular local build, not reproducible builds
across toolchains. Review the source revision and an unmodified worktree as well
as its lockfile. Lockfile verification alone does not verify all source bytes.

The setup module first verifies the upstream input hash, then requires each patch
site to match its expected occurrence count, and finally verifies the installed
hash. The adapter rejects the upstream hash and accepts only the hardened bytes.
The dedicated extension changes `sort -n` to `sort -V`, clears inherited
`OATH_SAFE`, requires oathtool's safe version branch, removes seed/URI-bearing
argv fallbacks, and rejects HOTP before generation or counter mutation. Existing
ordinary pass installations and their extensions are unaffected.

Native regression tests execute the full extension with synthetic GPG/oathtool
stubs. Versions 2.6.14 and 2.10.0 use stdin and contain no seed/URI in captured
argv; version 2.6.4 fails despite inherited `OATH_SAFE`; HOTP fails without changing
the ciphertext fixture. Adapter version acceptance remains conservative and is
separate from these patch-level version-comparison tests.

Upstream pass-otp is copyright Tad Fisher and licensed GPL-3.0-or-later. Its
unmodified public test fixture and license are retained at
`tests/fixtures/pass-otp-upstream.bash` and `tests/fixtures/pass-otp-LICENSE`.
Both fixture files are included in the source distribution through `MANIFEST.in`.
The local hardening transformations are in `authy_local.optional_setup`;
the generated extension retains upstream copyright/license notices. Preserve the
source, patch implementation and license together when redistributing it.
The exact upstream totpm MIT license is embedded in the shipped setup module and
installed alongside its binary; it is copyright 2024 Koditoriet AB.

## Native build and initialization boundary

Public sources were staged in `/tmp/Authy-to-1Password_Local/pass-otp-source`
and `/tmp/Authy-to-1Password_Local/totpm-source`. Review the pinned revisions
before building. The bounded file checks execute no source:

```sh
.venv/bin/python scripts/prepare_optional.py --verify-kind pass-otp \
    --source /tmp/Authy-to-1Password_Local/pass-otp-source
.venv/bin/python scripts/prepare_optional.py --verify-kind totpm \
    --source /tmp/Authy-to-1Password_Local/totpm-source
```

Build in the verified totpm source directory:

```sh
cargo build --release --locked --no-default-features --features install
target/release/totpm --version
target/release/totpm --help
target/release/totpm init --help
```

The build succeeded, reports version 0.1.2, includes local initialization and
omits the bulk-import command. Two upstream warnings remain: unused `command`
import and future Rust incompatibility in picky-asn1-x509. They do not represent
project lint results. [Pinned source](https://github.com/koditoriet/totpm/tree/6789ed7f8616e4d90e8d6670f04fe815bd34462b).

The preview's `init_argv` is the exact local-mode initialization invocation with
dedicated config/system/user paths. Use long options because upstream duplicates
the short `-p` flag. **Initialization creates a persistent TPM key**: it must run
privately only after checking recovery and existing configuration. Do not clear
the TPM, evict unrelated keys, change firmware, add setuid or adjust device access
to make a failed test pass. An inaccessible device leaves hardware acceptance open.

Local mode stores its unlocking material under the same user account. It provides
hardware binding, not a defense against an attacker already executing as that
user. Its seeds cannot be recovered after hardware/key loss; the independent
factor or service recovery path must survive that loss. [Upstream local-mode and
recovery model](https://github.com/koditoriet/totpm/tree/6789ed7f8616e4d90e8d6670f04fe815bd34462b#implementation-details).

## Dedicated key and private adoption checkpoints

Create the GPG encryption key interactively in the dedicated home, with a private
passphrase. Do not use the operator's ordinary keyring for tests or send key
listings, fingerprints, exports, enrollment URIs or seed input to an agent.
Privately initialize the dedicated pass store for that key, install only the
fingerprinted executable extension, and protect `.gpg-id` with mode 0600.

Before adopting real accounts, export an independently protected key backup to
an operator-selected external encrypted location and complete a synthetic restore
in a separate private keyring/store. Record only pass/fail and a location reference
in the external ledger. Do not place backups or key material in this repository.

Use the companion's explicit hidden enrollment flow one account at a time. Follow
the [migration/recovery gates](../specs/07-migration-and-recovery.md); do not automate seed
transfer from 1Password or remove Authy entries. A successful emulator or synthetic
keyring test does not close real hardware, dedicated-key backup or account login
acceptance. Report only aggregate outcomes.
