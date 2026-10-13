# Local candidate installation — 2026-10-12

The Phase 4–5 implementation request authorizes the local software integration.
The concrete preview for tested `authy_local-1.0.0rc1-py3-none-any.whl` passed
against the existing owned installation. Its SHA-256 is
`5539af5026aa7c0b4eebaf2733f783e5e9bb7ccf0c9cecb68899d34c8997bcc4`.

The main footprint remains the owned `.local/bin/otp-local`, three
`.config/fish/functions/otp1p{,c,f}.fish` files, a private release directory under
`.local/share/authy-local/releases/WHEEL_SHA256/` and private installation state
under `.local/state/authy-local/`. No alias, PATH or startup edits are requested.
The previous installed release remains available for verified rollback.

Separately, [native setup](2026-10-12-optional-setup.md) installs the exact reviewed
totpm binary, hardened pass-otp extension and their licenses under the dedicated
optional directory. Its own manifest tracks ownership. The main installer never
removes native dependencies, encrypted stores, keys or TPM state.

```sh
.venv/bin/python scripts/install.py install \
    --wheel dist/authy_local-1.0.0rc1-py3-none-any.whl --apply
.venv/bin/python scripts/prepare_optional.py --apply-runtime \
    --pass-source /tmp/Authy-to-1Password_Local/pass-otp-source \
    --totpm-binary /tmp/Authy-to-1Password_Local/totpm-source/target/release/totpm
```

Neither operation creates GPG keys, initializes a TPM, requests an OTP or changes
an account. Operational results are recorded in the
[verification report](2026-10-12-phase-4-5-verification.md).
