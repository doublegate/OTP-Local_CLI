"""Non-authenticating capability assessment."""

import platform
import shutil
import sys

from .backends.onepassword import child_environment, probe
from .errors import AppError
from .processes import run


def report(env: dict[str, str]) -> dict:
    result = {
        "platform": {"state": "available" if sys.platform in ("linux", "darwin") else "missing"},
        "python": {
            "state": "available" if sys.version_info[:2] == (3, 14) else "missing",
            "version": platform.python_version(),
        },
        "op": probe(env),
        "authentication": {"state": "unknown"},
        "clock": {"state": "unknown"},
    }
    for name in ("fish", "fzf", "wl-copy", "qrencode"):
        path = shutil.which(name, path=env.get("PATH", ""))
        result[name] = {"state": "available", "path": path} if path else {"state": "missing"}

    if sys.platform == "darwin":
        pbcopy_path = shutil.which("pbcopy", path=env.get("PATH", ""))
        if pbcopy_path:
            result["wl-copy"] = {"state": "available", "path": pbcopy_path}
            result["pbcopy"] = {"state": "available", "path": pbcopy_path}

    pinentry_path = (
        shutil.which("pinentry", path=env.get("PATH", ""))
        or shutil.which("pinentry-curses", path=env.get("PATH", ""))
        or shutil.which("pinentry-gnome3", path=env.get("PATH", ""))
    )
    result["pinentry"] = (
        {"state": "available", "path": pinentry_path} if pinentry_path else {"state": "missing"}
    )

    gpgconf_bin = shutil.which("gpgconf", path=env.get("PATH", ""))
    if gpgconf_bin:
        try:
            obs = run(
                [gpgconf_bin, "--list-dirs", "agent-socket"],
                env=child_environment(env),
                timeout=3,
            )
            if obs.returncode == 0 and obs.stdout.strip():
                result["gpg-agent"] = {
                    "state": "available",
                    "path": obs.stdout.strip().decode("utf-8", errors="replace"),
                }
            else:
                result["gpg-agent"] = {"state": "missing"}
        except AppError:
            result["gpg-agent"] = {"state": "missing"}
    else:
        result["gpg-agent"] = {"state": "missing"}
    from .backends.local import capabilities

    result.update(capabilities(env))
    from .backends.hardware import probe_hardware

    result.update(probe_hardware(env))

    import os
    from pathlib import Path

    tpm_candidate = None
    for dev in ("/dev/tpmrm0", "/dev/tpm0"):
        try:
            if Path(dev).exists():
                tpm_candidate = dev
                break
        except OSError:
            pass
    if tpm_candidate is not None:
        try:
            if os.access(tpm_candidate, os.R_OK | os.W_OK):
                result["tpm-device"] = {"state": "available", "path": tpm_candidate}
            else:
                result["tpm-device"] = {"state": "unknown", "path": tpm_candidate}
        except OSError:
            result["tpm-device"] = {"state": "unknown"}
    else:
        result["tpm-device"] = {"state": "missing"}
    clock = shutil.which("timedatectl", path=env.get("PATH", ""))
    if clock:
        try:
            observed = run(
                [clock, "show", "--property=NTPSynchronized", "--value"],
                env=child_environment(env),
                timeout=5,
                stdout_cap=8192,
                stderr_cap=8192,
            )
            if observed.returncode == 0 and observed.stdout in (b"yes\n", b"no\n"):
                clock_state = "available" if observed.stdout == b"yes\n" else "missing"
                result["clock"] = {"state": clock_state}
                try:
                    sync_obs = run(
                        [clock, "timesync-status"],
                        env=child_environment(env),
                        timeout=5,
                        stdout_cap=8192,
                        stderr_cap=8192,
                    )
                    if sync_obs.returncode == 0 and sync_obs.stdout:
                        import re

                        m = re.search(
                            rb"Offset:\s*([+-]?\d+(?:\.\d+)?\s*(?:us|ms|s))", sync_obs.stdout
                        )
                        if m:
                            result["clock"]["offset"] = m.group(1).decode("ascii")
                except AppError:
                    pass
        except AppError as error:
            if error.exit_code == 130:
                raise
    elif sys.platform == "darwin":
        result["clock"] = {"state": "available"}
    return result


def status(result: dict) -> int:
    required = ("platform", "python", "op")
    if any(result[key]["state"] != "available" for key in required):
        return 3
    return 3 if result["clock"]["state"] == "missing" else 0
