import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

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

    from .backends import bitwarden, dpapi, fido2, keepass, keychain

    result["fido2"] = fido2.probe(env)
    result["bitwarden"] = bitwarden.probe(env)
    result["keepass"] = keepass.probe(env)

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
        result["windows-hello"] = {"state": "available" if dpapi.has_windows_hello() else "missing"}
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

    try:
        from . import security

        mem_status = security.memory_security_status()
        result["memory-security"] = {
            "state": (
                "available"
                if mem_status["mlock_supported"] or mem_status["madvise_dontdump_supported"]
                else "missing"
            ),
            "mlock": mem_status["mlock_supported"],
            "dontdump": mem_status["madvise_dontdump_supported"],
        }
    except Exception:
        pass

    if sys.platform == "linux":
        try:
            from .pam_check import probe_pam_subsystem

            pam_sub = probe_pam_subsystem()
            result["pam"] = {"state": pam_sub.get("state", "missing")}
        except Exception:
            result["pam"] = {"state": "unknown"}
        for build_tool in ("gcc", "make"):
            bt_path = shutil.which(build_tool, path=env.get("PATH", ""))
            result[build_tool] = (
                {"state": "available", "path": bt_path} if bt_path else {"state": "missing"}
            )
    else:
        result["pam"] = {"state": "not-applicable"}
        result["gcc"] = {"state": "not-applicable"}
        result["make"] = {"state": "not-applicable"}

    return result


BREW_CAPABILITY_MAP = {
    "fish": "fish",
    "pass": "pass",
    "oathtool": "oath-toolkit",
    "yubikey": "ykman",
    "fzf": "fzf",
    "qrencode": "qrencode",
    "pinentry": "pinentry-mac",
    "bitwarden": "bitwarden-cli",
    "keepass": "keepassxc",
}

WINGET_CAPABILITY_MAP = {
    "fish": "fish-shell.fish",
    "pass": "GnuPG.Gpg4win",
    "gpg": "GnuPG.Gpg4win",
    "yubikey": "Yubico.YubiKeyManager",
    "fzf": "junegunn.fzf",
    "qrencode": "StefanHolek.qrencode",
    "bitwarden": "Bitwarden.CLI",
    "keepass": "KeePassXCTeam.KeePassXC",
}

SCOOP_CAPABILITY_MAP = {
    "fish": "fish",
    "pass": "pass",
    "gpg": "gpg",
    "oathtool": "oathtool",
    "yubikey": "ykman",
    "fzf": "fzf",
    "qrencode": "qrencode",
    "bitwarden": "bw",
    "keepass": "keepassxc",
}

APT_CAPABILITY_MAP = {
    "fish": "fish",
    "fzf": "fzf",
    "wl-copy": "wl-clipboard",
    "qrencode": "qrencode",
    "pinentry": "pinentry-curses",
    "gpg": "gnupg",
    "pass": "pass",
    "oathtool": "oathtool",
    "yubikey": "yubikey-manager",
    "ykman": "yubikey-manager",
    "keepass": "keepassxc",
    "keepassxc-cli": "keepassxc",
    "bitwarden": "bitwarden-cli",
    "bw": "bitwarden-cli",
    "pam": "libpam0g-dev",
    "gcc": "gcc",
    "make": "make",
    "build-essential": "build-essential",
}

PACMAN_CAPABILITY_MAP = {
    "fish": "fish",
    "fzf": "fzf",
    "wl-copy": "wl-clipboard",
    "qrencode": "qrencode",
    "pinentry": "pinentry",
    "gpg": "gnupg",
    "pass": "pass",
    "oathtool": "oath-toolkit",
    "yubikey": "yubikey-manager",
    "ykman": "yubikey-manager",
    "keepass": "keepassxc",
    "keepassxc-cli": "keepassxc",
    "bitwarden": "bitwarden-cli",
    "bw": "bitwarden-cli",
    "pam": "pam",
    "gcc": "gcc",
    "make": "make",
    "build-essential": "base-devel",
}

DNF_CAPABILITY_MAP = {
    "fish": "fish",
    "fzf": "fzf",
    "wl-copy": "wl-clipboard",
    "qrencode": "qrencode",
    "pinentry": "pinentry",
    "gpg": "gnupg2",
    "pass": "pass",
    "oathtool": "oathtool",
    "yubikey": "yubikey-manager",
    "ykman": "yubikey-manager",
    "keepass": "keepassxc",
    "keepassxc-cli": "keepassxc",
    "bitwarden": "bitwarden-cli",
    "bw": "bitwarden-cli",
    "pam": "pam-devel",
    "gcc": "gcc",
    "make": "make",
    "build-essential": "gcc make",
}


def get_os_release() -> dict[str, str]:
    """Safely inspect system os-release dictionary."""
    try:
        return platform.freedesktop_os_release()
    except OSError, AttributeError, Exception:
        pass
    for candidate in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            p = Path(candidate)
            if p.is_file():
                res = {}
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    res[k.strip()] = v.strip().strip('"').strip("'")
                return res
        except OSError, PermissionError:
            pass
    return {}


def detect_linux_package_manager(env: dict[str, str] | None = None) -> tuple[str, str] | None:
    """Detect Linux distribution family and package manager binary path.

    Returns:
        tuple[str, str] | None: (family, binary_path) where family is "debian", "arch", or "fedora"
    """
    path_env = env.get("PATH", "") if env else ""
    rel = get_os_release()
    distro_id = rel.get("ID", "").lower()
    id_like = rel.get("ID_LIKE", "").lower().split()

    if distro_id in {
        "debian",
        "ubuntu",
        "pop",
        "mint",
        "kali",
        "raspbian",
        "elementary",
        "zorin",
    } or any(k in id_like for k in ("debian", "ubuntu")):
        apt_bin = shutil.which("apt-get", path=path_env) or shutil.which("apt", path=path_env)
        if apt_bin:
            return ("debian", apt_bin)

    if (
        distro_id in {"arch", "cachyos", "manjaro", "endeavouros", "artix", "garuda", "arco"}
        or "arch" in id_like
    ):
        pacman_bin = shutil.which("pacman", path=path_env)
        if pacman_bin:
            return ("arch", pacman_bin)

    if distro_id in {
        "fedora",
        "rhel",
        "centos",
        "rocky",
        "almalinux",
        "nobara",
        "ol",
    } or any(k in id_like for k in ("fedora", "rhel", "centos")):
        dnf_bin = shutil.which("dnf", path=path_env) or shutil.which("yum", path=path_env)
        if dnf_bin:
            return ("fedora", dnf_bin)

    # Fallback to checking package manager binaries directly in PATH
    apt_bin = shutil.which("apt-get", path=path_env) or shutil.which("apt", path=path_env)
    if apt_bin:
        return ("debian", apt_bin)

    pacman_bin = shutil.which("pacman", path=path_env)
    if pacman_bin:
        return ("arch", pacman_bin)

    dnf_bin = shutil.which("dnf", path=path_env) or shutil.which("yum", path=path_env)
    if dnf_bin:
        return ("fedora", dnf_bin)

    return None


def build_linux_install_command(
    family: str,
    pm_binary: str,
    packages: list[str],
    *,
    is_root: bool = False,
    sudo_binary: str = "sudo",
) -> list[str]:
    """Generate non-interactive package installation command list."""
    if family == "debian":
        base_cmd = [pm_binary, "install", "-y", *packages]
    elif family == "arch":
        base_cmd = [pm_binary, "-S", "--noconfirm", *packages]
    elif family == "fedora":
        base_cmd = [pm_binary, "install", "-y", *packages]
    else:
        base_cmd = [pm_binary, "install", "-y", *packages]

    if not is_root:
        return [sudo_binary, *base_cmd]
    return base_cmd


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

    elif sys.platform == "linux":
        pm_info = detect_linux_package_manager(env)
        if not pm_info:
            err.write(
                "Automatic install on Linux requires apt-get, pacman, or dnf. "
                "Install missing packages manually using your distribution's package manager.\n\n"
            )
            return False

        family, pm_bin = pm_info
        distro_maps = {
            "debian": APT_CAPABILITY_MAP,
            "arch": PACMAN_CAPABILITY_MAP,
            "fedora": DNF_CAPABILITY_MAP,
        }
        cap_map = distro_maps.get(family, {})

        packages_to_install = []
        for cap in missing:
            pkg = cap_map.get(cap)
            if pkg and pkg not in packages_to_install:
                packages_to_install.append(pkg)

        if packages_to_install:
            pm_name = "APT" if family == "debian" else ("Pacman" if family == "arch" else "DNF")
            out.write(
                f"Installing missing capabilities via {pm_name}: {' '.join(packages_to_install)}...\n"
            )
            is_root = getattr(os, "geteuid", lambda: -1)() == 0
            sudo_bin = shutil.which("sudo", path=env.get("PATH", "")) or "sudo"
            cmd = build_linux_install_command(
                family, pm_bin, packages_to_install, is_root=is_root, sudo_binary=sudo_bin
            )
            try:
                child_env = child_environment(env)
                if family == "debian":
                    child_env["DEBIAN_FRONTEND"] = "noninteractive"
                proc = run(
                    cmd,
                    env=child_env,
                    timeout=900,
                    stdout_cap=10 * 1024 * 1024,
                    stderr_cap=10 * 1024 * 1024,
                    preserve_session=True,
                )
                if isinstance(getattr(proc, "stdout", None), (bytes, bytearray)):
                    out.write(proc.stdout.decode("utf-8", errors="replace"))
                if proc.returncode == 0:
                    out.write(f"Successfully installed missing {pm_name} packages.\n\n")
                    return True
                else:
                    err.write(f"{pm_name} installation returned a non-zero exit code.\n\n")
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


def doctor_check(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Execute capability inspection and compute automated remediation plan."""
    env_clean = dict(os.environ) if env is None else env
    rep = report(env_clean)
    missing = [k for k, v in rep.items() if v.get("state") == "missing"]

    pm_data: dict[str, Any] = {
        "platform": sys.platform,
        "family": "unknown",
        "binary": None,
    }
    packages_to_install: list[str] = []
    command: list[str] = []
    recommendations: list[str] = []

    if sys.platform == "linux":
        pm_info = detect_linux_package_manager(env_clean)
        if pm_info:
            family, pm_bin = pm_info
            pm_data["family"] = family
            pm_data["binary"] = pm_bin
            distro_maps = {
                "debian": APT_CAPABILITY_MAP,
                "arch": PACMAN_CAPABILITY_MAP,
                "fedora": DNF_CAPABILITY_MAP,
            }
            cap_map = distro_maps.get(family, {})
            for cap in missing:
                pkg = cap_map.get(cap)
                if pkg and pkg not in packages_to_install:
                    packages_to_install.append(pkg)
            if packages_to_install:
                is_root = getattr(os, "geteuid", lambda: -1)() == 0
                sudo_bin = shutil.which("sudo", path=env_clean.get("PATH", "")) or "sudo"
                command = build_linux_install_command(
                    family, pm_bin, packages_to_install, is_root=is_root, sudo_binary=sudo_bin
                )
                recommendations.append(f"Install missing system packages via: {' '.join(command)}")
        elif missing:
            recommendations.append(
                f"Install missing capabilities manually ({', '.join(missing)}) using your Linux distribution's package manager."
            )

    elif sys.platform == "darwin":
        brew = shutil.which("brew", path=env_clean.get("PATH", ""))
        pm_data["family"] = "homebrew"
        pm_data["binary"] = brew
        if brew:
            for cap in missing:
                formula = BREW_CAPABILITY_MAP.get(cap)
                if formula and formula not in packages_to_install:
                    packages_to_install.append(formula)
            if packages_to_install:
                command = [brew, "install", *packages_to_install]
                recommendations.append(
                    f"Install missing Homebrew formulas via: {' '.join(command)}"
                )
        elif missing:
            recommendations.append(
                "Install Homebrew from https://brew.sh to enable automatic capability installation."
            )

    elif sys.platform == "win32":
        winget = shutil.which("winget", path=env_clean.get("PATH", ""))
        scoop = shutil.which("scoop", path=env_clean.get("PATH", ""))
        if winget:
            pm_data["family"] = "winget"
            pm_data["binary"] = winget
            for cap in missing:
                pkg = WINGET_CAPABILITY_MAP.get(cap)
                if pkg and pkg not in packages_to_install:
                    packages_to_install.append(pkg)
            if packages_to_install:
                command = [winget, "install", *packages_to_install]
                recommendations.append(f"Install missing winget packages via: {' '.join(command)}")
        elif scoop:
            pm_data["family"] = "scoop"
            pm_data["binary"] = scoop
            for cap in missing:
                pkg = SCOOP_CAPABILITY_MAP.get(cap)
                if pkg and pkg not in packages_to_install:
                    packages_to_install.append(pkg)
            if packages_to_install:
                command = [scoop, "install", *packages_to_install]
                recommendations.append(f"Install missing Scoop packages via: {' '.join(command)}")

    if rep.get("clock", {}).get("state") == "missing":
        recommendations.append(
            "System clock is not NTP-synchronized. Run 'timedatectl set-ntp true' to avoid TOTP token drift."
        )

    if rep.get("op", {}).get("state") == "missing":
        recommendations.append(
            "1Password CLI ('op') is not found in PATH. Install from https://developer.1password.com/docs/cli/ or configure an alternative vault backend."
        )

    return {
        "status": status(rep),
        "report": rep,
        "missing": missing,
        "package_manager": pm_data,
        "packages_to_install": packages_to_install,
        "command": command,
        "recommendations": recommendations,
        "healthy": status(rep) == 0 and len(missing) == 0,
    }


def status(result: dict) -> int:
    required = ("platform", "python", "op")
    if any(result[key]["state"] != "available" for key in required):
        return 3
    return 3 if result["clock"]["state"] == "missing" else 0
