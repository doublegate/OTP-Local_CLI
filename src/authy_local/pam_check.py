"""Linux PAM integration validator and diagnostic inspection tooling."""

import json
import sys
from pathlib import Path

from .ipc import send_ipc_request, socket_path


def probe_pam_subsystem() -> dict:
    """Assess whether host platform provides Linux PAM headers and libraries."""
    if sys.platform != "linux":
        return {
            "state": "not-applicable",
            "message": "PAM module is only applicable to Linux host systems",
        }

    header_candidates = [
        Path("/usr/include/security/pam_appl.h"),
        Path("/usr/include/security/pam_modules.h"),
    ]
    headers_found = [str(p) for p in header_candidates if p.exists()]

    lib_candidates = [
        Path("/lib/security"),
        Path("/usr/lib/security"),
        Path("/usr/lib64/security"),
        Path("/usr/lib/x86_64-linux-gnu/security"),
        Path("/usr/lib/aarch64-linux-gnu/security"),
    ]
    pam_dirs_found = [str(p) for p in lib_candidates if p.exists() and p.is_dir()]

    if headers_found or pam_dirs_found:
        return {
            "state": "available",
            "headers": headers_found,
            "security_dirs": pam_dirs_found,
        }
    return {
        "state": "missing",
        "message": "No PAM development headers or system security library directories found",
    }


def probe_pam_module_binary(custom_path: Path | str | None = None) -> dict:
    """Locate compiled pam_otp_local.so binary across system and project paths."""
    candidates: list[Path] = []
    if custom_path:
        candidates.append(Path(custom_path))

    system_dirs = [
        Path("/lib/security"),
        Path("/usr/lib/security"),
        Path("/usr/lib64/security"),
        Path("/usr/lib/x86_64-linux-gnu/security"),
        Path("/usr/lib/aarch64-linux-gnu/security"),
    ]
    for d in system_dirs:
        candidates.append(d / "pam_otp_local.so")

    repo_dir = Path(__file__).resolve().parents[2] / "pam" / "pam_otp_local.so"
    candidates.append(repo_dir)

    for cand in candidates:
        if cand.exists() and cand.is_file():
            return {
                "state": "available",
                "path": str(cand),
                "system_installed": any(d in cand.parents for d in system_dirs),
            }

    return {
        "state": "missing",
        "searched_paths": [str(c) for c in candidates],
        "message": "pam_otp_local.so has not been compiled or installed",
    }


def check_daemon_socket(env: dict[str, str] | None = None) -> dict:
    """Check whether local resident daemon socket exists and responds to ping."""
    sock = socket_path(env)
    if not sock.exists():
        return {
            "state": "missing",
            "path": str(sock),
            "message": "Resident daemon UNIX socket does not exist; start with 'otp-local daemon start'",
        }

    try:
        res = send_ipc_request({"action": "ping"}, sock_path=sock, timeout=1.0)
        if res and res.get("status") == "ok":
            return {
                "state": "available",
                "path": str(sock),
                "ping": "ok",
                "version": res.get("version", 1),
            }
        return {
            "state": "degraded",
            "path": str(sock),
            "ping": "unexpected_response",
            "response": res,
        }
    except Exception as exc:
        return {
            "state": "degraded",
            "path": str(sock),
            "ping": "error",
            "error": str(exc),
        }


def inspect_pam_configurations(pam_d_dir: Path | str | None = None) -> dict:
    """Scan /etc/pam.d/ for active configurations referencing pam_otp_local.so."""
    target_dir = Path(pam_d_dir) if pam_d_dir else Path("/etc/pam.d")
    matches: dict[str, list[str]] = {}

    if not target_dir.exists() or not target_dir.is_dir():
        return {
            "state": "missing" if sys.platform == "linux" else "not-applicable",
            "path": str(target_dir),
            "matches": matches,
        }

    try:
        for entry in sorted(target_dir.iterdir()):
            if entry.is_file() and not entry.is_symlink():
                try:
                    content = entry.read_text(encoding="utf-8", errors="replace")
                    matched_lines = [
                        line.strip()
                        for line in content.splitlines()
                        if "pam_otp_local.so" in line and not line.strip().startswith("#")
                    ]
                    if matched_lines:
                        matches[entry.name] = matched_lines
                except PermissionError, OSError:
                    pass
    except PermissionError, OSError:
        pass

    return {
        "state": "available" if matches else "unconfigured",
        "path": str(target_dir),
        "matches": matches,
    }


def generate_pam_snippet(
    service: str = "sudo",
    mode: str = "required",
    options: list[str] | None = None,
) -> str:
    """Generate recommended PAM service configuration snippet."""
    opts_str = f" {' '.join(options)}" if options else ""
    return (
        f"# OTP-Local 2FA integration for {service}\nauth    {mode}    pam_otp_local.so{opts_str}\n"
    )


def validate_pam_config_syntax(lines: list[str]) -> list[str]:
    """Validate PAM configuration syntax and flag common misconfigurations."""
    errors: list[str] = []
    valid_types = {"auth", "account", "session", "password"}
    valid_controls = {
        "required",
        "requisite",
        "sufficient",
        "optional",
        "include",
        "substack",
    }

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            errors.append(f"Line {idx}: Insufficient fields: '{line}'")
            continue

        mod_type, control = parts[0], parts[1]
        if mod_type not in valid_types:
            errors.append(f"Line {idx}: Invalid PAM module type '{mod_type}'")
        if control not in valid_controls and not (
            control.startswith("[") and control.endswith("]")
        ):
            errors.append(f"Line {idx}: Invalid PAM control flag '{control}'")

    return errors


def run_pam_doctor_check(
    env: dict[str, str] | None = None,
    custom_module_path: Path | str | None = None,
    pam_d_dir: Path | str | None = None,
) -> dict:
    """Execute complete PAM integration diagnostic evaluation."""
    subsystem = probe_pam_subsystem()
    binary = probe_pam_module_binary(custom_module_path)
    daemon = check_daemon_socket(env)
    configs = inspect_pam_configurations(pam_d_dir)

    recommendations: list[str] = []
    if subsystem["state"] == "missing":
        recommendations.append(
            "Install PAM development headers via system package manager (e.g. pam-devel or libpam0g-dev)."
        )
    if binary["state"] == "missing":
        recommendations.append(
            "Compile PAM module: 'make -C pam' and copy pam/pam_otp_local.so to /usr/lib/security/."
        )
    if daemon["state"] != "available":
        recommendations.append(
            "Start the resident OTP daemon: 'otp-local daemon start' or install user service."
        )
    if configs["state"] == "unconfigured" and subsystem["state"] == "available":
        recommendations.append(
            "Configure PAM service by adding 'auth required pam_otp_local.so' to /etc/pam.d/sudo."
        )

    return {
        "subsystem": subsystem,
        "binary": binary,
        "daemon": daemon,
        "configurations": configs,
        "recommendations": recommendations,
        "overall_status": (
            "healthy"
            if (
                subsystem["state"] == "available"
                and binary["state"] == "available"
                and daemon["state"] == "available"
            )
            else "action_required"
        ),
    }


def doctor_pam_cli(
    env: dict[str, str] | None = None,
    stdout=None,
    stderr=None,
    as_json: bool = False,
) -> int:
    """CLI handler for otp-local doctor --pam."""
    out = stdout or sys.stdout
    report = run_pam_doctor_check(env)

    if as_json:
        out.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
        return 0 if report["overall_status"] == "healthy" else 3

    out.write("=== OTP-Local Linux PAM Subsystem Diagnostics ===\n\n")

    subsystem = report["subsystem"]
    out.write(f"PAM Subsystem:     {subsystem['state'].upper()}\n")

    binary = report["binary"]
    binary_state = binary["state"].upper()
    binary_path = binary.get("path", "Not installed")
    out.write(f"Module Binary:     {binary_state} ({binary_path})\n")

    daemon = report["daemon"]
    daemon_state = daemon["state"].upper()
    daemon_path = daemon.get("path", "N/A")
    out.write(f"Resident Daemon:   {daemon_state} ({daemon_path})\n")

    configs = report["configurations"]
    config_state = configs["state"].upper()
    out.write(f"PAM Configurations: {config_state}\n")
    if configs.get("matches"):
        for svc, lines in configs["matches"].items():
            for line in lines:
                out.write(f"  - /etc/pam.d/{svc}: {line}\n")
    else:
        out.write("  - No active services currently include pam_otp_local.so\n")

    recs = report.get("recommendations", [])
    if recs:
        out.write("\nRecommendations:\n")
        for rec in recs:
            out.write(f"  * {rec}\n")
    else:
        out.write("\nAll PAM subsystem and daemon requirements are satisfied.\n")

    out.write("\n")
    return 0 if report["overall_status"] == "healthy" else 3
