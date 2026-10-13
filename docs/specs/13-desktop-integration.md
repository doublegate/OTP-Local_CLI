# Desktop and System Integration Guide

Status: Implemented and verified for CLI and desktop delivery, 2026-10-13.
Extends [CLI Specification](03-cli-specification.md) and [Textual TUI](11-tui.md).

## 1. Overview

Authy Local integrates into desktop workflows on Linux (Wayland and X11) through:

1. Freedesktop application entries (`.desktop` files) for application menus and launchers.
2. Direct systemd user service management for the ephemeral session agent.
3. Global hotkey bindings in modern Wayland compositors (Hyprland, Sway) and window managers.
4. Native shell auto-completions for `fish`, `bash`, and `zsh`.
5. Offline backup export (`otp-local export`) with optional recipient-targeted GPG encryption.

## 2. Desktop Entries

Two `.desktop` specifications are provided under `share/applications/`:

- **Authy Local Dashboard** (`share/applications/authy-local.desktop`):
  Launches the full interactive Textual TUI dashboard (`otp-local tui`) inside your preferred terminal emulator.
- **Quick OTP Picker** (`share/applications/otp-pick.desktop`):
  Launches the native quick-launcher picker (`otp-local pick`) using `wofi`, `rofi`, or `fzf`, copying the selected token directly to the clipboard with zero terminal window flashes.

### Installation

To register both desktop entries with your user application menu:

```bash
mkdir -p ~/.local/share/applications
cp share/applications/*.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications/
```

## 3. Global Hotkey Configuration

Binding the quick-picker to a global keyboard shortcut provides instant two-factor access across any active window.

### 3.1 Hyprland (`~/.config/hypr/hyprland.conf`)

```ini
# Bind Super + O to launch quick OTP picker
bind = $mainMod, O, exec, otp-local pick
```

### 3.2 Sway (`~/.config/sway/config`)

```ini
# Bind Mod4 + O to launch quick OTP picker
bindsym Mod4+o exec otp-local pick
```

### 3.3 i3 (`~/.config/i3/config`)

```ini
# Bind Mod4 + O to launch quick OTP picker
bindsym Mod4+o exec otp-local pick
```

### 3.4 KDE Plasma & GNOME

- Open **System Settings** -> **Shortcuts** -> **Custom Shortcuts**.
- Add a new command shortcut triggering `otp-local pick`.
- Assign preferred key combination (e.g. `Meta + O` or `Ctrl + Alt + O`).

## 4. Systemd User Service

The ephemeral session agent daemon (`otp-local agent`) can be managed as a systemd user unit.

### Service Definition (`share/systemd/user/authy-local-agent.service`)

```ini
[Unit]
Description=Authy Local Ephemeral Session Agent
Documentation=https://github.com/doublegate/OTP-Local_CLI
After=default.target

[Service]
Type=simple
ExecStart=%h/.local/bin/otp-local agent start --timeout 900
Restart=on-failure
RestartSec=3s
PrivateTmp=true

[Install]
WantedBy=default.target
```

### Activation

```bash
mkdir -p ~/.config/systemd/user
cp share/systemd/user/authy-local-agent.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now authy-local-agent.service
```

Verify service status:

```bash
systemctl --user status authy-local-agent.service
otp-local agent status
```

## 5. Shell Completions

Native completion scripts provide tab completion for commands, backends, launchers, and format options.

### 5.1 Fish Shell

```bash
mkdir -p ~/.config/fish/completions
cp fish/completions/otp-local.fish ~/.config/fish/completions/
```

### 5.2 Bash

```bash
mkdir -p ~/.local/share/bash-completion/completions
cp completions/bash/otp-local ~/.local/share/bash-completion/completions/
```

### 5.3 Zsh

```bash
mkdir -p ~/.zsh/completion
cp completions/zsh/_otp-local ~/.zsh/completion/
```

Ensure `fpath=(~/.zsh/completion $fpath)` is present in `~/.zshrc`.

## 6. Offline Backups & Export

The `otp-local export` command enables exporting stored credentials for emergency backups, migration to hardware authenticators, or secure storage.

### 6.1 Formats

- `uri`: Line-delimited standard `otpauth://totp/...` or `steam://...` URIs.
- `aegis`: Standard JSON export compatible with Aegis Authenticator.
- `csv`: Standard CSV format with column headers `Account,Issuer,Secret,Digits,Period,Algorithm,Type,URI`.

### 6.2 Plaintext Export (Strict 0600 Permissions)

```bash
otp-local export --backend pass-otp --format aegis --output ~/backup.json
```

### 6.3 GPG-Encrypted Export

Exports directly through `gpg` process pipes so unencrypted secrets never touch disk:

```bash
otp-local export --backend pass-otp --format aegis --encrypt-gpg user@example.com --output ~/backup.json.gpg
```
