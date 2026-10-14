"""Universal Non-Blocking Asynchronous Core Architecture (Phase 12 / Sprint 12.1).

Provides non-blocking backend queries, concurrent multi-vault searches, and a
streaming JSON-RPC 2.0 / CBOR socket protocol.
"""

import abc
import asyncio
import json
import os
import struct
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Coroutine

from .enrollment import OtpParameters, generate_totp_code
from .ipc import (
    MAX_IPC_MESSAGE_SIZE,
    decode_cbor,
    encode_cbor,
)
from .ipc import (
    socket_path as default_socket_path,
)

# Standard JSON-RPC 2.0 Error Codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
BACKEND_TIMEOUT = -32000
BACKEND_UNAVAILABLE = -32001


@dataclass
class TotpResult:
    """Represents a computed or retrieved TOTP code with time-to-live metadata."""

    code: str
    period: int = 30
    remaining: int = 30
    issuer: str = ""
    account: str = ""
    backend: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VaultItem:
    """Represents an item or credential reference within a vault backend."""

    id: str
    label: str
    account: str = ""
    issuer: str = ""
    backend: str = ""
    origin_badge: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AsyncBackend(abc.ABC):
    """Abstract base class for asynchronous credential store backends."""

    def __init__(
        self,
        name: str,
        config: dict[str, Any] | None = None,
        env: dict[str, str] | None = None,
    ):
        self.name = name
        self.config = config or {}
        self.env = env or dict(os.environ)

    @abc.abstractmethod
    async def is_available(self) -> bool:
        """Asynchronously determine if the backend and tools are operational."""
        ...

    @abc.abstractmethod
    async def list_items(self) -> list[VaultItem]:
        """Asynchronously list or stream stored vault credentials."""
        ...

    @abc.abstractmethod
    async def get_totp(self, query: str) -> TotpResult | None:
        """Asynchronously compute or retrieve a TOTP code matching query."""
        ...

    @abc.abstractmethod
    async def enroll(self, account: str, secret: str, **kwargs: Any) -> bool:
        """Asynchronously enroll a new OTP credential."""
        ...


class AsyncSyncAdapter(AsyncBackend):
    """Generic adapter that wraps synchronous backend implementations via asyncio.to_thread."""

    def __init__(
        self,
        name: str,
        check_available_fn: Callable[..., bool] | None = None,
        list_fn: Callable[..., list[str]] | None = None,
        code_fn: Callable[..., str | None] | None = None,
        enroll_fn: Callable[..., Any] | None = None,
        config: dict[str, Any] | None = None,
        env: dict[str, str] | None = None,
    ):
        super().__init__(name=name, config=config, env=env)
        self._check_available_fn = check_available_fn
        self._list_fn = list_fn
        self._code_fn = code_fn
        self._enroll_fn = enroll_fn

    async def is_available(self) -> bool:
        if not self._check_available_fn:
            return True
        try:
            return await asyncio.to_thread(self._check_available_fn, self.env)
        except Exception:
            return False

    async def list_items(self) -> list[VaultItem]:
        if not self._list_fn:
            return []
        try:
            raw_labels = await asyncio.to_thread(self._list_fn, self.config, self.env)
            items = []
            for label in raw_labels:
                items.append(
                    VaultItem(
                        id=label,
                        label=label,
                        backend=self.name,
                    )
                )
            return items
        except Exception:
            return []

    async def get_totp(self, query: str) -> TotpResult | None:
        if not self._code_fn:
            return None
        try:
            code = await asyncio.to_thread(self._code_fn, query, self.config, self.env)
            if not code:
                return None
            now = int(time.time())
            period = 30
            remaining = period - (now % period)
            return TotpResult(
                code=code,
                period=period,
                remaining=remaining,
                backend=self.name,
            )
        except Exception:
            return None

    async def enroll(self, account: str, secret: str, **kwargs: Any) -> bool:
        if not self._enroll_fn:
            return False
        try:
            await asyncio.to_thread(self._enroll_fn, account, secret, self.env, **kwargs)
            return True
        except Exception:
            return False


class AsyncMockBackend(AsyncBackend):
    """In-memory mock asynchronous backend for unit testing and benchmarks."""

    def __init__(
        self,
        name: str = "mock",
        tokens: dict[str, str] | None = None,
        latency: float = 0.0,
        available: bool = True,
    ):
        super().__init__(name=name)
        self.tokens: dict[str, str] = tokens or {}
        self.latency = latency
        self.available = available

    async def is_available(self) -> bool:
        if self.latency > 0:
            await asyncio.sleep(self.latency)
        return self.available

    async def list_items(self) -> list[VaultItem]:
        if self.latency > 0:
            await asyncio.sleep(self.latency)
        if not self.available:
            raise RuntimeError(f"Backend {self.name} is offline")
        return [
            VaultItem(
                id=label,
                label=label,
                backend=self.name,
            )
            for label in self.tokens.keys()
        ]

    async def get_totp(self, query: str) -> TotpResult | None:
        if self.latency > 0:
            await asyncio.sleep(self.latency)
        if not self.available:
            raise RuntimeError(f"Backend {self.name} is offline")
        for label, secret in self.tokens.items():
            if query.lower() in label.lower():
                params = OtpParameters(secret=secret)
                code, rem = generate_totp_code(params)
                return TotpResult(
                    code=code,
                    period=30,
                    remaining=int(rem),
                    issuer=label,
                    backend=self.name,
                )
        return None

    async def enroll(self, account: str, secret: str, **kwargs: Any) -> bool:
        if self.latency > 0:
            await asyncio.sleep(self.latency)
        self.tokens[account] = secret
        return True


class AsyncFederatedResolver:
    """High-performance concurrent multi-vault resolver utilizing non-blocking asyncio.gather."""

    ORIGIN_BADGES = {
        "onepassword": "[1P]",
        "bitwarden": "[BW]",
        "keepass": "[KP]",
        "pass-otp": "[GPG]",
        "totpm": "[TPM]",
        "keychain": "[KEYCHAIN]",
        "fido2": "[FIDO2]",
        "dpapi": "[DPAPI]",
    }

    def __init__(
        self,
        backends: list[AsyncBackend] | None = None,
        env: dict[str, str] | None = None,
    ):
        self.backends: list[AsyncBackend] = backends or []
        self.env: dict[str, str] = env or dict(os.environ)

    def add_backend(self, backend: AsyncBackend) -> None:
        self.backends.append(backend)

    async def search(self, query: str = "", timeout: float = 5.0) -> list[VaultItem]:
        """Concurrently query all available backends, deduplicating and badging entries."""
        if not self.backends:
            return []

        async def _query_backend(b: AsyncBackend) -> tuple[str, list[VaultItem]]:
            try:
                avail = await asyncio.wait_for(b.is_available(), timeout=timeout)
                if not avail:
                    return b.name, []
                items = await asyncio.wait_for(b.list_items(), timeout=timeout)
                return b.name, items
            except Exception:
                return b.name, []

        tasks = [_query_backend(b) for b in self.backends]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate and deduplicate
        label_to_backends: dict[str, list[str]] = {}
        for r in results:
            if isinstance(r, tuple):
                b_name, items = r
                for it in items:
                    norm = it.label.strip()
                    if norm not in label_to_backends:
                        label_to_backends[norm] = []
                    if b_name not in label_to_backends[norm]:
                        label_to_backends[norm].append(b_name)

        q_lower = query.lower()
        aggregated: list[VaultItem] = []
        for label, b_names in sorted(label_to_backends.items()):
            if q_lower and q_lower not in label.lower():
                continue

            # Composite origin badge
            badges = [self.ORIGIN_BADGES.get(b, f"[{b.upper()}]") for b in b_names]
            badge_str = "+".join(b.strip("[]") for b in badges)
            composite_badge = f"[{badge_str}]"

            primary_backend = b_names[0]
            aggregated.append(
                VaultItem(
                    id=label,
                    label=label,
                    backend=primary_backend,
                    origin_badge=composite_badge,
                )
            )

        return aggregated

    async def retrieve_code(self, label: str, timeout: float = 5.0) -> TotpResult | None:
        """Asynchronously query backends concurrently to retrieve the first valid TOTP code."""
        if not self.backends:
            return None

        async def _get(b: AsyncBackend) -> TotpResult | None:
            try:
                return await asyncio.wait_for(b.get_totp(label), timeout=timeout)
            except Exception:
                return None

        tasks = [asyncio.create_task(_get(b)) for b in self.backends]
        try:
            for fut in asyncio.as_completed(tasks):
                try:
                    res = await fut
                    if isinstance(res, TotpResult) and res.code:
                        for t in tasks:
                            if not t.done():
                                t.cancel()
                        return res
                except Exception:
                    pass
            return None
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()


# --- Asynchronous Framing and JSON-RPC 2.0 Streaming Protocol ---


async def async_send_framed(
    writer: asyncio.StreamWriter,
    data: dict[str, Any],
    encoding: str = "json",
) -> None:
    """Asynchronously serialize and transmit 4-byte big-endian length-prefixed message."""
    if encoding == "cbor":
        payload = encode_cbor(data)
    else:
        payload = json.dumps(data).encode("utf-8")

    if len(payload) > MAX_IPC_MESSAGE_SIZE:
        raise ValueError(f"Payload size {len(payload)} exceeds maximum {MAX_IPC_MESSAGE_SIZE}")

    header = struct.pack(">I", len(payload))
    writer.write(header + payload)
    await writer.drain()


async def async_recv_framed(
    reader: asyncio.StreamReader,
    encoding: str = "json",
    max_bytes: int = MAX_IPC_MESSAGE_SIZE,
) -> dict[str, Any] | None:
    """Asynchronously read 4-byte big-endian length-prefixed message."""
    try:
        header = await reader.readexactly(4)
    except asyncio.IncompleteReadError, ConnectionResetError:
        return None

    (msg_len,) = struct.unpack(">I", header)
    if msg_len == 0 or msg_len > max_bytes:
        raise ValueError(f"Invalid message length: {msg_len}")

    try:
        payload = await reader.readexactly(msg_len)
    except asyncio.IncompleteReadError, ConnectionResetError:
        return None

    if encoding == "cbor":
        return decode_cbor(payload)
    return json.loads(payload.decode("utf-8"))


class AsyncJsonRpcServer:
    """Streaming asynchronous JSON-RPC 2.0 / CBOR server supporting bi-directional notifications."""

    def __init__(
        self,
        resolver: AsyncFederatedResolver | None = None,
        encoding: str = "json",
    ):
        self.resolver = resolver or AsyncFederatedResolver()
        self.encoding = encoding
        self._server: asyncio.Server | None = None
        self._active_clients: set[asyncio.StreamWriter] = set()
        self._handlers: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {
            "health": self._handle_health,
            "search": self._handle_search,
            "get_totp": self._handle_get_totp,
            "list_items": self._handle_list_items,
        }

    def register_method(
        self,
        name: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
    ) -> None:
        self._handlers[name] = handler

    async def _handle_health(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "healthy",
            "backends_count": len(self.resolver.backends),
            "timestamp": int(time.time()),
        }

    async def _handle_search(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        query = params.get("query", "")
        timeout = float(params.get("timeout", 5.0))
        items = await self.resolver.search(query=query, timeout=timeout)
        return [it.to_dict() for it in items]

    async def _handle_get_totp(self, params: dict[str, Any]) -> dict[str, Any] | None:
        query = params.get("query", "")
        timeout = float(params.get("timeout", 5.0))
        res = await self.resolver.retrieve_code(label=query, timeout=timeout)
        return res.to_dict() if res else None

    async def _handle_list_items(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        items = await self.resolver.search(query="", timeout=5.0)
        return [it.to_dict() for it in items]

    async def handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._active_clients.add(writer)
        try:
            while True:
                msg = await async_recv_framed(reader, encoding=self.encoding)
                if msg is None:
                    break

                # Process JSON-RPC 2.0 message
                req_id = msg.get("id")
                method = msg.get("method")
                params = msg.get("params", {})

                # Check if it's a notification (no id)
                is_notification = req_id is None

                if not method or not isinstance(method, str):
                    if not is_notification:
                        await async_send_framed(
                            writer,
                            {
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "error": {
                                    "code": INVALID_REQUEST,
                                    "message": "Invalid Request: missing method",
                                },
                            },
                            encoding=self.encoding,
                        )
                    continue

                handler = self._handlers.get(method)
                if not handler:
                    if not is_notification:
                        await async_send_framed(
                            writer,
                            {
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "error": {
                                    "code": METHOD_NOT_FOUND,
                                    "message": f"Method not found: {method}",
                                },
                            },
                            encoding=self.encoding,
                        )
                    continue

                try:
                    result = await handler(params)
                    if not is_notification:
                        await async_send_framed(
                            writer,
                            {
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "result": result,
                            },
                            encoding=self.encoding,
                        )
                except Exception as ex:
                    if not is_notification:
                        await async_send_framed(
                            writer,
                            {
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "error": {
                                    "code": INTERNAL_ERROR,
                                    "message": str(ex),
                                },
                            },
                            encoding=self.encoding,
                        )
        finally:
            self._active_clients.discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def broadcast_notification(self, method: str, params: dict[str, Any]) -> None:
        """Broadcast an asynchronous notification to all connected clients."""
        notif = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        for client in list(self._active_clients):
            try:
                await async_send_framed(client, notif, encoding=self.encoding)
            except Exception:
                self._active_clients.discard(client)

    async def start(self, path: str | None = None, port: int | None = None) -> None:
        if port is not None:
            self._server = await asyncio.start_server(
                self.handle_client, host="127.0.0.1", port=port
            )
        else:
            p = path or str(default_socket_path())
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass
            self._server = await asyncio.start_unix_server(self.handle_client, path=p)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        for client in list(self._active_clients):
            try:
                client.close()
                await client.wait_closed()
            except Exception:
                pass
        self._active_clients.clear()


class AsyncJsonRpcClient:
    """Asynchronous client for interacting with AsyncJsonRpcServer."""

    def __init__(self, encoding: str = "json"):
        self.encoding = encoding
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._seq = 0
        self._notification_handlers: dict[str, list[Callable[[dict[str, Any]], Any]]] = {}

    def on_notification(
        self,
        method: str,
        handler: Callable[[dict[str, Any]], Any],
    ) -> None:
        if method not in self._notification_handlers:
            self._notification_handlers[method] = []
        self._notification_handlers[method].append(handler)

    async def connect_unix(self, path: str) -> None:
        self._reader, self._writer = await asyncio.open_unix_connection(path)

    async def connect_tcp(self, host: str, port: int) -> None:
        self._reader, self._writer = await asyncio.open_connection(host, port)

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = 5.0,
    ) -> Any:
        if not self._writer or not self._reader:
            raise ConnectionError("Client is not connected")

        self._seq += 1
        req_id = self._seq
        req = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }

        await async_send_framed(self._writer, req, encoding=self.encoding)

        # Read response, handling any intermediate notifications
        while True:
            resp = await asyncio.wait_for(
                async_recv_framed(self._reader, encoding=self.encoding),
                timeout=timeout,
            )
            if resp is None:
                raise ConnectionResetError("Connection closed while awaiting response")

            if resp.get("id") == req_id:
                if "error" in resp:
                    err = resp["error"]
                    raise RuntimeError(f"JSON-RPC Error {err.get('code')}: {err.get('message')}")
                return resp.get("result")

            # Check if this was a notification
            if "method" in resp and "id" not in resp:
                notif_method = resp["method"]
                handlers = self._notification_handlers.get(notif_method, [])
                for h in handlers:
                    try:
                        res = h(resp.get("params", {}))
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception:
                        pass

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        if not self._writer:
            raise ConnectionError("Client is not connected")
        notif = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        await async_send_framed(self._writer, notif, encoding=self.encoding)

    async def close(self) -> None:
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._writer = None
        self._reader = None
