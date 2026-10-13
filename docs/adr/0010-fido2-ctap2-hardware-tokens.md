# ADR 0010: Hardware-Enforced Isolation via FIDO2 CTAP 2.1 HMAC-Secret

- Status: Proposed for release v1.3.0 (Phase 8)
- Supersedes: None; extends Explicit Local Backends (ADR 0005)

## Context

Software-only TOTP stores store encrypted seeds on disk where decryption keys may be vulnerable to memory scraping or root filesystem compromise. Physical security tokens (YubiKey, SoloKey, Nitrokey) offer hardware-isolated execution where secret keys cannot be extracted.

While standard OATH-TOTP on YubiKeys (`ykman oath`) is limited in slot capacity (typically 32 to 64 accounts), the FIDO2 / CTAP 2.1 protocol provides an `hmac-secret` extension (and WebAuthn PRF) capable of deriving deterministic symmetric secrets for an unlimited number of credentials while requiring physical touch presence.

## Decision

1. Implement `Fido2Backend` in `src/authy_local/backends/fido2.py` utilizing `python-fido2` and CTAP 2.1.
2. Store TOTP seeds encrypted with keys derived dynamically from the physical security key via `HMACGetSecretInput` and deterministic per-credential salts.
3. Require physical user touch presence (UP) and optional PIN verification (UV) for every decryption event.
4. Support multi-token registration: Allow users to enroll a primary and a backup security key simultaneously.
5. Provide an interactive pulsing visual touch prompt modal (`Fido2TouchModal`) in the Textual TUI during hardware assertions.

## Consequences

- Completely eliminates unencrypted seed storage on disk; compromising the host disk does not compromise the TOTP seeds.
- Scales to thousands of accounts without being restricted by legacy YubiKey OATH slot limits.
- Requires physical presence, protecting against remote malware and headless exfiltration.
- Gracefully handles USB disconnects with clear diagnostic feedback in the TUI and CLI.
