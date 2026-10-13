"""Extensible plugin engine package for OTP-Local (Phase 12 / Sprint 12.2)."""

from .manager import PluginManager, get_plugin_manager
from .specs import OtpLocalPluginSpec, hookimpl, hookspec

__all__ = [
    "PluginManager",
    "get_plugin_manager",
    "OtpLocalPluginSpec",
    "hookimpl",
    "hookspec",
]
