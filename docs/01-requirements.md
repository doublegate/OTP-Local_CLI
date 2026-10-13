# Requirements and acceptance

## Product boundary

Deliver a local terminal companion and an operator-led migration procedure. The
companion retrieves current codes from an existing 1Password item; enrollment is
performed through the native UI and the protected service. The project is not a
new password manager, Authy client, TOTP engine, or synchronization service.

Primary user: workstation owner using CachyOS, Wayland and fish. Secondary access
is the existing 1Password mobile/browser experience. Python 3.14 is the initial
development target; broader OS support is outside this baseline.

## Requirements

| ID | Requirement | Acceptance evidence | Sprint |
|---|---|---|---|
| R-01 | One authoritative ordinary-account TOTP store in 1Password | ADR and human pilot using UI and CLI | 0.1, 3.1 |
| R-02 | Explicit account, vault and item scope | Fake-tool argv tests; wrong-scope live test by operator | 1.2 |
| R-03 | Show only a validated current code on explicit request | Exact stdout/error/length tests | 1.2 |
| R-04 | Clipboard mode prints no code and never writes on retrieval failure | Mock clipboard call assertions | 2.1 |
| R-05 | Interactive selector never silently chooses an ambiguous item | Duplicate labels, control characters, cancel tests | 2.1 |
| R-06 | No seed export, enrollment, deletion or vault writes in the companion | Allowed-command tests and review | 1.2 |
| R-07 | Offline development and synthetic credentials | Tests pass with real op unavailable | 1.1 |
| R-08 | Reversible install without overwriting user functions | Conflict, retry and uninstall tests | 2.2 |
| R-09 | Recovery verified before each enrollment change | Private operator checklist | 3.1, 3.2 |
| R-10 | Every in-scope account has a terminal access and recovery outcome | Aggregate reconciliation of private ledger | 3.2, 5.2 |
| R-11 | Optional stores do not block baseline completion | Explicit adopted/skipped branch decisions | 4.1, 4.2 |
| R-12 | Retirement requires successful fresh login and independent recovery | Per-account checks and final signed-off counts | 5.1, 5.2 |
| R-13 | Backend errors and metadata never become executable text | Injection/error fixtures; shell=False review | 1.1, 2.1 |
| R-14 | No real secrets or account inventories in project artifacts | Manual review and fixture provenance | All |
| R-15 | Cohesive keyboard TUI using the same scoped operations and safe errors | Navigation, cancellation, terminal and package tests; human synthetic acceptance | 2.3, 5.2 |

## Quality and resource limits

The companion adds no network client, background service, analytics or database.
Only approved backends communicate with their providers. No persistent code cache
or item-list cache is created by this project. Vendor-managed caches are a separate
boundary and are not claimed absent.

Each backend operation is bounded by time and bytes as specified in the
[CLI contract](03-cli-specification.md). At most one retrieval is active per
invocation; no speculative calls, polling or automatic retry after cancellation.
Latency is dominated by the human authorization prompt; record that separately
from mocked processing performance, without inventing a production latency target.

## Completion levels

1. Design complete: coherent specs, research evidence, ADRs and phase plans exist.
2. Software complete: specified offline gates pass, reversible installation works,
   and a human has checked native desktop integration using a synthetic item.
3. Migration complete: all in-scope accounts are verified or explicitly excluded,
   recovery is tested, and retirement conditions are met.

An excluded proprietary integration is a recorded exception, not a successful
migration. If Authy must remain for one, report partial retirement explicitly.
Optional stores may be skipped. Do not equate software release with migration
completion or demand an unsupported export to reach a misleading complete state.

## Non-goals

No bulk MFA changes, scraping of enrollment pages, automatic recovery-code handling,
service-account credentials, remote OTP API, scheduled OTP generation, clipboard
history manipulation, TPM administration, or publication in the baseline.
