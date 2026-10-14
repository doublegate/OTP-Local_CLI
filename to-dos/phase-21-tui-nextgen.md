# Phase 21: Next-Generation Textual TUI 2.0 (v2.9.0)

Status: Planned; milestone for release v2.9.0. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Elevate the terminal user experience to modern, responsive graphical fidelity by redesigning the Textual TUI with hierarchical vault folders, color-coded custom tagging, smooth animated circular countdown timers, an integrated audit log visualizer, live optical webcam QR scanning, and batch management actions.

## Entry Conditions and Dependencies

- Phase 20 completed and verified.
- Textual v0.80+ UI framework and camera/optical capture utilities.

## Sprint Sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-21.1](sprints/21.1.md) | Modern UI dashboard (vault folders, tags, circular timers, audit replay) | Entry gate |
| [S-AUTH-21.2](sprints/21.2.md) | Optical webcam QR scanner, batch actions, and bulk modals | S-AUTH-21.1 |

All tasks in each sprint must have automated synthetic test verification before closing.

## Deliverables and Evidence

- Modernized Textual screens and custom widgets in `src/authy_local/tui/`:
  - `CountdownRing`: Smooth circular SVG/Unicode progress widget with dynamic warning palettes.
  - `VaultSidebar`: Hierarchical tree browser grouping credentials by vault provider, folders, and tags.
  - `AuditLogViewer`: Tamper-evident audit event inspector with search and verification badges.
- Optical QR scanner module in `src/authy_local/tui/scanner.py` with camera capture and static image drag-and-drop.
- Batch operations modal supporting multi-select tagging, batch deletion, and batch migration.
- Automated pilot and headless pilot test suite in `tests/test_tui_v2.py`.
- Updated TUI documentation in `docs/specs/11-tui.md`.

## Exit Criteria

- Zero visual stutter or frame drops during continuous 30fps progress ring animations.
- Optical QR scanner reliably detects standard and inverted QR codes under low lighting.
- All existing keyboard shortcuts and accessibility affordances preserved.
