"""Non-authenticating capability assessment."""

import platform
import shutil
import sys

from .backends.onepassword import child_environment, probe
from .errors import AppError
from .processes import run


def report(env: dict[str, str]) -> dict:
    result = {
        "platform": {
            "state": "available" if sys.platform in ("linux", "darwin", "win32") else "missing"
        },
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
    elif sys.platform == "win32":
        clip_path = shutil.which("clip", path=env.get("PATH", ""))
        if clip_path:
            result["wl-copy"] = {"state": "available", "path": clip_path}

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

    from .backends import dpapi, keychain

    if sys.platform == "darwin":
        result["keychain"] = keychain.probe(env)
        result["secure-enclave"] = {
            "state": "available" if keychain.has_secure_enclave() else "missing"
        }
        result["totpm"] = {"state": "not-applicable"}
        result["tpm2-totp"] = {"state": "not-applicable"}
        result["tpm-device"] = {"state": "not-applicable"}
        result["dpapi"] = {"state": "not-applicable"}
        result["credman"] = {"state": "not-applicable"}
        result["windows-hello"] = {"state": "not-applicable"}
    elif sys.platform == "win32":
        result["dpapi"] = dpapi.probe(env)
        result["credman"] = dpapi.probe_credman(env)
        result["windows-hello"] = {
            "state": "available" if dpapi.has_windows_hello() else "missing"
        }
        result["keychain"] = {"state": "not-applicable"}
        result["secure-enclave"] = {"state": "not-applicable"}
        result["totpm"] = {"state": "not-applicable"}
        result["tpm2-totp"] = {"state": "not-applicable"}
        result["tpm-device"] = {"state": "not-applicable"}
    else:
        result["keychain"] = {"state": "not-applicable"}
        result["secure-enclave"] = {"state": "not-applicable"}
        if dpapi.is_wsl_bridge_active(env):
            result["dpapi"] = dpapi.probe(env)
            result["credman"] = dpapi.probe_credman(env)
            result["windows-hello"] = {"state": "not-applicable"}
        else:
            result["dpapi"] = {"state": "not-applicable"}
            result["credman"] = {"state": "not-applicable"}
            result["windows-hello"] = {"state": "not-applicable"}
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
    elif sys.platform == "win32":
        w32tm = shutil.which("w32tm", path=env.get("PATH", ""))
        if w32tm:
            try:
                obs = run([w32tm, "/query", "/status"], env=child_environment(env), timeout=3)
                result["clock"] = {"state": "available" if obs.returncode == 0 else "missing"}
            except AppError:
                result["clock"] = {"state": "available"}
        else:
            result["clock"] = {"state": "available"}
    return result


BREW_CAPABILITY_MAP = {
    "fish": "fish",
    "pass": "pass",
    "oathtool": "oath-toolkit",
    "yubikey": "ykman",
    "fzf": "fzf",
    "qrencode": "qrencode",
    "pinentry": "pinentry-mac",
}

WINGET_CAPABILITY_MAP = {
    "fish": "fish-shell.fish",
    "pass": "GnuPG.Gpg4win",
    "gpg": "GnuPG.Gpg4win",
    "yubikey": "Yubico.YubiKeyManager",
    "fzf": "junegunn.fzf",
    "qrencode": "StefanHolek.qrencode",
}

SCOOP_CAPABILITY_MAP = {
    "fish": "fish",
    "pass": "pass",
    "gpg": "gpg",
    "oathtool": "oathtool",
    "yubikey": "ykman",
    "fzf": "fzf",
    "qrencode": "qrencode",
}


def install_missing(env: dict[str, str], *, stdout=None, stderr=None) -> bool:
    """Attempt automatic remediation of missing optional dependencies via system package manager."""
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr

    current = report(env)
    missing = [k for k, v in current.items() if v.get("state") == "missing"]

    if sys.platform == "darwin":
        brew = shutil.which("brew", path=env.get("PATH", ""))
        if not brew:
            err.write(
                "Automatic install requires Homebrew ('brew'). Install Homebrew from https://brew.sh\n"
            )
            return False

        packages_to_install = []
        for cap in missing:
            formula = BREW_CAPABILITY_MAP.get(cap)
            if formula and formula not in packages_to_install:
                packages_to_install.append(formula)

        if packages_to_install:
            out.write(
                f"Installing missing capabilities via Homebrew: {' '.join(packages_to_install)}...\n"
            )
            try:
                proc = run(
                    [brew, "install", *packages_to_install],
                    env=child_environment(env),
                    timeout=900,
                    stdout_cap=10 * 1024 * 1024,
                    stderr_cap=10 * 1024 * 1024,
                    preserve_session=True,
                )
                if isinstance(getattr(proc, "stdout", None), (bytes, bytearray)):
                    out.write(proc.stdout.decode("utf-8", errors="replace"))
                if proc.returncode == 0:
                    out.write("Successfully installed missing Homebrew packages.\n\n")
                    return True
                else:
                    err.write("Homebrew installation returned a non-zero exit code.\n\n")
                    return False
            except AppError as error:
                if error.exit_code == 7:
                    err.write("Installation timed out after 15 minutes.\n\n")
                elif error.exit_code == 130:
                    err.write("Installation was interrupted by user.\n\n")
                else:
                    err.write("Installation encountered an unexpected execution error.\n\n")
                return False
        else:
            out.write("No installable software packages are missing.\n\n")
            return True

    elif sys.platform == "win32":
        winget = shutil.which("winget", path=env.get("PATH", ""))
        scoop = shutil.which("scoop", path=env.get("PATH", ""))

        if not winget and not scoop:
            err.write(
                "Automatic install on Windows requires winget or Scoop. Install winget via App Installer or Scoop from https://scoop.sh\n"
            )
            return False

        if winget:
            packages_to_install = []
            for cap in missing:
                pkg = WINGET_CAPABILITY_MAP.get(cap)
                if pkg and pkg not in packages_to_install:
                    packages_to_install.append(pkg)

            if packages_to_install:
                out.write(
                    f"Installing missing capabilities via winget: {' '.join(packages_to_install)}...\n"
                )
                try:
                    all_success = True
                    for pkg in packages_to_install:
                        proc = run(
                            [
                                winget,
                                "install",
                                "--exact",
                                "--id",
                                pkg,
                                "--accept-source-agreements",
                                "--accept-package-agreements",
                                "--silent",
                            ],
                            env=child_environment(env),
                            timeout=900,
                            stdout_cap=10 * 1024 * 1024,
                            stderr_cap=10 * 1024 * 1024,
                            preserve_session=True,
                        )
                        if isinstance(getattr(proc, "stdout", None), (bytes, bytearray)):
                            out.write(proc.stdout.decode("utf-8", errors="replace"))
                        if proc.returncode != 0:
                            all_success = False
                    if all_success:
                        out.write("Successfully installed missing winget packages.\n\n")
                        return True
                    else:
                        err.write("winget installation returned a non-zero exit code.\n\n")
                        return False
                except AppError as error:
                    if error.exit_code == 7:
                        err.write("Installation timed out after 15 minutes.\n\n")
                    elif error.exit_code == 130:
                        err.write("Installation was interrupted by user.\n\n")
                    else:
                        err.write("Installation encountered an unexpected execution error.\n\n")
                    return False
            else:
                out.write("No installable software packages are missing.\n\n")
                return True
        elif scoop:
            packages_to_install = []
            for cap in missing:
                pkg = SCOOP_CAPABILITY_MAP.get(cap)
                if pkg and pkg not in packages_to_install:
                    packages_to_install.append(pkg)

            if packages_to_install:
                out.write(
                    f"Installing missing capabilities via Scoop: {' '.join(packages_to_install)}...\n"
                )
                try:
                    proc = run(
                        [scoop, "install", *packages_to_install],
                        env=child_environment(env),
                        timeout=900,
                        stdout_cap=10 * 1024 * 1024,
                        stderr_cap=10 * 1024 * 1024,
                        preserve_session=True,
                    )
                    if isinstance(getattr(proc, "stdout", None), (bytes, bytearray)):
                        out.write(proc.stdout.decode("utf-8", errors="replace"))
                    if proc.returncode == 0:
                        out.write("Successfully installed missing Scoop packages.\n\n")
                        return True
                    else:
                        err.write("Scoop installation returned a non-zero exit code.\n\n")
                        return False
                except AppError as error:
                    if error.exit_code == 7:
                        err.write("Installation timed out after 15 minutes.\n\n")
                    elif error.exit_code == 130:
                        err.write("Installation was interrupted by user.\n\n")
                    else:
                        err.write("Installation encountered an unexpected execution error.\n\n")
                    return False
            else:
                out.write("No installable software packages are missing.\n\n")
                return True

    return True


def status(result: dict) -> int:
    required = ("platform", "python", "op")
    if any(result[key]["state"] != "available" for key in required):
        return 3
    return 3 if result["clock"]["state"] == "missing" else 0
