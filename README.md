# OTP-Local CLI

[![Release](https://img.shields.io/badge/release-v1.0.0-blue.svg)](https://github.com/doublegate/OTP-Local_CLI/releases/tag/v1.0.0)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg)](README.md#cross-platform-installation)
[![Security](https://img.shields.io/badge/security-Zero--Disk--Storage-success.svg)](SECURITY.md)
[![UI](https://img.shields.io/badge/UI-Textual%20TUI-blueviolet.svg)](docs/11-tui.md)

![OTP-Local CLI Banner](assets/banner.svg)

Local terminal companion, migration engine, and security layer for accessing two-factor authentication (TOTP/HOTP) tokens across 1Password, local GPG `pass-otp`, hardware TPM 2.0 enclaves, and YubiKeys.

Designed for security engineers, operators, and developers who require instant, secure, and auditable OTP access in their local shell environment without persistent disk seed storage or vendor cloud lock-in.

---

## Visual Interface Overview

`otp-local tui` provides a real-time terminal dashboard powered by Textual, featuring dynamic countdown bars, search filtering, one-touch clipboard copying with automatic scrubbing, QR code visualization, and comprehensive environment diagnostics.

![OTP-Local TUI Preview](assets/tui_preview.svg)

---

## System Architecture

The architecture isolates secret material inside designated secure hardware or credential stores. The CLI and TUI interact through an ephemeral local UNIX domain socket session daemon that holds zero unencrypted state on disk and enforces memory zeroization upon process termination.

```mermaid
flowchart TD
    subgraph UI ["Operator Interfaces"]
        CLI["CLI Commands (otp-local)"]
        TUI["Terminal UI (Textual TUI)"]
        FISH["Fish Shell Functions (otp1p, otp1pc)"]
    end

    subgraph Core ["Local Agent & Security Enclave"]
        DISPATCH["Command Dispatcher & Argument Parser"]
        AGENT["Ephemeral Session Agent (UDS Socket)"]
        SCRUBBER["Clipboard Auto-Wiper (30s Scrub Timer)"]
        AUDITOR["Weak Secret & Duplicate Hash Auditor"]
    end

    subgraph Backends ["Hardware & Cryptographic Backends"]
        OP["1Password CLI (op)"]
        PASS["pass-otp (GPG Keyring)"]
        TPM["totpm (TPM 2.0 Enclave)"]
        YUBI["YubiKey (oathtool / PCSC)"]
    end

    CLI --> DISPATCH
    TUI --> DISPATCH
    FISH --> DISPATCH

    DISPATCH --> AGENT
    AGENT --> OP
    AGENT --> PASS
    AGENT --> TPM
    AGENT --> YUBI

    DISPATCH --> SCRUBBER
    DISPATCH --> AUDITOR
```

---

## Token Acquisition & Clipboard Lifecycle

The sequence below illustrates the bounded lifecycle of an OTP request. Secret seeds are never written to disk or exposed in error logs; clipboard memory is automatically zeroized after a configurable duration.

```mermaid
sequenceDiagram
    autonumber
    actor User as Operator
    participant Shell as Shell / TUI
    participant Agent as Ephemeral Session Agent
    participant Backend as Keyring / Hardware Enclave
    participant Clip as System Clipboard

    User->>Shell: Request OTP (show / copy / tui)
    Shell->>Agent: Query token via private socket (0600)
    alt Cached Session Active
        Agent-->>Shell: Return TOTP code
    else Session Locked / Idle Timeout
        Agent->>Backend: Authenticate & generate bounded OTP
        Backend-->>Agent: Bounded OTP code (6-8 digits)
        Agent-->>Shell: Forward OTP code
    end
    alt Copy Action Selected
        Shell->>Clip: Write OTP code
        Shell->>Shell: Arm asynchronous scrubber timer (30s)
        Note over Shell,Clip: Timer fires after 30 seconds
        Shell->>Clip: Overwrite and scrub clipboard buffer
    else Show Action Selected
        Shell->>User: Display OTP with visual TTL countdown
    end
```

---

## Performance Benchmarks

Performance was evaluated on Linux (Kernel 6.13, AMD/Intel x86_64) across all execution paths. In-process token computation completes in microseconds, while the ephemeral session agent reduces multi-account latency by over 99% compared to raw external CLI spawning.

![Benchmark Latency Graph](assets/benchmark_timings.svg)

| Execution Path | Mean Latency | Memory Footprint | Storage Persistence | Security Boundary |
| --- | --- | --- | --- | --- |
| **In-Process RFC 6238** | **0.04 ms** | < 12 KB (ephemeral) | None (in-memory) | Process isolation |
| **Session Agent IPC (UDS)** | **0.85 ms** | < 1.2 MB RSS | None (socket) | Mode 0600 socket |
| **Hardware TPM 2.0 (`totpm`)** | **12.1 ms** | External hardware | Sealed to PCRs | Silicon hardware |
| **GPG `pass-otp`** | **18.5 ms** | `gpg-agent` memory | GPG encrypted files | Private GPG key |
| **1Password CLI (`op`)** | **285 ms** | App IPC boundary | Encrypted SQLite | Biometric / App unlock |

---

## Features

- **Multi-Backend Architecture**: Seamlessly query or switch between 1Password, `pass-otp`, TPM 2.0 (`totpm`), and YubiKey.
- **Modern Textual TUI**: Interactive full-screen terminal interface with live visual countdown progress bars, profile switching, item detail inspector, and searchable token tables.
- **Fail-Closed Security**: File modes enforced at 0600, parent directories at 0700, and zero sensitive state in process memory or error stack traces.
- **Ephemeral Session Daemon**: Background systemd user service and socket activation (`authy-local-agent.service`) with configurable idle auto-lock (default: 900 seconds).
- **Clipboard Scrubber**: High-reliability clipboard scrubber supporting Wayland (`wl-copy`), X11 (`xclip`), and macOS (`pbcopy`) with automatic 30-second memory wipes.
- **Terminal QR Rendering**: Inspect or cross-enroll tokens via high-contrast UTF-8/ANSI terminal QR codes directly inside the CLI or TUI (`otp-local qr <account>`).
- **Comprehensive Doctor**: Non-authenticating diagnostic tool (`otp-local doctor`) evaluating platform tools, system clock synchronization, GPG agents, TPM devices, and IPC health.
- **Security Auditor**: Detect identical shared secrets, short seed lengths, or unhardened digest parameters (`otp-local audit`).
- **Standardized Importers/Exporters**: Import or export tokens to standard formats (Aegis JSON, 2FAS, Bitwarden, Google Authenticator URI) with optional GPG recipient encryption.

---

## Cross-Platform Installation

### Linux (Arch Linux, Fedora, Ubuntu, Debian)

```sh
# Install system prerequisites (optional for full capability)
sudo apt-get install -y qrencode fzf wl-clipboard  # Debian/Ubuntu
# sudo pacman -S qrencode fzf wl-clipboard        # Arch Linux

# Install via pip
pip install authy-local

# Run health diagnostics
otp-local doctor
```

### macOS

```sh
# Install prerequisites via Homebrew
brew install qrencode fzf 1password-cli

# Install via pip
pip install authy-local

# Run health diagnostics
otp-local doctor
```

### Windows (WSL2 / PowerShell)

Under Windows, `otp-local` is fully supported via standard Python environments or WSL2:

```powershell
# Install via pip
pip install authy-local

# Run doctor check
otp-local doctor
```

---

## Quick Start CLI Usage

### 1. Run Diagnostic Health Check

```sh
otp-local doctor
```

Validates availability of platform commands, 1Password CLI, GPG agent, Wayland/X11 clipboard, and hardware security modules without requiring authentication.

### 2. Launch the Terminal User Interface (TUI)

```sh
otp-local tui
```

Hotkeys:

- `Enter`: Copy currently focused OTP code to clipboard (arms 30s auto-wiper).
- `v`: View account metadata and parameters modal.
- `q`: Render high-resolution terminal QR code.
- `b`: Switch active backend (1Password, pass-otp, TPM2, YubiKey).
- `/` or `f`: Instant fuzzy filter across accounts and issuers.
- `d`: Run doctor capability assessment panel.
- `Esc` / `Ctrl+C`: Gracefully exit and wipe in-memory secrets.

### 3. Generate or Copy Tokens from the Command Line

```sh
# Display token directly in terminal
otp-local show "GitHub"

# Copy token to system clipboard with 30s auto-wipe
otp-local copy "Amazon Web Services"

# Interactive fuzzy search and selection
otp-local select
```

### 4. Ephemeral Session Agent

Start or inspect the local session daemon for fast token acquisition:

```sh
# Start ephemeral daemon with 15-minute timeout
otp-local agent start --timeout 900

# Query daemon status
otp-local agent status

# Terminate session daemon and zeroize cache
otp-local agent stop
```

---

## Developer Quick Start

To set up an isolated development environment:

```sh
# Clone repository
git clone https://github.com/doublegate/OTP-Local_CLI.git
cd OTP-Local_CLI

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install development and testing dependencies
pip install -r requirements-dev.txt
pip install --no-build-isolation --no-deps -e .
npm ci --ignore-scripts

# Verify test suite and quality gates
python scripts/bundle_guides.py
python scripts/check_docs.py
ruff check src tests scripts
ruff format --check src tests scripts
npx markdownlint-cli2
pytest tests -v
python scripts/smoke_package.py
```

---

## Documentation Index

- [Project Status & Decisions](PROJECT-STATUS.md)
- [Architecture & Contract Specification](docs/03-cli-specification.md)
- [Textual TUI Guide & Shortcuts](docs/11-tui.md)
- [Desktop Integration & Systemd Units](docs/13-desktop-integration.md)
- [Security Model & Threat Boundaries](SECURITY.md)
- [Optional Hardware & TPM Setup](docs/2026-10-12-optional-setup.md)
- [Contributing Guidelines](CONTRIBUTING.md)
- [Release Changelog](CHANGELOG.md)

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
