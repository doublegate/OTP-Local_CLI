"""Pluggy hook specifications for OTP-Local extensible plugin engine (Phase 12 / Sprint 12.2)."""

from typing import Any

import pluggy

from ..async_core import AsyncBackend
from ..auditor import AuditFinding
from ..enrollment import OtpParameters

hookspec = pluggy.HookspecMarker("otp_local")
hookimpl = pluggy.HookimplMarker("otp_local")


class OtpLocalPluginSpec:
    """Plugin hook specifications defining extension points for OTP-Local."""

    @hookspec
    def otp_local_register_backend(self) -> list[AsyncBackend] | AsyncBackend | None:
        """Register one or more custom AsyncBackend credential stores.

        Plugins return an instance or list of AsyncBackend objects that are
        automatically integrated into the AsyncFederatedResolver.
        """
        ...

    @hookspec
    def otp_local_on_token_generated(
        self,
        account: str,
        issuer: str,
        backend: str,
        timestamp: float,
    ) -> None:
        """Invoked whenever a TOTP code is retrieved, copied, or displayed.

        Can be used for desktop notifications, security audit logs, or webhooks.
        """
        ...

    @hookspec
    def otp_local_custom_ui_action(
        self,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Execute a custom UI or terminal action.

        Receives application state in context dictionary and can return action results.
        """
        ...

    @hookspec
    def otp_local_audit_rule(
        self,
        tokens: list[OtpParameters],
        env: dict[str, str],
    ) -> list[AuditFinding] | None:
        """Evaluate custom security, policy, or hygiene audit rules on enrolled tokens."""
        ...
