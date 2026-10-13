# Project: Modernize Authy-to-1Password TUI & Performance Optimization

## Architecture
- **Language & Runtime**: Python 3.14 on Linux (interactive terminal).
- **Core Subsystems**:
  - `src/authy_local/tui.py`: Modernized Textual TUI Application (`AuthyApp`), screens (Dashboard, Browser, Doctor, CodeModal, ScopeForm, MessageModal, HelpOverlay), styles, and action dispatchers.
  - `src/authy_local/tui_items.py`: Item catalog indexing, fast fuzzy search, argument builder, deletion helpers.
  - `src/authy_local/tui_profiles.py`: Scope file management (`~/.config/authy-local/tui-profiles.json`, permissions `0600`).
  - `src/authy_local/backends/`: Token retrieval (`onepassword.py`, `local.py`) with capability probe caching and in-memory TOTP window caching.
  - `src/authy_local/cache.py`: In-memory TOTP cache keyed by `(backend, item_id, time_step)`.
  - `src/authy_local/cli.py`: CLI entrypoints (`otp-local tui`), terminal checks, and dispatch integration.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Capability Probe Caching | Cache external tool version checks (`op --version`, `oath --version`, `totpm --version`) to avoid subprocess latency on hot-paths | M1 | Survey (Explorer 3) |
| 2 | In-Memory TOTP Window Cache | Ephemeral cache for TOTP codes valid within RFC 6238 30s window to avoid re-decryption on repeated view/copy | M1 | Survey (Explorer 3) |
| 3 | Fast Search & Fuzzy Indexing | Pre-indexed token keys/labels with fast subsequence matching for instant filtering | M1 | Survey (Explorer 3) |
| 4 | Benchmark Verification Suite | Microbenchmarks measuring subprocess probes, cache lookups, search scaling, before vs after | M1 | Survey (Explorer 3) |
| 5 | Textual App Scaffolding | Textual application skeleton, layout, color palette, base screens, and responsive CSS | M2 | Survey (Explorer 1) |
| 6 | Dependency & Packaging Config | Add Textual to `pyproject.toml` and `.venv`, adapt offline installer / smoke package | M2 | Survey (Explorer 2) |
| 7 | Action: "Doctor" | Inspect local capabilities (1Password CLI, GPG pass, totpm, TPM) without authenticating | M3 | ORIGINAL_REQUEST §R1 |
| 8 | Action: "Show code" | Prompt for account/service, retrieve OTP code, display with countdown timer | M3 | ORIGINAL_REQUEST §R1 |
| 9 | Action: "Copy code" | Prompt for account/service, retrieve OTP code, copy to desktop clipboard | M3 | ORIGINAL_REQUEST §R1 |
| 10 | Action: "Browse and show" | Interactive token list browser, search/filter, Enter/s shows code | M3 | ORIGINAL_REQUEST §R1 |
| 11 | Action: "Browse and copy" | Interactive token list browser, search/filter, Enter/c copies code | M3 | ORIGINAL_REQUEST §R1 |
| 12 | Action: "Installation preview" | Preview local wheel without applying changes | M3 | ORIGINAL_REQUEST §R1 |
| 13 | Action: "Private migration guide" | Review migration steps and independent recovery checkpoints | M3 | ORIGINAL_REQUEST §R1 |
| 14 | Action: "Saved scope" | Interactive form to configure resident account/vault IDs or local store paths | M3 | ORIGINAL_REQUEST §R1 |
| 15 | Terminal Suspension Handoff | Suspend Textual UI during external 1Password biometric authorization or CLI invocation | M3 | Survey (Explorer 1) |
| 16 | Real-time TOTP Countdown Bar | Visual progress bar showing remaining seconds in current 30-second TOTP window | M4 | ORIGINAL_REQUEST §R3 |
| 17 | Instant Fuzzy Search in Browser | Real-time typing filter with match highlighting in token browser | M4 | ORIGINAL_REQUEST §R3 |
| 18 | Clipboard Copy Notification | Visual toast / status badge confirming copy action to desktop clipboard | M4 | ORIGINAL_REQUEST §R3 |
| 19 | Keyboard Shortcuts Help Overlay | Modal / footer displaying available keybindings for fast navigation | M4 | ORIGINAL_REQUEST §R3 |
| 20 | TUI Unit & Component Tests | Comprehensive tests for Textual screens, widgets, and actions using Textual test runner | M5 | ORIGINAL_REQUEST §Testing |
| 21 | Pytest Regression Pass | Refactor tests mocking curses to new architecture; full pytest suite passes | M5 | ORIGINAL_REQUEST §Testing |
| 22 | Coverage Maintenance | Maintain aggregate branch test coverage >= 90% | M5 | Survey (Explorer 2) |
| 23 | E2E Testing Verification (Tiers 1-4) | Pass 100% of requirement-derived opaque-box E2E test suite | M6 | ORIGINAL_REQUEST §AC |
| 24 | Adversarial Hardening (Tier 5) | White-box adversarial testing and edge-case boundary hardening | M6 | Project Pattern |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Core Performance Optimizations & Benchmarking | In-memory TOTP cache, capability probe caching, fast fuzzy search index, benchmark suite | none | DONE |
| M2 | Modern Textual TUI Foundation & Packaging | Textual integration in pyproject.toml, packaging adjustments, App skeleton, base layout | none | DONE |
| M3 | Menu Actions & Dialogs Migration (All 8 Actions) | Implement all 8 original actions in Textual with terminal suspension for biometric auth | M1, M2 | DONE |
| M4 | Feature Enhancements & UX Polishing | Real-time countdown bar, instant fuzzy search, copy notification badge, help overlay | M3 | DONE |
| M5 | Test Suite Modernization & Pytest Pass | Unit/integration tests for Textual components, curses mock test migration, full pytest pass | M4 | DONE |
| M6 | Final Verification & Adversarial Hardening | Pass 100% E2E test suite (Tiers 1-4), Tier 5 adversarial hardening, gate approval | M5, TEST_READY.md | DONE |

## Interface Contracts
### `authy_local.cache`
- `get_cached_totp(backend: str, item_id: str, time_step: int) -> str | None`
- `set_cached_totp(backend: str, item_id: str, time_step: int, code: str) -> None`
- `clear_cache() -> None`

### `authy_local.tui_items`
- `records(backend: str, store: Path | None = None) -> list[tuple[str, str]]`
- `fuzzy_filter(rows: list[tuple[str, str]], query: str) -> list[tuple[str, str]]`
- `arguments(backend: str, key: str, vault: str | None = None, account: str | None = None) -> list[str]`
- `remove(backend: str, key: str) -> None`

### `authy_local.tui` (Textual Application)
- Class `AuthyApp(App)`
- Entry function `run(dispatch: Callable, preview: Callable, terminal: bool = True) -> int`
- CLI invocation: `authy_local tui` connects CLI dispatch callbacks into `AuthyApp`

## Code Layout
- `src/authy_local/tui.py`: Main Textual application and screen definitions.
- `src/authy_local/tui_items.py`: Item catalog helpers and search filtering.
- `src/authy_local/tui_profiles.py`: Scope file read/write with 0600 permissions.
- `src/authy_local/cache.py`: Ephemeral in-memory TOTP window cache.
- `src/authy_local/backends/`: Backend adapters with cached capability probes.
- `tests/test_tui_textual.py`: Modernized unit tests for Textual TUI components.
- `tests/test_cache.py`: Unit tests for TOTP caching logic.
- `tests/test_benchmarks.py`: Integration tests asserting benchmark execution and speedups.
- `benchmarks/`: Performance benchmarks and profiling scripts.
- `tests/e2e/`: Opaque-box E2E test suite created by E2E Testing Track.
