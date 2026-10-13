"""Unit and integration tests for Extensible Plugin Engine (Phase 12 / Sprint 12.2)."""

import tempfile
import unittest

from authy_local.async_core import AsyncBackend, AsyncFederatedResolver, TotpResult, VaultItem
from authy_local.auditor import AuditFinding
from authy_local.enrollment import OtpParameters
from authy_local.plugins import PluginManager, get_plugin_manager, hookimpl


class SampleBackendPlugin:
    """Mock plugin implementing a custom async storage backend."""

    class CustomStorageBackend(AsyncBackend):
        def __init__(self):
            super().__init__(name="custom_cloud")

        async def is_available(self) -> bool:
            return True

        async def list_items(self) -> list[VaultItem]:
            return [VaultItem(id="c1", label="CustomService", backend="custom_cloud")]

        async def get_totp(self, query: str) -> TotpResult | None:
            if query == "CustomService":
                return TotpResult(code="999888", remaining=30, backend="custom_cloud")
            return None

        async def enroll(self, account: str, secret: str, **kwargs) -> bool:
            return True

    @hookimpl
    def otp_local_register_backend(self):
        return self.CustomStorageBackend()


class SampleNotificationPlugin:
    """Mock plugin capturing token generation events."""

    def __init__(self):
        self.events = []

    @hookimpl
    def otp_local_on_token_generated(
        self, account: str, issuer: str, backend: str, timestamp: float
    ):
        self.events.append(
            {"account": account, "issuer": issuer, "backend": backend, "timestamp": timestamp}
        )


class SampleAuditRulePlugin:
    """Mock plugin evaluating custom security audit rules."""

    @hookimpl
    def otp_local_audit_rule(self, tokens: list[OtpParameters], env: dict[str, str]):
        findings = []
        for t in tokens:
            if "legacy" in t.account.lower():
                findings.append(
                    AuditFinding(
                        rule_id="CUSTOM-001",
                        severity="MEDIUM",
                        title="Legacy Account Detected",
                        accounts=[t.account],
                        description="Account contains legacy naming convention",
                        recommendation="Migrate to standardized naming scheme",
                    )
                )
        return findings


class SampleUiActionPlugin:
    """Mock plugin executing custom UI actions."""

    @hookimpl
    def otp_local_custom_ui_action(self, context: dict):
        return {"action": "export_telemetry", "count": context.get("token_count", 0)}


class TestPluginSystem(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pm = PluginManager()

    def test_register_and_unregister_plugin(self):
        plugin = SampleNotificationPlugin()
        self.assertFalse(self.pm.is_registered(plugin))
        self.pm.register(plugin, name="notif_test")
        self.assertTrue(self.pm.is_registered(plugin))
        self.pm.unregister(plugin)
        self.assertFalse(self.pm.is_registered(plugin))

    async def test_custom_backend_plugin_integration(self):
        plugin = SampleBackendPlugin()
        self.pm.register(plugin)

        backends = self.pm.get_registered_backends()
        self.assertEqual(len(backends), 1)
        self.assertEqual(backends[0].name, "custom_cloud")

        resolver = AsyncFederatedResolver(backends=backends)
        items = await resolver.search(query="")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].label, "CustomService")

        code = await resolver.retrieve_code("CustomService")
        self.assertIsNotNone(code)
        self.assertEqual(code.code, "999888")

    def test_notification_hook_broadcast(self):
        plugin = SampleNotificationPlugin()
        self.pm.register(plugin)

        self.pm.notify_token_generated(account="alice@example.com", issuer="AWS", backend="fido2")
        self.assertEqual(len(plugin.events), 1)
        ev = plugin.events[0]
        self.assertEqual(ev["account"], "alice@example.com")
        self.assertEqual(ev["issuer"], "AWS")
        self.assertEqual(ev["backend"], "fido2")

    def test_custom_audit_rule_plugin(self):
        plugin = SampleAuditRulePlugin()
        self.pm.register(plugin)

        tokens = [
            OtpParameters(secret="JBSWY3DPEHPK3PXY", account="legacy_admin@corp.com"),
            OtpParameters(secret="KRSXG5CTMVRXEZLU", account="regular_user@corp.com"),
        ]
        findings = self.pm.run_custom_audit_rules(tokens)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "CUSTOM-001")
        self.assertEqual(findings[0].accounts, ["legacy_admin@corp.com"])

    def test_custom_ui_action_plugin(self):
        plugin = SampleUiActionPlugin()
        self.pm.register(plugin)

        results = self.pm.run_custom_actions({"token_count": 42})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action"], "export_telemetry")
        self.assertEqual(results[0]["count"], 42)

    def test_plugin_configuration_allowlist(self):
        with tempfile.TemporaryDirectory() as td:
            env = {"XDG_CONFIG_HOME": td}
            pm = PluginManager(env=env)
            self.assertEqual(len(pm._enabled_plugins), 0)

            pm.save_config(["trusted_plugin_1", "trusted_plugin_2"])
            self.assertIn("trusted_plugin_1", pm._enabled_plugins)
            self.assertIn("trusted_plugin_2", pm._enabled_plugins)

            # Reload from disk
            pm2 = PluginManager(env=env)
            self.assertEqual(pm2._enabled_plugins, {"trusted_plugin_1", "trusted_plugin_2"})

    def test_global_plugin_manager_singleton(self):
        inst1 = get_plugin_manager()
        inst2 = get_plugin_manager()
        self.assertIs(inst1, inst2)
        inst3 = get_plugin_manager(reset=True)
        self.assertIsNot(inst1, inst3)


if __name__ == "__main__":
    unittest.main()
