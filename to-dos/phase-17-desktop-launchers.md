# Phase 17: Desktop Launcher and Shell Integration (v2.5.0)

Status: Planned; milestone for release v2.5.0. See [delivery index](README.md) and [ROADMAP.md](../ROADMAP.md).

## Objective

Elevate everyday desktop productivity across Linux and macOS by implementing native status bar streaming modules (Waybar, Polybar), interactive desktop application launcher scripts (Raycast, Alfred 5), and keyboard-driven window-manager fuzzy pickers (Rofi, Wofi, Fzf).

## Entry Conditions and Dependencies

- Phase 16 completed and verified.
- Resident UNIX socket daemon (`src/authy_local/daemon.py`) and fast IPC operational.

## Sprint Sequence

| Sprint | Purpose | Dependency |
|---|---|---|
| [S-AUTH-17.1](sprints/17.1.md) | Linux status bar streaming modules (Waybar, Polybar) | Entry gate |
| [S-AUTH-17.2](sprints/17.2.md) | Quick-launchers and fuzzy pickers (Raycast, Alfred, Rofi, Wofi) | S-AUTH-17.1 |

All tasks in each sprint must have automated synthetic test verification before closing.

## Deliverables and Evidence

- Status bar module in `src/authy_local/integrations/statusbar.py` outputting continuous JSON events for Waybar and Polybar with remaining-seconds progress counters and tooltip account menus.
- Raycast extension script in `integrations/raycast/` with instant search and automatic clipboard copy.
- Alfred 5 workflow in `integrations/alfred/` supporting fuzzy search filter and hotkey trigger.
- Native Rofi / Wofi / Fzf script in `integrations/launchers/otp-picker.sh` connecting directly to the local daemon socket.
- Comprehensive automated test suite in `tests/test_desktop_launchers.py`.
- Documentation and setup guide in `docs/operations/desktop-launchers.md`.

## Exit Criteria

- Sub-5ms response latency when querying credentials from Rofi or Alfred via daemon IPC.
- Zero CPU busy-waiting in Waybar/Polybar continuous streaming daemon loop.
- Clipboard auto-wipe behavior verified across X11, Wayland, and macOS clipboards.
