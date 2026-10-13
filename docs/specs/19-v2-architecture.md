# Universal Async Architecture and Extensible Plugin Engine Specification

Status: Planned for release v2.0.0.
Extends [Architecture](02-architecture.md), [CLI Specification](03-cli-specification.md), and [Desktop Integration](13-desktop-integration.md).

## 1. Overview and Requirements

Release v2.0.0 marks the Long-Term Support (LTS) foundation for OTP-Local CLI. This specification details the transition to a non-blocking asynchronous core (`asyncio`), an extensible plugin architecture, and a stable, frozen public Python API.

Key requirements:

1. Universal non-blocking async core for all backend queries, network calls, and UI operations.
2. Extensible plugin engine (`pluggy` based) supporting third-party backends, authenticators, and renderers.
3. Stable public API freeze under `authy_local` with 100% semantic versioning compliance.
4. Backward compatibility adapter maintaining parity for v1.x CLI commands and scripts.
5. High-performance JSON-RPC 2.0 / CBOR streaming protocol over local IPC sockets.

## 2. Universal Async Core Architecture (`src/authy_local/async_core.py`)

### 2.1 Asynchronous Backend Hierarchy

```python
class AsyncBackend(abc.ABC):
    @abc.abstractmethod
    async def get_totp(self, query: str) -> TotpResult:
        """Asynchronously compute or retrieve a TOTP code."""
        ...

    @abc.abstractmethod
    async def list_items(self) -> AsyncIterator[VaultItem]:
        """Asynchronously stream vault items."""
        ...

    @abc.abstractmethod
    async def enroll(self, item: NewOtpItem) -> bool:
        """Asynchronously enroll a new OTP credential."""
        ...
```

### 2.2 Concurrency & Timeout Guarantees

- Concurrent multi-vault queries run via `asyncio.gather(*[b.list_items() for b in backends], return_exceptions=True)`.
- Per-backend timeout bounded at 5.0 seconds; slow or unresponsive backends yield partial results rather than stalling the application.

## 3. Extensible Plugin Hook Engine (`src/authy_local/plugins/`)

### 3.1 Hook Specifications

Using `pluggy`, the plugin manager defines three primary hook categories:

1. `otp_local_register_backend`: Adds new credential stores (e.g. AWS Secrets Manager, HashiCorp Vault, hardware HSMs).
2. `otp_local_on_token_generated`: Notification hook triggered when a TOTP code is copied or displayed (enabling desktop notifications, audit logging, or webhook triggers).
3. `otp_local_custom_ui_action`: Adds custom actions or modals to the Textual TUI dashboard.

### 3.2 Discovery & Security Isolation

- Plugins are discovered via Python standard entry points: `[project.entry-points."authy_local.plugins"]`.
- Safety verification: Plugins must be explicitly enabled in configuration (`~/.config/otp-local/plugins.json`); untrusted third-party plugins cannot execute automatically.

## 4. Public API Freeze & Deprecation Policy

### 4.1 Frozen Namespace (`authy_local`)

The root `authy_local` namespace exposes a frozen public interface:

- `authy_local.get_totp(service: str, account: str | None = None) -> TotpResult`
- `authy_local.list_credentials() -> list[VaultItem]`
- `authy_local.enroll_credential(secret: str, service: str, account: str) -> bool`
- `authy_local.check_health() -> DoctorReport`

### 4.2 Deprecation & Compatibility Shims

- All v1.x synchronous function calls are preserved via synchronous wrappers executing an internal asyncio event loop.
- Deprecated symbols emit `DeprecationWarning` with target removal in v3.0.0.
