"""Unit, concurrency, and protocol tests for Async Core (Phase 12 / Sprint 12.1)."""

import asyncio
import tempfile
import time
import unittest

from authy_local.async_core import (
    METHOD_NOT_FOUND,
    AsyncFederatedResolver,
    AsyncJsonRpcClient,
    AsyncJsonRpcServer,
    AsyncMockBackend,
    AsyncSyncAdapter,
    TotpResult,
    VaultItem,
    async_recv_framed,
    async_send_framed,
)


class TestAsyncDataModels(unittest.TestCase):
    def test_totp_result_and_vault_item(self):
        res = TotpResult(code="123456", remaining=25, backend="mock", issuer="GitHub")
        d = res.to_dict()
        self.assertEqual(d["code"], "123456")
        self.assertEqual(d["remaining"], 25)
        self.assertEqual(d["backend"], "mock")

        item = VaultItem(id="1", label="GitHub (alice)", backend="mock", origin_badge="[1P]")
        it_dict = item.to_dict()
        self.assertEqual(it_dict["label"], "GitHub (alice)")
        self.assertEqual(it_dict["origin_badge"], "[1P]")


class TestAsyncBackends(unittest.IsolatedAsyncioTestCase):
    async def test_async_mock_backend_operations(self):
        backend = AsyncMockBackend(
            name="onepassword",
            tokens={"GitHub": "JBSWY3DPEHPK3PXP", "AWS": "KRSXG5CTMVRXEZLU"},
        )
        self.assertTrue(await backend.is_available())
        items = await backend.list_items()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].backend, "onepassword")

        code_res = await backend.get_totp("GitHub")
        self.assertIsNotNone(code_res)
        self.assertEqual(len(code_res.code), 6)
        self.assertEqual(code_res.backend, "onepassword")

        # Missing token
        missing = await backend.get_totp("NonExistent")
        self.assertIsNone(missing)

        # Enroll new token
        enrolled = await backend.enroll("GitLab", "MZXW6YTBOI======")
        self.assertTrue(enrolled)
        self.assertIn("GitLab", backend.tokens)

    async def test_async_sync_adapter(self):
        def sync_available(env):
            return True

        def sync_list(config, env):
            return ["Item1", "Item2"]

        def sync_code(query, config, env):
            if query == "Item1":
                return "654321"
            return None

        adapter = AsyncSyncAdapter(
            name="pass-otp",
            check_available_fn=sync_available,
            list_fn=sync_list,
            code_fn=sync_code,
        )

        self.assertTrue(await adapter.is_available())
        items = await adapter.list_items()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].label, "Item1")

        res = await adapter.get_totp("Item1")
        self.assertIsNotNone(res)
        self.assertEqual(res.code, "654321")

        none_res = await adapter.get_totp("ItemUnknown")
        self.assertIsNone(none_res)


class TestAsyncFederatedResolver(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_multi_vault_search_and_deduplication(self):
        b1 = AsyncMockBackend(
            name="onepassword",
            tokens={"GitHub": "JBSWY3DPEHPK3PXP", "AWS": "KRSXG5CTMVRXEZLU"},
        )
        b2 = AsyncMockBackend(
            name="bitwarden",
            tokens={"GitHub": "JBSWY3DPEHPK3PXP", "DigitalOcean": "NBSWY3DPEHPK3PXY"},
        )
        b3 = AsyncMockBackend(
            name="keepass",
            tokens={"Hetzner": "MZXW6YTBOI======"},
        )

        resolver = AsyncFederatedResolver(backends=[b1, b2, b3])
        items = await resolver.search(query="", timeout=2.0)

        # Unique labels: AWS, DigitalOcean, GitHub, Hetzner
        labels = [it.label for it in items]
        self.assertEqual(labels, ["AWS", "DigitalOcean", "GitHub", "Hetzner"])

        # Check composite origin badge for GitHub (in both 1P and BW)
        github_item = next(it for it in items if it.label == "GitHub")
        self.assertEqual(github_item.origin_badge, "[1P+BW]")

        # Hetzner should only have KeePass badge
        hetzner_item = next(it for it in items if it.label == "Hetzner")
        self.assertEqual(hetzner_item.origin_badge, "[KP]")

    async def test_slow_backend_timeout_does_not_block_fast_backends(self):
        fast_backend = AsyncMockBackend(
            name="fast_tpm",
            tokens={"FastService": "JBSWY3DPEHPK3PXP"},
            latency=0.01,
        )
        slow_backend = AsyncMockBackend(
            name="slow_remote",
            tokens={"SlowService": "KRSXG5CTMVRXEZLU"},
            latency=2.0,  # Deliberately slow
        )

        resolver = AsyncFederatedResolver(backends=[fast_backend, slow_backend])

        t0 = time.monotonic()
        # Bound search timeout to 0.2 seconds
        items = await resolver.search(query="", timeout=0.2)
        elapsed = time.monotonic() - t0

        self.assertLess(elapsed, 0.8)
        # Fast backend should have succeeded
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].label, "FastService")

    async def test_concurrent_retrieve_code(self):
        b1 = AsyncMockBackend(
            name="onepassword",
            tokens={"GitHub": "JBSWY3DPEHPK3PXP"},
        )
        b2 = AsyncMockBackend(
            name="bitwarden",
            tokens={"AWS": "KRSXG5CTMVRXEZLU"},
        )
        resolver = AsyncFederatedResolver(backends=[b1, b2])

        res = await resolver.retrieve_code("AWS")
        self.assertIsNotNone(res)
        self.assertEqual(len(res.code), 6)
        self.assertEqual(res.backend, "bitwarden")


class TestJsonRpcStreamingProtocol(unittest.IsolatedAsyncioTestCase):
    async def test_json_rpc_over_tcp(self):
        b = AsyncMockBackend(
            name="mock_store",
            tokens={"GitHub": "JBSWY3DPEHPK3PXP"},
        )
        resolver = AsyncFederatedResolver(backends=[b])
        server = AsyncJsonRpcServer(resolver=resolver, encoding="json")

        # Find an open port
        await server.start(port=0)
        sock = server._server.sockets[0]
        port = sock.getsockname()[1]

        client = AsyncJsonRpcClient(encoding="json")
        await client.connect_tcp("127.0.0.1", port)

        try:
            # 1. Test health check
            health = await client.call("health")
            self.assertEqual(health["status"], "healthy")
            self.assertEqual(health["backends_count"], 1)

            # 2. Test search
            items = await client.call("search", {"query": "Git"})
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["label"], "GitHub")

            # 3. Test get_totp
            code_res = await client.call("get_totp", {"query": "GitHub"})
            self.assertIsNotNone(code_res)
            self.assertEqual(len(code_res["code"]), 6)

            # 4. Test method not found error
            with self.assertRaises(RuntimeError) as cm:
                await client.call("unknown_method_xyz")
            self.assertIn(str(METHOD_NOT_FOUND), str(cm.exception))

        finally:
            await client.close()
            await server.stop()

    async def test_json_rpc_over_unix_socket_and_notifications(self):
        with tempfile.NamedTemporaryFile(delete=True) as tf:
            sock_path = tf.name

        server = AsyncJsonRpcServer(encoding="json")
        await server.start(path=sock_path)

        client = AsyncJsonRpcClient(encoding="json")
        await client.connect_unix(sock_path)

        notifications_received = []

        def on_notification(data):
            notifications_received.append(data)

        client.on_notification("vault_updated", on_notification)

        try:
            # Health check request
            res = await client.call("health")
            self.assertEqual(res["status"], "healthy")

            # Server broadcasts a notification
            await server.broadcast_notification("vault_updated", {"change": "token_added"})

            # Make a round-trip call to trigger notification processing
            await client.call("health")

            self.assertEqual(len(notifications_received), 1)
            self.assertEqual(notifications_received[0]["change"], "token_added")

        finally:
            await client.close()
            await server.stop()

    async def test_framed_message_cbor_roundtrip(self):
        # Test low level streaming framing with CBOR
        class DummyStream:
            def __init__(self):
                self.buf = bytearray()

            def write(self, data):
                self.buf.extend(data)

            async def drain(self):
                pass

            async def readexactly(self, n):
                if len(self.buf) < n:
                    raise asyncio.IncompleteReadError(bytes(self.buf), n)
                data = self.buf[:n]
                self.buf = self.buf[n:]
                return bytes(data)

        stream = DummyStream()
        msg = {"jsonrpc": "2.0", "id": 42, "method": "test", "params": {"key": "value"}}

        await async_send_framed(stream, msg, encoding="cbor")
        received = await async_recv_framed(stream, encoding="cbor")

        self.assertEqual(received, msg)


class TestConcurrencyBenchmark(unittest.IsolatedAsyncioTestCase):
    async def test_async_concurrency_speedup(self):
        # Create 5 backends, each with simulated 0.05s I/O latency
        backends = [
            AsyncMockBackend(
                name=f"vault_{i}", tokens={f"token_{i}": "JBSWY3DPEHPK3PXP"}, latency=0.05
            )
            for i in range(5)
        ]
        resolver = AsyncFederatedResolver(backends=backends)

        t0 = time.monotonic()
        items = await resolver.search(query="")
        concurrent_time = time.monotonic() - t0

        self.assertEqual(len(items), 5)
        # Sequential time would be ~0.25s. Concurrent should be < 0.12s
        self.assertLess(concurrent_time, 0.18)


if __name__ == "__main__":
    unittest.main()
