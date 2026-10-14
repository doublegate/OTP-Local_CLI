"""OTP-Local CLI: Universal Two-Factor Authentication Terminal Companion and Security Layer.

Frozen Public Python API for v2.0.1 LTS.
"""

from .async_core import (
    AsyncBackend,
    AsyncFederatedResolver,
    AsyncJsonRpcClient,
    AsyncJsonRpcServer,
    AsyncMockBackend,
    AsyncSyncAdapter,
    TotpResult,
    VaultItem,
)
from .auditor import (
    AuditFinding,
    AuditReport,
    audit_tokens,
    calculate_shannon_entropy,
    check_time_drift,
    format_audit_report,
    generate_rotation_advice,
    scan_environment_leaks,
)
from .compat import legacy_copy_code, legacy_list_accounts, legacy_show_code
from .enrollment import OtpParameters, clean_base32, generate_totp_code
from .plugins import (
    OtpLocalPluginSpec,
    PluginManager,
    get_plugin_manager,
    hookimpl,
    hookspec,
)
from .processes import AppError
from .security import (
    SecureBuffer,
    disable_core_dumps,
    lock_process_memory,
    secure_zero,
)

__version__ = "2.0.1"

__all__ = [
    # Version
    "__version__",
    # Async Core Architecture
    "AsyncBackend",
    "AsyncSyncAdapter",
    "AsyncMockBackend",
    "AsyncFederatedResolver",
    "TotpResult",
    "VaultItem",
    "AsyncJsonRpcServer",
    "AsyncJsonRpcClient",
    # Extensible Plugin System
    "PluginManager",
    "get_plugin_manager",
    "OtpLocalPluginSpec",
    "hookimpl",
    "hookspec",
    # Runtime Memory Forensics Hardening
    "SecureBuffer",
    "secure_zero",
    "lock_process_memory",
    "disable_core_dumps",
    # Autonomous Security Auditor v2
    "audit_tokens",
    "calculate_shannon_entropy",
    "check_time_drift",
    "scan_environment_leaks",
    "generate_rotation_advice",
    "format_audit_report",
    "AuditFinding",
    "AuditReport",
    # Core OTP Parameters & Primitives
    "OtpParameters",
    "generate_totp_code",
    "clean_base32",
    "AppError",
    # Backward Compatibility Shims (v1.x)
    "legacy_show_code",
    "legacy_copy_code",
    "legacy_list_accounts",
]
