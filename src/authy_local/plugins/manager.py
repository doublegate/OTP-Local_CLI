"""Plugin manager implementation for OTP-Local (Phase 12 / Sprint 12.2)."""

import importlib.metadata
import json
import os
import time
from pathlib import Path
from typing import Any

import pluggy

from ..async_core import AsyncBackend
from ..auditor import AuditFinding
from ..enrollment import OtpParameters
from .specs import OtpLocalPluginSpec

_GLOBAL_PLUGIN_MANAGER: "PluginManager | None" = None


class PluginManager:
    """Manages discovery, lifecycle, and hook execution for OTP-Local plugins."""

    def __init__(self, env: dict[str, str] | None = None):
        self.env = env or dict(os.environ)
        self.pm = pluggy.PluginManager("otp_local")
        self.pm.add_hookspecs(OtpLocalPluginSpec)
        self._enabled_plugins: set[str] = set()
        self._load_config()

    def _get_config_path(self) -> Path:
        xdg = self.env.get("XDG_CONFIG_HOME")
        if xdg:
            base = Path(xdg)
        else:
            base = Path(self.env.get("HOME", Path.home())) / ".config"
        return base / "authy-local" / "plugins.json"

    def _load_config(self) -> None:
        """Load enabled plugin list from secure configuration file."""
        cfg_path = self._get_config_path()
        if cfg_path.is_file():
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._enabled_plugins = set(data.get("enabled", []))
                    elif isinstance(data, list):
                        self._enabled_plugins = set(data)
            except Exception:
                self._enabled_plugins = set()

    def save_config(self, enabled_plugins: list[str]) -> None:
        """Save enabled plugin list to configuration."""
        cfg_path = self._get_config_path()
        cfg_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump({"enabled": sorted(enabled_plugins)}, f, indent=2)
        self._enabled_plugins = set(enabled_plugins)

    def register(self, plugin: Any, name: str | None = None) -> str:
        """Register a plugin instance or module."""
        return self.pm.register(plugin, name=name)

    def unregister(self, plugin: Any = None, name: str | None = None) -> Any:
        """Unregister a plugin instance or module."""
        return self.pm.unregister(plugin=plugin, name=name)

    def is_registered(self, plugin: Any) -> bool:
        """Return True if plugin is currently registered."""
        return self.pm.is_registered(plugin)

    def discover_and_load(self, allow_all: bool = False) -> list[str]:
        """Discover plugins registered via setuptools entry points 'otp_local.plugins'.

        Unless allow_all is True, only plugins explicitly present in the enabled
        configuration are loaded to ensure fail-closed security.
        """
        loaded = []
        try:
            eps = importlib.metadata.entry_points()
            # Compatible with both dict-like and SelectableGroups entry_points
            if hasattr(eps, "select"):
                plugin_eps = eps.select(group="otp_local.plugins")
            else:
                plugin_eps = eps.get("otp_local.plugins", [])

            for ep in plugin_eps:
                if allow_all or ep.name in self._enabled_plugins:
                    try:
                        plugin_cls = ep.load()
                        inst = plugin_cls() if isinstance(plugin_cls, type) else plugin_cls
                        self.register(inst, name=ep.name)
                        loaded.append(ep.name)
                    except Exception:
                        pass
        except Exception:
            pass
        return loaded

    def get_registered_backends(self) -> list[AsyncBackend]:
        """Collect all AsyncBackend instances provided by registered plugins."""
        backends: list[AsyncBackend] = []
        results = self.pm.hook.otp_local_register_backend()
        for res in results:
            if isinstance(res, list):
                for b in res:
                    if isinstance(b, AsyncBackend):
                        backends.append(b)
            elif isinstance(res, AsyncBackend):
                backends.append(res)
        return backends

    def notify_token_generated(
        self,
        account: str,
        issuer: str = "",
        backend: str = "local",
        timestamp: float | None = None,
    ) -> None:
        """Broadcast token generation event across all active plugins."""
        now = time.time() if timestamp is None else timestamp
        self.pm.hook.otp_local_on_token_generated(
            account=account,
            issuer=issuer,
            backend=backend,
            timestamp=now,
        )

    def run_custom_actions(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        """Execute custom UI or CLI actions across registered plugins."""
        actions: list[dict[str, Any]] = []
        results = self.pm.hook.otp_local_custom_ui_action(context=context)
        for r in results:
            if isinstance(r, dict):
                actions.append(r)
        return actions

    def run_custom_audit_rules(
        self,
        tokens: list[OtpParameters],
        env: dict[str, str] | None = None,
    ) -> list[AuditFinding]:
        """Execute custom audit rules across registered plugins."""
        e = self.env if env is None else env
        findings: list[AuditFinding] = []
        results = self.pm.hook.otp_local_audit_rule(tokens=tokens, env=e)
        for r in results:
            if isinstance(r, list):
                for f in r:
                    if isinstance(f, AuditFinding):
                        findings.append(f)
            elif isinstance(r, AuditFinding):
                findings.append(r)
        return findings


def get_plugin_manager(
    env: dict[str, str] | None = None,
    reset: bool = False,
) -> PluginManager:
    """Return the global PluginManager singleton instance."""
    global _GLOBAL_PLUGIN_MANAGER
    if _GLOBAL_PLUGIN_MANAGER is None or reset:
        _GLOBAL_PLUGIN_MANAGER = PluginManager(env=env)
    return _GLOBAL_PLUGIN_MANAGER
