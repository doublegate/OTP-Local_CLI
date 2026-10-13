# Research and host evidence — 2026-10-11

Scope: read-only executable/package/help checks and primary-source research.
No vault enumeration, OTP retrieval, account enrollment, package installation,
clipboard read or GPG-key inspection was performed. Findings describe this host
and documented behavior; they do not establish authenticated readiness.

## Host observations

| Check | Observed | Meaning/limit |
|---|---|---|
| OS/session | CachyOS rolling, kernel 7.2.9-2-cachyos, Wayland | Initial supported environment |
| 1Password Desktop | Package 8.12.40-31 | Present; unlock/integration unknown |
| CLI | `op` 2.39.0, package 2.39.0-1 | Help inspected, no authenticated command run |
| Shell | fish 4.9.3 | Wrapper syntax target |
| Runtime | Python 3.14.7-2 | Available; project environment absent |
| Selector/JSON | fzf 0.74.5-1.1; jq 1.8.2-1.1 | Available; jq not a runtime requirement |
| Clipboard | wl-clipboard 2.3.0-1.1 | Installed; actual copy/history behavior untested |
| Encryption | GnuPG 2.4.9-3.1 | Installed; key readiness unknown |
| Optional packages | pass, pass-otp, totpm, tpm2-tools, fprintd absent | No installation attempted; fingerprint hardware is not required |
| Development | Ruff 0.17.0-1.1; python-pytest 9.1.1; ShellCheck present | Not a project test suite |
| Markdown | markdownlint-cli2 0.23.3 / markdownlint 0.41.1 | Available; no project config yet |
| Time, host-level | NTP=yes; NTPSynchronized=yes; America/New_York | Snapshot, not future drift guarantee |
| TPM, host-level | `/dev/tpm0`, `/dev/tpmrm0` exist, mode 0660; MSFT0101:00 | Capability, not effective user access/provisioning |
| TPM assessment | systemd has-tpm2: yes; firmware/driver/system/subsystem/libraries present | No seed operation or initialization |
| Named fish helper files | otp/otp1p/otp1pc/otp1pf files absent | Other function definitions not ruled out |
| Version control | Parent workspace repository; project ignored | Standalone repository decision remains open |

The sandbox could not reach the host system bus and initially hid TPM devices.
A narrowly scoped read-only host check resolved visibility. Do not diagnose host
failure from those sandbox results, or infer a permission to alter host settings.

Local `op --help`, `op item get --help` and `op item list --help` confirmed scoped
`--account`, `--vault`, `--otp`, Login category listing, JSON formatting, no-color
and `--cache=false` options. Actual prompts, credentials and item responses remain
untested. No claim is made that all Login items have TOTP fields.

## Primary sources and design consequences

| Source | Verified/documented finding | Consequence |
|---|---|---|
| [Twilio Authy Desktop EOL guide](https://help.twilio.com/articles/22771146070299-End-user-guide-End-of-Life-EOL-for-Twilio-Authy-Desktop-app) | Desktop ended March 19, 2024; no supported export flow in guide | Re-enroll ordinary accounts; avoid historical desktop extraction as baseline |
| [1Password CLI desktop integration](https://www.1password.dev/cli/app-integration) | Linux uses native app, Polkit and system authentication settings | Human settings gate; do not require fingerprint reader |
| [1Password item commands](https://www.1password.dev/cli/reference/management-commands/item) | OTP retrieval and scoped listing documented; JSON-template edits can overwrite passkeys | Read-only companion; native UI enrollment; no item-template edits |
| [1Password CLI reference](https://www.1password.dev/cli/reference) | IDs, scope and default Unix memory cache described | Explicit IDs; disable cache per own call; no claim all vendor caching disappears |
| [1Password one-time passwords](https://support.1password.com/one-time-passwords/) | Native QR/manual enrollment supported | Keep seed handling in native app |
| [1Password CLI installation](https://www.1password.dev/cli/get-started) | Official installation/integration entry point | Consult before future package changes; installed host needs no automatic install |
| [fish language](https://fishshell.com/docs/current/language.html) | Function autoloading and pipeline status behavior documented | Thin wrappers; verify exit propagation and live collisions |
| [RFC 6238](https://datatracker.ietf.org/doc/html/rfc6238) | TOTP standard and reference vectors | Use independent synthetic vectors for optional compatibility; no new engine |
| [Google key URI format](https://github.com/google/google-authenticator/wiki/Key-Uri-Format) | URI fields include algorithm, digits and period | Preserve parameters when evaluating optional stores; test actual app support |
| [pass-otp](https://github.com/pass-extension/pass-otp) and [implementation](https://github.com/pass-extension/pass-otp/blob/develop/otp.bash) | Hidden insert/generation flows; URI-bearing diagnostics and version-dependent oathtool path | Safe-entry/source review gate before adoption |
| [totpm](https://github.com/koditoriet/totpm) | Local/system modes and hardware-bound storage described | Separate privilege/recovery design; release-specific CLI still unverified |
| [jmhobbs/authy-cli](https://github.com/jmhobbs/authy-cli) | Registration/API compatibility warning; diagnostic/export sensitivity | Do not run as baseline migration |
| [alexzorin/authy](https://github.com/alexzorin/authy) | Archived project reports attestation incompatibility | Historical extractor is not current migration evidence |

Research is a dated snapshot, not an endorsement of community export tools.
The historical `ua741/authy-export` fork's reachable documentation does not prove
current service compatibility; its behavior has not been tested here.

## Open verification before execution

- Human desktop unlock/CLI integration, intended account/vault selection and synthetic pilot.
- CLI account-identifier validation against the chosen installed configuration.
- Clipboard manager retention, fzf safety options and terminal behavior on the real session.
- Per-service MFA, proprietary Authy and recovery instructions at migration time.
- Optional store release/source review, algorithm compatibility and recovery drills.
- Repository policy and installer collision checks across live fish definitions.

## Reference preservation

The original v2 reference remains immutable. Its SHA-256 baseline is:

```text
d4ae68a822ee2652c690aa155e071adce43561984826c0462bd5d01748e0faca
```

The derived specifications replace ambiguous examples with explicit contracts.
They do not certify the original's host-installation commands or export tools.
