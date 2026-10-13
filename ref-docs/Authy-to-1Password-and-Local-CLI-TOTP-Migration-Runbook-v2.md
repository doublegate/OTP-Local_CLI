# Authy → 1Password + Local Desktop / CLI TOTP Migration Runbook

**Target environment:** CachyOS / Arch Linux, fish shell, TPM 2.0-capable workstation  
**Goal:** Replace dependence on the retired Authy Desktop application while making every ordinary TOTP account available through **1Password** and through a **terminal command-line workflow**.  
**Preferred end state:** 1Password as the user-facing cross-platform authenticator, with either **1Password CLI (`op`)**, `pass-otp`, or TPM-backed `totpm` providing terminal access. Optionally use a fish/fzf helper such as `otp github`.

**Revision:** v2 — adds 1Password desktop/mobile/browser TOTP and 1Password CLI as a first-class migration and terminal-access path.

> **Security note**
>
> TOTP seeds are long-lived secrets. Anyone who obtains a seed can generate valid MFA codes. Treat exported `otpauth://` URIs, QR codes, JSON exports, screenshots, shell history, clipboard contents, backups, and temporary files containing seeds as highly sensitive.

---

## 1. Executive summary

Twilio ended support for Authy Desktop on **March 19, 2024** for Windows, macOS, and Linux. Existing installations were intended to be invalidated and removed as registered Authy devices. Twilio currently recommends mobile Authy or migration to another authenticator.

Authy does **not** provide an official token export/import mechanism. Twilio's supported migration procedure is:

1. Sign into each protected service.
2. Disable its existing authenticator-based 2FA.
3. Re-enable authenticator-based 2FA.
4. Enroll the new authenticator using the newly issued QR code or secret.
5. Verify the new authenticator before removing the old Authy entry.

For a Linux workstation, the most practical targets are:

- **1Password + 1Password CLI** — one TOTP seed can serve the desktop/mobile/browser experience *and* terminal usage with `op item get <item> --otp`.
- **`pass` + `pass-otp`** — mature, portable, GPG-encrypted, fully local, and scriptable.
- **`totpm`** — TPM 2.0-backed TOTP client with stronger machine binding, but less mature and deliberately non-exportable.
- **KeePassXC / KeePassXC CLI** — useful if you already want a portable encrypted database with OTP support.

The recommended migration strategy is:

```text
Authy mobile
   │
   │  per-service re-enrollment (supported)
   ▼
fresh otpauth:// URI / QR code
   │
   ├──► pass-otp        ← recommended default
   │
   └──► totpm           ← strong machine-bound option
```

Use reverse-engineered Authy export only as a contingency/migration aid.

---

# 2. Current Authy desktop status

Twilio's Authy Desktop applications for:

- Windows
- macOS
- Linux

reached end-of-life on **March 19, 2024**.

Twilio states that the retired desktop installations are no longer supported and that desktop devices may be invalidated/removed from the Authy account.

There is no supported:

- Authy Linux desktop application
- Authy Windows/macOS desktop application
- Authy web vault
- Authy command-line client
- official token export workflow

## Official references

- Twilio Authy Desktop EOL:
  https://www.twilio.com/en-us/changelog/end-of-life--eol--of-twilio-authy-desktop-apps
- Twilio Authy Desktop end-user guide:
  https://help.twilio.com/articles/22771146070299-End-user-guide-End-of-Life-EOL-for-Twilio-Authy-Desktop-app
- Twilio token export/import policy:
  https://help.twilio.com/articles/19753420684059-Export-or-Import-Tokens-in-the-Authy-app

---

# 3. Recommended architecture

The preferred design is to make **1Password the primary cross-device authenticator** while retaining a terminal-access path.

There are two good operating models.

## Model A — one authoritative TOTP copy in 1Password

```text
                    ┌─────────────────┐
                    │   Authy Mobile  │
                    │  temporary use  │
                    └────────┬────────┘
                             │
                    service re-enrollment
                             │
                  ┌──────────▼──────────┐
                  │   fresh TOTP seed   │
                  │ QR / otpauth:// URI │
                  └──────────┬──────────┘
                             │
                             ▼
                   ┌───────────────────┐
                   │     1Password     │
                   │ one-time password │
                   └─────────┬─────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
     Desktop / browser / mobile       1Password CLI
       autofill / copy OTP        op item get ITEM --otp
```

This is the **cleanest default** because there is only one authoritative copy of the TOTP seed.

It provides:

- 1Password desktop access
- browser autofill
- mobile access
- automatic one-time-password filling
- terminal retrieval through 1Password CLI
- no second TOTP database to synchronize or back up

Example:

```fish
op item get GitHub --otp
```

If the Login item named `GitHub` contains a One-Time Password field, the command outputs the currently valid TOTP code.

---

## Model B — 1Password + independent local CLI copy

For services where you intentionally want an additional local implementation:

```text
                         fresh TOTP seed
                               │
               ┌───────────────┼────────────────┐
               │               │                │
               ▼               ▼                ▼
          1Password        pass-otp           totpm
         cross-device     GPG-encrypted     TPM-backed
               │               │                │
               ▼               ▼                ▼
           GUI/mobile       local CLI         local CLI
```

During the service's MFA enrollment, capture the **same QR code / `otpauth://` seed** into 1Password and the selected local CLI store **before finishing enrollment**.

Because all clients possess the same TOTP seed, they should generate the same rolling code at the same time.

### Important security implication

This is redundancy, **not additional MFA factor strength**.

Duplicating a TOTP seed means there are more locations from which that same second factor could be compromised.

Use Model B only where the resilience benefit is worth the additional secret copy.

---

## Recommended hierarchy

### Default for ordinary services

```text
1Password TOTP
    +
1Password CLI (`op`)
```

This gives both graphical/mobile and command-line access without duplicating the seed.

### Services where an independent local fallback is desirable

```text
1Password TOTP
    +
pass-otp
```

### Services intentionally bound to the workstation

```text
1Password TOTP
    +
totpm
```

### Highest-value accounts

Prefer:

```text
FIDO2/WebAuthn hardware key
    +
second hardware key
    +
offline recovery codes
```

Use TOTP only as a fallback when appropriate.

---

# 4. Migration safety checklist

Before changing any account:

- [ ] Confirm you can sign into the service.
- [ ] Confirm Authy currently generates a valid code for that service.
- [ ] Obtain and securely store the service's recovery codes.
- [ ] Verify your recovery email and phone number.
- [ ] Make sure you know the account password.
- [ ] Ensure system time synchronization works.
- [ ] Do **not** delete the Authy token yet.
- [ ] Do **not** disable Authy backups yet.
- [ ] Migrate one service at a time.
- [ ] Test the new authenticator with a fresh login.
- [ ] Only then remove the old Authy entry.

For high-value accounts such as:

- primary email,
- domain registrar,
- password manager,
- cloud provider,
- GitHub,
- VPN,
- financial accounts,

perform migration conservatively and retain recovery codes offline.

---

# 5. Verify system clock first

TOTP depends on accurate time.

On CachyOS:

```fish
timedatectl status
```

You want to see:

```text
System clock synchronized: yes
NTP service: active
```

If necessary:

```fish
sudo timedatectl set-ntp true
```

Check again:

```fish
timedatectl status
```

A clock drift of roughly 30 seconds can invalidate many TOTP codes.

---

# 6. Option A — 1Password + 1Password CLI (recommended primary path)

1Password can store standard TOTP enrollment secrets and continuously generate rolling one-time passwords.

Official 1Password documentation supports:

- QR-code scanning
- manual TOTP secret entry
- desktop, browser, Linux, Android, iOS, Windows, and macOS access
- automatic OTP filling in supported browser flows
- terminal OTP generation through 1Password CLI

Official references:

- https://support.1password.com/one-time-passwords/
- https://support.1password.com/explore/linux/
- https://www.1password.dev/cli/reference/management-commands/item

---

## 6.1 Add an existing or newly re-enrolled service to 1Password

For each service:

1. Open the service's MFA / two-factor-authentication settings.
2. If migrating from Authy, authenticate using the existing Authy token.
3. Save current recovery codes.
4. Disable the old TOTP enrollment if the service requires this.
5. Enable authenticator-app / TOTP MFA again.
6. Stop when the service displays its new QR code or manual secret.
7. Open the corresponding Login item in 1Password.
8. Edit the Login item.
9. Select **Add More → One-Time Password**.
10. Scan the QR code or paste the enrollment secret.
11. Save the item.
12. Copy the current rolling code from 1Password.
13. Enter it into the service to confirm enrollment.
14. Complete a fresh-login test.
15. Only after verification, retire the corresponding Authy token.

On supported 1Password browser-extension flows, **Scan QR Code** can capture the QR code directly from the page.

---

## 6.2 Verify the 1Password TOTP

Open the Login item.

You should see a rolling code similar to:

```text
123456
```

The code normally changes every 30 seconds, although services can specify different TOTP parameters.

During service enrollment, use the 1Password-generated code to confirm that the stored seed is correct.

---

## 6.3 Install 1Password CLI

1Password CLI uses the executable:

```text
op
```

After installation, verify:

```fish
op --version
```

The official Linux installation documentation should be treated as authoritative for current package/repository instructions:

https://developer.1password.com/docs/cli/get-started/

If the desktop application is installed, prefer enabling 1Password CLI integration with the desktop app so terminal authorization follows the normal 1Password unlock/approval workflow rather than creating ad-hoc long-lived credentials.

---

## 6.4 Generate a TOTP code from the terminal

For a Login item named `GitHub`:

```fish
op item get GitHub --otp
```

Example output:

```text
123456
```

For an item in a specific vault:

```fish
op item get GitHub --vault Personal --otp
```

Using an item ID is safer in scripts because item titles can change or collide:

```fish
op item get abcdefghijklmnopqrstuvwxyz --otp
```

The `--otp` option returns the **currently generated one-time password**, not the raw TOTP seed.

---

## 6.5 1Password as both desktop and terminal authenticator

This is the simplest way to meet the goal of having both interfaces available:

```text
                   one TOTP seed
                        │
                        ▼
                   1Password
                     item
                        │
          ┌─────────────┴─────────────┐
          │                           │
          ▼                           ▼
     1Password UI                 terminal
   desktop/mobile/web       op item get ITEM --otp
```

No duplicate `pass-otp` database is required.

---

## 6.6 Fish helper for 1Password

Create:

```text
~/.config/fish/functions/otp1p.fish
```

with:

```fish
function otp1p --description "Generate a TOTP code from 1Password"
    if not type -q op
        echo "1Password CLI (op) is not installed" >&2
        return 127
    end

    if test (count $argv) -eq 0
        echo "Usage: otp1p ITEM [VAULT]" >&2
        return 2
    end

    set -l item "$argv[1]"

    if test (count $argv) -ge 2
        op item get "$item" --vault "$argv[2]" --otp
    else
        op item get "$item" --otp
    end
end
```

Examples:

```fish
otp1p GitHub
otp1p GitHub Personal
```

---

## 6.7 Copy the 1Password OTP directly to the Wayland clipboard

```fish
op item get GitHub --otp | string trim | wl-copy
```

A helper:

```fish
function otp1pc --description "Copy a 1Password OTP to Wayland clipboard"
    if test (count $argv) -eq 0
        echo "Usage: otp1pc ITEM" >&2
        return 2
    end

    op item get "$argv[1]" --otp | string trim | wl-copy
end
```

Usage:

```fish
otp1pc GitHub
```

Remember that KDE clipboard history may retain the code unless configured otherwise.

The OTP itself is short-lived, but minimizing clipboard retention remains good hygiene.

---

## 6.8 Interactive 1Password OTP selector with `fzf`

A convenient implementation is:

```fish
function otp1pf --description "Select a 1Password Login and emit its OTP"
    if not type -q op
        echo "1Password CLI (op) is not installed" >&2
        return 127
    end

    if not type -q fzf
        echo "fzf is not installed" >&2
        return 127
    end

    set -l selected (
        op item list --categories Login --format=json \
        | jq -r '.[] | [.id, .title] | @tsv' \
        | fzf \
        | cut -f1
    )

    test -n "$selected"; or return 1

    op item get "$selected" --otp
end
```

Install `jq` and `fzf` if required:

```fish
sudo pacman -S jq fzf
```

Usage:

```fish
otp1pf
```

Not every Login item contains a TOTP field. If an item without one is selected, 1Password CLI will report that no primary one-time password is available.

---

## 6.9 Unified `otp` command backed by 1Password

If 1Password is your preferred source of truth:

```fish
function otp --description "Generate an OTP from 1Password"
    if test (count $argv) -eq 0
        echo "Usage: otp ITEM" >&2
        return 2
    end

    op item get "$argv[1]" --otp
end
```

Then:

```fish
otp GitHub
otp Cloudflare
otp Synology
```

This provides the exact terminal UX originally sought without maintaining a separate TOTP store.

---

## 6.10 New-account enrollment: save the same seed to 1Password and `pass-otp`

If you deliberately want both 1Password and a fully local independent CLI implementation:

1. Begin TOTP enrollment on the service.
2. Leave the enrollment QR code displayed.
3. Scan the QR code into 1Password.
4. Import the **same** QR/URI into `pass-otp`.
5. Confirm that both produce the same code.
6. Submit that code to the service.
7. Save recovery codes.
8. Complete a fresh-login test.

Do **not** finish enrollment before the second client has captured the seed unless the service lets you display it again.

This pattern applies equally to:

```text
1Password + pass-otp
```

or:

```text
1Password + totpm
```

provided the second tool accepts the same enrollment material.

---

## 6.11 Existing Authy services: migration pattern

For each ordinary TOTP account currently in Authy:

```text
Existing Authy token
       │
       ▼
service security settings
       │
disable/re-enroll TOTP
       │
       ▼
new QR / secret
       │
       ├──► 1Password
       │
       ├──► optional pass-otp
       │
       └──► optional totpm
       │
       ▼
verify code
       │
       ▼
fresh login
       │
       ▼
retire old Authy token
```

This avoids depending on unsupported Authy extraction.

---

## 6.12 New services from this point forward

For every new service:

### Preferred default

```text
service TOTP QR
      │
      ▼
  1Password
      │
      ├── GUI/mobile/browser
      └── 1Password CLI
```

### If local redundancy is required

Capture the same seed at enrollment into:

```text
1Password
    +
pass-otp or totpm
```

Then verify that both clients produce the same rolling code before finishing enrollment.

---

## 6.13 Security trade-off: password + TOTP in the same 1Password item

Storing:

```text
username
password
TOTP seed
```

in the same 1Password vault is extremely convenient.

However, it means successful compromise of the unlocked vault could expose both the password and the TOTP generator.

That is weaker factor separation than:

```text
password in 1Password
+
TOTP on independent hardware/device
```

or, preferably:

```text
password in 1Password
+
FIDO2/WebAuthn security key
```

For ordinary consumer services, the convenience may be acceptable.

For privileged infrastructure, primary identity, or high-impact administrative accounts, prefer phishing-resistant hardware-backed authentication where available.

---

# 7. Option B — `pass` + `pass-otp` (independent local CLI)



## 7.1 Install packages

On CachyOS / Arch:

```fish
sudo pacman -S pass pass-otp gnupg fzf wl-clipboard qrencode zbar
```

Useful roles:

| Package | Purpose |
|---|---|
| `pass` | Unix password store |
| `pass-otp` | TOTP extension |
| `gnupg` | encrypts password-store entries |
| `fzf` | interactive token selector |
| `wl-clipboard` | Wayland clipboard support |
| `qrencode` | render QR codes |
| `zbar` | decode QR codes |

---

## 7.2 Create or select a GPG key

List existing secret keys:

```fish
gpg --list-secret-keys --keyid-format=long
```

Example:

```text
sec   ed25519/0123456789ABCDEF 2026-10-09 [SC]
```

If you already have an appropriate personal encryption-capable key, use it.

If not, create one:

```fish
gpg --full-generate-key
```

Then list keys again:

```fish
gpg --list-secret-keys --keyid-format=long
```

Copy the appropriate key ID.

---

## 7.3 Initialize `pass`

Example:

```fish
pass init 0123456789ABCDEF
```

Verify:

```fish
pass ls
```

Default store:

```text
~/.password-store/
```

The entries inside are GPG encrypted.

---

## 7.4 Add a test TOTP token

`pass-otp` accepts standard Key URI Format:

```text
otpauth://totp/ISSUER:ACCOUNT?secret=BASE32SECRET&issuer=ISSUER
```

Insert manually:

```fish
pass otp insert 2fa/test
```

Paste the URI at the prompt.

Generate the code:

```fish
pass otp 2fa/test
```

Copy it to the clipboard:

```fish
pass otp -c 2fa/test
```

`pass-otp` clears copied OTPs after a short timeout.

---

# 8. Best supported migration method: re-enroll every service

This is the method Twilio recommends.

For each service:

1. Sign in using the existing Authy code.
2. Navigate to the service's security/MFA settings.
3. Obtain recovery codes if you have not already.
4. Disable the existing authenticator/TOTP method.
5. Immediately enable authenticator/TOTP again.
6. The service will display either:
   - a QR code, or
   - a Base32 secret/key.
7. Add the new token to `pass-otp`.
8. Enter a generated code into the service.
9. Save the service configuration.
10. Sign out and perform a fresh login using the new token.
11. Keep Authy intact until the login test succeeds.

---

# 9. Import directly from a displayed QR code

## Method 1 — decode a saved QR image

If you save the QR image to a temporary file:

```fish
zbarimg -q --raw ./qrcode.png
```

Expected output:

```text
otpauth://totp/GitHub:user@example.com?secret=...
```

Import directly:

```fish
zbarimg -q --raw ./qrcode.png | pass otp insert 2fa/github
```

Immediately securely delete the QR image if it contains only the enrollment code.

On SSDs, filesystem-level secure deletion is not guaranteed due to wear leveling. Prefer avoiding persistent storage entirely when possible.

---

## Method 2 — Wayland clipboard

If the QR image is copied to the clipboard:

```fish
wl-paste | zbarimg -q --raw - | pass otp insert 2fa/github
```

This avoids manually exposing the seed as text.

---

## Method 3 — manually enter the URI

If the service displays the secret:

```fish
pass otp insert 2fa/github
```

Then provide the full `otpauth://` URI.

If the site only gives a raw Base32 key, construct:

```text
otpauth://totp/GitHub:user@example.com?secret=BASE32SECRET&issuer=GitHub
```

Be careful with:

- issuer
- account name
- number of digits
- period
- algorithm

Most services use:

```text
digits=6
period=30
algorithm=SHA1
```

but do **not** assume this for every service.

---

# 10. Verify an imported token

Generate:

```fish
pass otp 2fa/github
```

Compare against:

- the service during enrollment, and
- Authy temporarily if the old and new enrollment intentionally use the same seed.

For a normal migration involving re-enrollment, Authy may show a **different** code because the site issued a **new seed**. That is expected.

Perform a fresh login with the new token before considering the migration complete.

---

# 11. Fish-shell helper for `pass-otp`

Create:

```text
~/.config/fish/functions/otp.fish
```

with:

```fish
function otp --description "Select and copy a TOTP code from pass"
    set -l root "2fa"

    if not type -q pass
        echo "pass is not installed" >&2
        return 127
    end

    if not type -q fzf
        echo "fzf is not installed" >&2
        return 127
    end

    set -l entries (
        find "$HOME/.password-store/$root" \
            -type f \
            -name '*.gpg' \
            2>/dev/null \
        | sed "s|^$HOME/.password-store/||" \
        | sed 's|\.gpg$||' \
        | sort
    )

    if test (count $entries) -eq 0
        echo "No OTP entries found under $root/" >&2
        return 1
    end

    set -l selected (printf '%s\n' $entries | fzf --prompt='OTP> ')

    if test -z "$selected"
        return 1
    end

    pass otp -c "$selected"
end
```

Usage:

```fish
otp
```

Select:

```text
2fa/github
2fa/google
2fa/cloudflare
2fa/synology
```

The OTP is copied to the clipboard.

---

# 12. Direct `otp SERVICE` helper for `pass-otp`

If you want:

```fish
otp github
```

to work directly, use this version:

```fish
function otp --description "Generate/copy TOTP from pass"
    set -l root "2fa"

    if test (count $argv) -gt 0
        set -l query "$root/$argv[1]"

        if test -f "$HOME/.password-store/$query.gpg"
            pass otp -c "$query"
            return $status
        end

        set -l match (
            find "$HOME/.password-store/$root" \
                -type f \
                -name '*.gpg' \
                2>/dev/null \
            | sed "s|^$HOME/.password-store/||" \
            | sed 's|\.gpg$||' \
            | string match -ri ".*$argv[1].*" \
            | head -n 1
        )

        if test -n "$match"
            pass otp -c "$match"
            return $status
        end

        echo "No matching OTP token found." >&2
        return 1
    end

    set -l selected (
        find "$HOME/.password-store/$root" \
            -type f \
            -name '*.gpg' \
            2>/dev/null \
        | sed "s|^$HOME/.password-store/||" \
        | sed 's|\.gpg$||' \
        | sort \
        | fzf --prompt='OTP> '
    )

    test -n "$selected"; or return 1
    pass otp -c "$selected"
end
```

Examples:

```fish
otp github
otp cloudflare
otp
```

---

# 13. Avoid leaking TOTP secrets into shell history

Never do this:

```fish
echo 'otpauth://totp/...secret=SUPERSECRET...' > token.txt
```

or:

```fish
pass otp insert 2fa/github <<< 'otpauth://...'
```

because shell history, process inspection, terminal logging, clipboard history, or temporary files may expose the seed.

Prefer:

```fish
pass otp insert 2fa/github
```

and paste interactively.

For QR decoding, prefer a pipe:

```fish
wl-paste | zbarimg -q --raw - | pass otp insert 2fa/github
```

---

# 14. Disable clipboard-history capture for MFA material

KDE Plasma's clipboard manager can preserve clipboard history.

When copying OTPs or secrets:

- avoid copying raw seeds whenever possible,
- configure Klipper appropriately,
- clear history after migration,
- do not sync clipboard history to cloud services.

A TOTP **code** is short-lived.  
A TOTP **seed** is effectively permanent until the service rotates it.

---

# 15. Backup strategy for `pass`

The password store can be backed up because every entry is encrypted to your GPG key.

However, backing up:

```text
~/.password-store
```

is useless unless you also retain access to the GPG private key.

Recommended backup components:

```text
~/.password-store/
GPG private key / hardware token
GPG revocation certificate
offline recovery codes
```

For maximum security, consider placing the GPG private key on a hardware security token instead of keeping a raw copy on disk.

---

# 16. Optional Git tracking for `pass`

`pass` supports Git:

```fish
pass git init
```

Commit:

```fish
pass git add .
pass git commit -m "Initialize password store"
```

Only push the encrypted store to a remote you trust.

Remember:

- file names are visible,
- directory structure is visible,
- encrypted contents remain protected by GPG.

Therefore, names such as:

```text
2fa/production-secret-root-account
```

may reveal metadata even when the token itself is encrypted.

Use neutral naming if metadata exposure matters.

---

# 17. Option C — TPM-backed `totpm`

Project:

https://github.com/koditoriet/totpm

`totpm` is a Linux CLI TOTP client that stores/decrypts TOTP secrets using TPM 2.0.

According to the project's design:

- encrypted token material is stored in an SQLite database,
- the TPM protects the primary key,
- decrypted secrets are intended not to leave the TPM,
- system mode can use a dedicated `totpm` user,
- fingerprint verification via `fprintd` can provide presence checking,
- secrets are deliberately not recoverable/exportable.

## Important consequence

If the machine, TPM key, system secret, or relevant storage is destroyed:

**the TOTP secrets cannot be recovered from `totpm`.**

Therefore, keep:

- service recovery codes,
- alternative hardware security keys,
- or another independently enrolled authenticator.

---

# 18. Verify TPM 2.0 on CachyOS

Check:

```fish
ls -l /dev/tpm*
```

Typical output:

```text
/dev/tpm0
/dev/tpmrm0
```

Inspect capabilities:

```fish
sudo pacman -S tpm2-tools
```

Then:

```fish
tpm2_getcap properties-fixed
```

Check EFI/TPM integration:

```fish
systemd-analyze has-tpm2
```

If supported, it should indicate usable TPM2 functionality.

---

# 19. Install Rust tooling for `totpm`

If Rust is not installed:

```fish
sudo pacman -S rust cargo
```

Or use `rustup` if that is your preferred toolchain management strategy.

Verify:

```fish
rustc --version
cargo --version
```

---

# 20. Build/install `totpm`

The upstream project currently documents two Linux installation styles.

## System install — preferred

```fish
cargo install --features=install totpm
```

Then:

```fish
sudo ~/.cargo/bin/totpm init
```

System mode is upstream's recommended mode because it provides better isolation against non-root local attackers.

## Local install

```fish
cargo install totpm
```

Then:

```fish
totpm init --local
```

Local mode is easier but provides weaker protection against a malicious process already running as your user.

> Before relying on the tool, run:
>
> ```fish
> totpm --help
> ```
>
> and use the command syntax from the version actually installed. The project is comparatively young and its CLI may evolve.

---

# 21. TPM permissions

`totpm` uses TPM2-TSS.

The upstream documentation states that users may need membership in the `tss` group.

Check:

```fish
getent group tss
```

If the group exists and your user is not a member:

```fish
sudo usermod -aG tss $USER
```

Then fully log out and back in.

Verify:

```fish
groups
```

Do **not** loosen permissions on `/dev/tpm*` as a shortcut.

---

# 22. Fingerprint presence verification

`totpm` can use `fprintd`.

Install:

```fish
sudo pacman -S fprintd
```

Enroll:

```fish
fprintd-enroll
```

Verify:

```fish
fprintd-verify
```

Whether fingerprint presence verification is useful depends on your threat model and hardware.

---

# 23. Why `totpm` can be stronger than ordinary desktop TOTP

Traditional software TOTP stores the seed somewhere accessible to software after decryption.

`totpm` attempts to bind the token to the physical TPM so the raw secret cannot simply be exported.

Conceptually:

```text
encrypted token blob
       │
       ▼
      TPM
       │
       ├─ decrypt internally
       ├─ compute TOTP
       │
       ▼
    123456
```

This is useful against attackers who obtain a copy of your home directory.

However:

- a root-level attacker may still be able to request codes while controlling the machine,
- same-device MFA reduces physical factor separation,
- TPM loss means token loss.

Use hardware security keys/WebAuthn whenever a service supports them.

---

# 24. Recommended hybrid model

A strong practical strategy is:

```text
Tier 1 — highest-value accounts
    FIDO2/WebAuthn hardware security key
    + offline recovery codes
    + optional totpm fallback

Tier 2 — normal TOTP accounts
    pass-otp

Tier 3 — legacy Authy-specific integrations
    keep Authy mobile until service can be migrated
```

Examples for Tier 1:

- primary email
- password manager
- GitHub
- domain registrar
- cloud administration
- identity provider

Prefer phishing-resistant FIDO2/WebAuthn over TOTP where possible.

---

# 25. Authy-specific vs. ordinary TOTP tokens

Authy can contain two broad token classes.

## Standard TOTP accounts

These are conventional TOTP seeds.

Typical examples:

```text
GitHub
Google
Microsoft
Cloudflare
Synology
```

They can normally be re-enrolled into another authenticator.

## Authy "Apps"

Some services historically used Authy's proprietary service integration.

These may:

- use device-specific token material,
- generate seven-digit codes,
- behave differently from normal TOTP,
- become invalid when a registered Authy device is removed.

The most commonly cited historical example is Twitch.

Do **not** assume every Authy token can be exported and treated as ordinary six-digit TOTP.

---

# 26. Unsupported migration path — reverse-engineered Authy export

This section is **not** the recommended route.

It exists for cases where manually re-enrolling dozens of accounts is impractical or where an old Authy installation contains tokens that need recovery.

Risks include:

- Authy API changes,
- Authy account suspension,
- accidental exposure of MFA seeds,
- unsupported tooling,
- stale software,
- untrusted binaries,
- incomplete export of proprietary Authy Apps.

---

# 27. `authy-cli`

Project:

https://github.com/jmhobbs/authy-cli

Historically it supported:

```text
authy-cli list
authy-cli token <id>
authy-cli sync
authy-cli export -
```

and could maintain a local encrypted Authy database.

However, its upstream README currently states that registration no longer works because the Authy API changed.

Therefore:

**Do not choose `authy-cli` as the foundation of a new MFA workflow.**

It may still be useful for an already-registered historical installation.

---

# 28. `authy-export`

Project:

https://github.com/ua741/authy-export

This project reverse-engineers enough of the Authy protocol to register itself as another device and export TOTP tokens in Key URI Format.

The upstream project explicitly warns that using it can cause Authy account suspension.

Treat it as:

```text
one-time migration utility
```

not:

```text
permanent Authy client
```

If you decide to use it:

1. Read the full source or build it yourself.
2. Perform migration from a trusted workstation.
3. Keep Authy mobile available during the process.
4. Export only once.
5. Immediately import tokens into the replacement system.
6. Verify every account.
7. Destroy plaintext exports.
8. Remove any temporary Authy device only after understanding the effect on Authy-specific Apps.

---

# 29. Old Authy Desktop extraction

If you already possess an **existing old Authy Desktop installation that still shows valid codes**, do not uninstall or modify it until migration is complete.

One historical extraction utility is:

https://github.com/authier-pm/authy-desktop-export

It relies on launching the old Electron app with:

```text
--remote-debugging-port=5858
```

Example historical Linux launch:

```fish
authy --remote-debugging-port=5858
```

The extraction utility can then access the application's internal state.

## Important warning

Opening an Electron remote debugging port exposes sensitive application internals locally.

While doing this:

- disconnect from untrusted networks,
- bind only to localhost if applicable,
- do not expose the port through firewall/NAT,
- close the application immediately after export,
- remove plaintext exported files after verified migration.

Do not install old Authy Desktop software solely to create a new production workflow.

---

# 30. Safe handling of a temporary export

Create a RAM-backed workspace:

```fish
mkdir -p /dev/shm/authy-migrate
chmod 700 /dev/shm/authy-migrate
cd /dev/shm/authy-migrate
```

`/dev/shm` is typically tmpfs, so files are memory-backed rather than written directly to persistent disk.

Verify:

```fish
findmnt /dev/shm
```

Perform any temporary conversion there.

When finished:

```fish
rm -rf /dev/shm/authy-migrate
```

Then verify:

```fish
test -e /dev/shm/authy-migrate; and echo "WARNING: still exists"
```

Do not place plaintext exports in:

```text
~/Downloads
~/Documents
cloud-synced folders
Git repositories
Dropbox
Google Drive
Syncthing
backup targets
```

---

# 31. Do not place TOTP seeds in environment variables

Avoid:

```fish
set -x AUTHY_EXPORT_PASSWORD "..."
```

or similar persistent environment variables.

Environment variables may leak through:

- crash dumps,
- process inspection,
- debugging tools,
- shell logs,
- scripts.

Prefer an interactive password prompt whenever possible.

---

# 32. Post-migration verification matrix

Build a checklist:

| Service | Recovery codes saved | New TOTP enrolled | Fresh login tested | Authy removed |
|---|---:|---:|---:|---:|
| GitHub | ☐ | ☐ | ☐ | ☐ |
| Google | ☐ | ☐ | ☐ | ☐ |
| Microsoft | ☐ | ☐ | ☐ | ☐ |
| Cloudflare | ☐ | ☐ | ☐ | ☐ |
| Synology | ☐ | ☐ | ☐ | ☐ |

Never bulk-delete Authy tokens before this table is complete.

---

# 33. Recovery-code storage

Recovery codes should not live next to the TOTP seed if you want meaningful failure independence.

Good options:

- printed copy in a secure physical location,
- encrypted offline removable media,
- password manager protected by a different recovery path,
- secure document vault,
- second physical site for critical accounts.

For particularly important accounts, keep at least one recovery method that does not depend on:

- the workstation,
- its TPM,
- the same GPG key,
- the same phone.

---

# 34. Hardware security keys are better where supported

If a service supports:

- FIDO2
- WebAuthn
- passkeys bound to a hardware authenticator
- security keys

prefer them over TOTP.

TOTP can be phished in real time.

FIDO2/WebAuthn provides origin binding and is substantially more resistant to credential phishing.

A strong configuration is:

```text
Primary:
  hardware security key

Secondary:
  second hardware security key

Recovery:
  offline recovery codes

Fallback:
  local TOTP only if required
```

---

# 35. Testing the resulting setup

List:

```fish
pass ls 2fa
```

Generate:

```fish
pass otp 2fa/github
```

Copy:

```fish
pass otp -c 2fa/github
```

Interactive:

```fish
otp
```

Direct helper:

```fish
otp github
```

Test several accounts before deleting anything from Authy.

---

# 36. Security hardening

## Lock screen

Require authentication on unlock.

## Full-disk encryption

Use LUKS for workstation storage.

## Swap

Ensure swap is encrypted if sensitive material could be paged to disk.

Check:

```fish
swapon --show
lsblk -f
```

## Core dumps

Consider limiting core dumps for processes handling secrets.

## Clipboard

Avoid persistent clipboard history for seeds.

## SSH

Do not expose password-store contents through unnecessary remote sessions.

## Shell logging

Do not enable terminal session recording while migrating TOTP seeds.

## Backups

Ensure backup destinations protect GPG keys and recovery materials appropriately.

---

# 37. Threat-model comparison

| Property | Authy Mobile | 1Password + `op` | pass-otp | totpm |
|---|---|---|---|---|
| Desktop GUI | No supported desktop Authy | Yes | No | No |
| Desktop CLI | No | **Yes** | Yes | Yes |
| Mobile access | Yes | **Yes** | Not normally | No |
| Browser OTP autofill | Limited/Authy-dependent | **Yes** | No | No |
| Cloud dependence | Yes/optional sync | 1Password account sync | No | No |
| Portable | Mobile-centric | **Yes** | Yes | No |
| Scriptable | No | **Yes** | Yes | Yes |
| One seed for GUI + CLI | No desktop GUI | **Yes** | CLI only | CLI only |
| Secret export possible | Officially no | Vault-dependent; avoid exposing raw seed | Yes if GPG key available | Intentionally no |
| Hardware binding | Mobile platform | Device/account security model | Depends on GPG setup | TPM |
| Easy backup | Authy cloud backup | 1Password account/recovery model | Encrypted file backup | No seed recovery |
| Good for automation | Poor | **Excellent** | Excellent | Good |
| Mature ecosystem | High | **High** | High | Lower |
| Machine-loss recovery | Authy account | 1Password account recovery model | Restore GPG + store | Recovery code/re-enroll |

---

# 38. Decision recommendation

For this workstation:

## Default

Use:

```text
1Password TOTP
    +
1Password CLI (`op`)
```

because it provides:

- a single authoritative TOTP seed,
- Linux desktop support,
- browser and mobile access,
- rolling-code autofill,
- direct command-line generation with `op item get ITEM --otp`,
- mature cross-platform synchronization,
- no second OTP database required.

## Independent local fallback

Where you intentionally want a separate local implementation, enroll the same seed into:

```text
1Password
    +
pass + pass-otp + GPG
```

This adds resilience and offline/local control at the cost of another copy of the TOTP seed.

## Higher-assurance selected accounts

Use:

```text
totpm
```

where machine binding is intentionally desired.

## Best security

Use:

```text
FIDO2/WebAuthn hardware keys
```

where supported.

---

# 39. Suggested directory layout

```text
~/.password-store/
└── 2fa/
    ├── cloud/
    │   ├── aws.gpg
    │   └── cloudflare.gpg
    ├── dev/
    │   └── github.gpg
    ├── identity/
    │   ├── google.gpg
    │   └── microsoft.gpg
    ├── infrastructure/
    │   └── synology.gpg
    └── misc/
```

Usage:

```fish
pass otp 2fa/dev/github
```

---

# 40. Migration sequence I recommend

Perform accounts in this order:

```text
1. Low-risk disposable account
2. Normal service
3. GitHub / developer services
4. NAS / infrastructure
5. Cloud infrastructure
6. Primary email
7. Password manager / identity provider
8. Financial / regulated accounts
```

This allows you to validate the workflow before touching accounts with severe lockout consequences.

---

# 41. Rollback plan

If a migration fails:

1. Do not delete the existing Authy entry.
2. Use Authy to sign back in.
3. Restore the previous MFA method if the service permits it.
4. Use recovery codes if needed.
5. Check system clock.
6. Check TOTP URI parameters.
7. Confirm the account was not re-enrolled with a different seed.
8. Retry only after access is stable.

If Authy itself becomes unavailable:

- use service recovery codes,
- use alternate registered security keys,
- invoke the service's account-recovery procedure.

---

# 42. Migration complete criteria

Do not consider Authy retired until:

- [ ] every account has been inventoried,
- [ ] every account has a recovery mechanism,
- [ ] every migrated token produces valid codes,
- [ ] every account has been tested with a fresh login,
- [ ] high-value services have a second independent recovery factor,
- [ ] plaintext migration artifacts are gone,
- [ ] clipboard history has been cleared,
- [ ] temporary QR images are removed,
- [ ] backup strategy is tested,
- [ ] recovery codes are stored independently.

---

# 43. Optional final cleanup

After every account has been independently verified:

1. Remove obsolete tokens from Authy.
2. Review Authy's registered devices.
3. Remove obsolete desktop devices.
4. Disable Authy account/device features you no longer need.
5. Keep the mobile Authy app temporarily if any proprietary Authy Apps remain.
6. Do not delete the Authy account until every proprietary integration has been confirmed migrated or removed.

---

# 44. Useful commands cheat sheet

## 1Password

```fish
op --version
op item get GitHub --otp
op item get GitHub --vault Personal --otp
op item list --categories Login --format=json
```

## pass-otp

```fish
pass ls 2fa
pass otp insert 2fa/github
pass otp 2fa/github
pass otp -c 2fa/github
pass otp uri 2fa/github
pass otp uri -q 2fa/github
```

## QR decode

```fish
zbarimg -q --raw qrcode.png
```

Wayland clipboard:

```fish
wl-paste | zbarimg -q --raw -
```

Direct import:

```fish
wl-paste | zbarimg -q --raw - | pass otp insert 2fa/github
```

## GPG

```fish
gpg --list-secret-keys --keyid-format=long
```

## TPM

```fish
ls -l /dev/tpm*
systemd-analyze has-tpm2
tpm2_getcap properties-fixed
```

## totpm

```fish
totpm --help
```

Use the installed version's help text for token-add/list/code-generation syntax.

---

# 45. Source references

## Twilio / Authy

- Authy Desktop EOL:
  https://www.twilio.com/en-us/changelog/end-of-life--eol--of-twilio-authy-desktop-apps
- Authy Desktop end-user guide:
  https://help.twilio.com/articles/22771146070299-End-user-guide-End-of-Life-EOL-for-Twilio-Authy-Desktop-app
- Export/import not supported:
  https://help.twilio.com/articles/19753420684059-Export-or-Import-Tokens-in-the-Authy-app

## 1Password

- One-time passwords:
  https://support.1password.com/one-time-passwords/
- 1Password on Linux:
  https://support.1password.com/explore/linux/
- 1Password CLI item reference:
  https://www.1password.dev/cli/reference/management-commands/item
- 1Password CLI getting started:
  https://developer.1password.com/docs/cli/get-started/

## CLI / local tools

- pass-otp:
  https://github.com/pass-extension/pass-otp
- totpm:
  https://github.com/koditoriet/totpm
- authy-cli:
  https://github.com/jmhobbs/authy-cli
- authy-export:
  https://github.com/ua741/authy-export
- authy-desktop-export:
  https://github.com/authier-pm/authy-desktop-export

---

# 46. Final recommended implementation

For the requested operating model, use **1Password as the primary source of truth** for ordinary TOTP credentials.

```text
CachyOS
  ├── 1Password Desktop
  ├── 1Password browser extension
  ├── 1Password CLI (`op`)
  ├── fzf / jq / wl-clipboard
  │
  ├── optional independent CLI store
  │    ├── pass
  │    ├── pass-otp
  │    └── GPG
  │
  └── optional machine-bound store
       └── totpm + TPM 2.0
```

For each existing Authy service, re-enroll once and capture the new TOTP enrollment into **1Password**.

Then terminal access is immediately available through:

```fish
op item get GitHub --otp
```

or through a helper:

```fish
otp GitHub
```

For new services, follow the same policy from the beginning.

If an account warrants an independent local fallback, capture the **same enrollment QR/seed at enrollment time** into `pass-otp` or `totpm` as well.

The preferred operational hierarchy is:

```text
1. FIDO2/WebAuthn hardware security key where supported
2. 1Password TOTP for standard authenticator-based MFA
3. 1Password CLI for terminal access to that same TOTP
4. pass-otp as an optional independent local fallback
5. totpm for selected workstation-bound TOTP credentials
6. Authy mobile only for proprietary Authy integrations that cannot yet migrate
```

This achieves the core requirement:

> **Every ordinary TOTP service can be available from 1Password and from the command line, without depending on Authy Desktop.**

The simplest implementation does this with **one copy of the seed in 1Password** and uses 1Password CLI for terminal access. The dual-store implementation remains available where local independence is worth the additional secret copy.

