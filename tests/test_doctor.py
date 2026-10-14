"""Tests for Linux package manager detection, capability remediation, and doctor diagnostics."""

import io
import unittest
from unittest.mock import MagicMock, patch

from authy_local import cli, doctor
from authy_local.errors import AppError


class TestLinuxPackageManagerDetection(unittest.TestCase):
    """Tests for detect_linux_package_manager() across distro families and PATH fallbacks."""

    @patch("authy_local.doctor.get_os_release", return_value={"ID": "debian"})
    @patch("shutil.which")
    def test_detect_debian(self, mock_which, mock_rel) -> None:
        mock_which.side_effect = lambda cmd, path="": (
            "/usr/bin/apt-get" if cmd == "apt-get" else None
        )
        res = doctor.detect_linux_package_manager({"PATH": "/usr/bin"})
        self.assertEqual(res, ("debian", "/usr/bin/apt-get"))

    @patch("authy_local.doctor.get_os_release", return_value={"ID": "ubuntu", "ID_LIKE": "debian"})
    @patch("shutil.which")
    def test_detect_ubuntu(self, mock_which, mock_rel) -> None:
        mock_which.side_effect = lambda cmd, path="": (
            "/usr/bin/apt-get" if cmd == "apt-get" else None
        )
        res = doctor.detect_linux_package_manager({"PATH": "/usr/bin"})
        self.assertEqual(res, ("debian", "/usr/bin/apt-get"))

    @patch("authy_local.doctor.get_os_release", return_value={"ID": "arch"})
    @patch("shutil.which")
    def test_detect_arch(self, mock_which, mock_rel) -> None:
        mock_which.side_effect = lambda cmd, path="": "/usr/bin/pacman" if cmd == "pacman" else None
        res = doctor.detect_linux_package_manager({"PATH": "/usr/bin"})
        self.assertEqual(res, ("arch", "/usr/bin/pacman"))

    @patch("authy_local.doctor.get_os_release", return_value={"ID": "cachyos", "ID_LIKE": "arch"})
    @patch("shutil.which")
    def test_detect_cachyos(self, mock_which, mock_rel) -> None:
        mock_which.side_effect = lambda cmd, path="": "/usr/bin/pacman" if cmd == "pacman" else None
        res = doctor.detect_linux_package_manager({"PATH": "/usr/bin"})
        self.assertEqual(res, ("arch", "/usr/bin/pacman"))

    @patch("authy_local.doctor.get_os_release", return_value={"ID": "fedora"})
    @patch("shutil.which")
    def test_detect_fedora(self, mock_which, mock_rel) -> None:
        mock_which.side_effect = lambda cmd, path="": "/usr/bin/dnf" if cmd == "dnf" else None
        res = doctor.detect_linux_package_manager({"PATH": "/usr/bin"})
        self.assertEqual(res, ("fedora", "/usr/bin/dnf"))

    @patch("authy_local.doctor.get_os_release", return_value={"ID": "rhel", "ID_LIKE": "fedora"})
    @patch("shutil.which")
    def test_detect_rhel(self, mock_which, mock_rel) -> None:
        mock_which.side_effect = lambda cmd, path="": "/usr/bin/dnf" if cmd == "dnf" else None
        res = doctor.detect_linux_package_manager({"PATH": "/usr/bin"})
        self.assertEqual(res, ("fedora", "/usr/bin/dnf"))

    @patch("authy_local.doctor.get_os_release", return_value={})
    @patch("shutil.which")
    def test_fallback_binary_pacman_when_os_release_fails(self, mock_which, mock_rel) -> None:
        mock_which.side_effect = lambda cmd, path="": "/usr/bin/pacman" if cmd == "pacman" else None
        res = doctor.detect_linux_package_manager({"PATH": "/usr/bin"})
        self.assertEqual(res, ("arch", "/usr/bin/pacman"))

    @patch("authy_local.doctor.get_os_release", return_value={})
    @patch("shutil.which")
    def test_fallback_binary_apt_when_os_release_fails(self, mock_which, mock_rel) -> None:
        mock_which.side_effect = lambda cmd, path="": (
            "/usr/bin/apt-get" if cmd == "apt-get" else None
        )
        res = doctor.detect_linux_package_manager({"PATH": "/usr/bin"})
        self.assertEqual(res, ("debian", "/usr/bin/apt-get"))

    @patch("authy_local.doctor.get_os_release", return_value={})
    @patch("shutil.which")
    def test_fallback_binary_dnf_when_os_release_fails(self, mock_which, mock_rel) -> None:
        mock_which.side_effect = lambda cmd, path="": "/usr/bin/dnf" if cmd == "dnf" else None
        res = doctor.detect_linux_package_manager({"PATH": "/usr/bin"})
        self.assertEqual(res, ("fedora", "/usr/bin/dnf"))

    @patch("authy_local.doctor.get_os_release", return_value={"ID": "solaris"})
    @patch("shutil.which", return_value=None)
    def test_unknown_distribution_returns_none(self, mock_which, mock_rel) -> None:
        res = doctor.detect_linux_package_manager({"PATH": "/usr/bin"})
        self.assertIsNone(res)


class TestLinuxCommandGeneration(unittest.TestCase):
    """Tests for build_linux_install_command() across package managers and root/non-root."""

    def test_build_apt_command_non_root(self) -> None:
        cmd = doctor.build_linux_install_command(
            "debian", "/usr/bin/apt-get", ["libpam0g-dev"], is_root=False, sudo_binary="sudo"
        )
        self.assertEqual(cmd, ["sudo", "/usr/bin/apt-get", "install", "-y", "libpam0g-dev"])

    def test_build_apt_command_root(self) -> None:
        cmd = doctor.build_linux_install_command(
            "debian", "/usr/bin/apt-get", ["libpam0g-dev"], is_root=True
        )
        self.assertEqual(cmd, ["/usr/bin/apt-get", "install", "-y", "libpam0g-dev"])

    def test_build_pacman_command_non_root(self) -> None:
        cmd = doctor.build_linux_install_command(
            "arch", "/usr/bin/pacman", ["pam"], is_root=False, sudo_binary="sudo"
        )
        self.assertEqual(cmd, ["sudo", "/usr/bin/pacman", "-S", "--noconfirm", "pam"])

    def test_build_pacman_command_root(self) -> None:
        cmd = doctor.build_linux_install_command("arch", "/usr/bin/pacman", ["pam"], is_root=True)
        self.assertEqual(cmd, ["/usr/bin/pacman", "-S", "--noconfirm", "pam"])

    def test_build_dnf_command_non_root(self) -> None:
        cmd = doctor.build_linux_install_command(
            "fedora", "/usr/bin/dnf", ["pam-devel"], is_root=False, sudo_binary="sudo"
        )
        self.assertEqual(cmd, ["sudo", "/usr/bin/dnf", "install", "-y", "pam-devel"])

    def test_build_dnf_command_root(self) -> None:
        cmd = doctor.build_linux_install_command(
            "fedora", "/usr/bin/dnf", ["pam-devel"], is_root=True
        )
        self.assertEqual(cmd, ["/usr/bin/dnf", "install", "-y", "pam-devel"])

    def test_custom_sudo_binary(self) -> None:
        cmd = doctor.build_linux_install_command(
            "debian",
            "/usr/bin/apt-get",
            ["libpam0g-dev"],
            is_root=False,
            sudo_binary="/opt/bin/sudo",
        )
        self.assertEqual(
            cmd, ["/opt/bin/sudo", "/usr/bin/apt-get", "install", "-y", "libpam0g-dev"]
        )


class TestLinuxDependencyMapping(unittest.TestCase):
    """Tests for APT, Pacman, and DNF capability mappings."""

    def test_pam_mapping(self) -> None:
        self.assertEqual(doctor.APT_CAPABILITY_MAP["pam"], "libpam0g-dev")
        self.assertEqual(doctor.PACMAN_CAPABILITY_MAP["pam"], "pam")
        self.assertEqual(doctor.DNF_CAPABILITY_MAP["pam"], "pam-devel")

    def test_yubikey_mapping(self) -> None:
        self.assertEqual(doctor.APT_CAPABILITY_MAP["yubikey"], "yubikey-manager")
        self.assertEqual(doctor.PACMAN_CAPABILITY_MAP["yubikey"], "yubikey-manager")
        self.assertEqual(doctor.DNF_CAPABILITY_MAP["yubikey"], "yubikey-manager")

    def test_bitwarden_mapping(self) -> None:
        self.assertEqual(doctor.APT_CAPABILITY_MAP["bitwarden"], "bitwarden-cli")
        self.assertEqual(doctor.PACMAN_CAPABILITY_MAP["bitwarden"], "bitwarden-cli")
        self.assertEqual(doctor.DNF_CAPABILITY_MAP["bitwarden"], "bitwarden-cli")

    def test_keepass_mapping(self) -> None:
        self.assertEqual(doctor.APT_CAPABILITY_MAP["keepass"], "keepassxc")
        self.assertEqual(doctor.PACMAN_CAPABILITY_MAP["keepass"], "keepassxc")
        self.assertEqual(doctor.DNF_CAPABILITY_MAP["keepass"], "keepassxc")

    def test_pass_mapping(self) -> None:
        self.assertEqual(doctor.APT_CAPABILITY_MAP["pass"], "pass")
        self.assertEqual(doctor.PACMAN_CAPABILITY_MAP["pass"], "pass")
        self.assertEqual(doctor.DNF_CAPABILITY_MAP["pass"], "pass")

    def test_build_tools_mapping(self) -> None:
        self.assertEqual(doctor.APT_CAPABILITY_MAP["gcc"], "gcc")
        self.assertEqual(doctor.PACMAN_CAPABILITY_MAP["gcc"], "gcc")
        self.assertEqual(doctor.DNF_CAPABILITY_MAP["gcc"], "gcc")
        self.assertEqual(doctor.APT_CAPABILITY_MAP["make"], "make")
        self.assertEqual(doctor.PACMAN_CAPABILITY_MAP["make"], "make")
        self.assertEqual(doctor.DNF_CAPABILITY_MAP["make"], "make")
        self.assertEqual(doctor.APT_CAPABILITY_MAP["build-essential"], "build-essential")
        self.assertEqual(doctor.PACMAN_CAPABILITY_MAP["build-essential"], "base-devel")
        self.assertEqual(doctor.DNF_CAPABILITY_MAP["build-essential"], "gcc make")

    def test_clipboard_mapping(self) -> None:
        self.assertEqual(doctor.APT_CAPABILITY_MAP["wl-copy"], "wl-clipboard")
        self.assertEqual(doctor.PACMAN_CAPABILITY_MAP["wl-copy"], "wl-clipboard")
        self.assertEqual(doctor.DNF_CAPABILITY_MAP["wl-copy"], "wl-clipboard")


class TestDoctorInstallMissingLinux(unittest.TestCase):
    """Tests for install_missing() execution on Linux with various package managers."""

    @patch("sys.platform", "linux")
    @patch(
        "authy_local.doctor.detect_linux_package_manager",
        return_value=("debian", "/usr/bin/apt-get"),
    )
    @patch("authy_local.doctor.report")
    @patch("authy_local.doctor.run")
    @patch("os.geteuid", return_value=1000)
    def test_install_missing_apt_success(
        self, mock_euid, mock_run, mock_report, mock_detect
    ) -> None:
        mock_report.return_value = {
            "pam": {"state": "missing"},
            "yubikey": {"state": "missing"},
        }
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"Setting up packages...\n"
        mock_run.return_value = mock_proc

        out = io.StringIO()
        err = io.StringIO()
        success = doctor.install_missing({"PATH": "/usr/bin"}, stdout=out, stderr=err)

        self.assertTrue(success)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertTrue(cmd[0].endswith("sudo"))
        self.assertEqual(
            cmd[1:], ["/usr/bin/apt-get", "install", "-y", "libpam0g-dev", "yubikey-manager"]
        )
        env_passed = mock_run.call_args[1]["env"]
        self.assertEqual(env_passed.get("DEBIAN_FRONTEND"), "noninteractive")
        self.assertIn("Successfully installed missing APT packages", out.getvalue())

    @patch("sys.platform", "linux")
    @patch(
        "authy_local.doctor.detect_linux_package_manager", return_value=("arch", "/usr/bin/pacman")
    )
    @patch("authy_local.doctor.report")
    @patch("authy_local.doctor.run")
    @patch("os.geteuid", return_value=0)
    def test_install_missing_pacman_success(
        self, mock_euid, mock_run, mock_report, mock_detect
    ) -> None:
        mock_report.return_value = {
            "pam": {"state": "missing"},
            "keepass": {"state": "missing"},
        }
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"installing pam...\n"
        mock_run.return_value = mock_proc

        out = io.StringIO()
        err = io.StringIO()
        success = doctor.install_missing({"PATH": "/usr/bin"}, stdout=out, stderr=err)

        self.assertTrue(success)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd, ["/usr/bin/pacman", "-S", "--noconfirm", "pam", "keepassxc"])
        self.assertIn("Successfully installed missing Pacman packages", out.getvalue())

    @patch("sys.platform", "linux")
    @patch(
        "authy_local.doctor.detect_linux_package_manager", return_value=("fedora", "/usr/bin/dnf")
    )
    @patch("authy_local.doctor.report")
    @patch("authy_local.doctor.run")
    @patch("os.geteuid", return_value=1000)
    def test_install_missing_dnf_success(
        self, mock_euid, mock_run, mock_report, mock_detect
    ) -> None:
        mock_report.return_value = {
            "pam": {"state": "missing"},
            "bitwarden": {"state": "missing"},
        }
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"Installed pam-devel...\n"
        mock_run.return_value = mock_proc

        out = io.StringIO()
        err = io.StringIO()
        success = doctor.install_missing({"PATH": "/usr/bin"}, stdout=out, stderr=err)

        self.assertTrue(success)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertTrue(cmd[0].endswith("sudo"))
        self.assertEqual(cmd[1:], ["/usr/bin/dnf", "install", "-y", "pam-devel", "bitwarden-cli"])
        self.assertIn("Successfully installed missing DNF packages", out.getvalue())

    @patch("sys.platform", "linux")
    @patch(
        "authy_local.doctor.detect_linux_package_manager", return_value=("arch", "/usr/bin/pacman")
    )
    @patch("authy_local.doctor.report")
    @patch("authy_local.doctor.run")
    def test_install_missing_nonzero_exit(self, mock_run, mock_report, mock_detect) -> None:
        mock_report.return_value = {"pam": {"state": "missing"}}
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = b""
        mock_run.return_value = mock_proc

        out = io.StringIO()
        err = io.StringIO()
        success = doctor.install_missing({"PATH": "/usr/bin"}, stdout=out, stderr=err)

        self.assertFalse(success)
        self.assertIn("Pacman installation returned a non-zero exit code", err.getvalue())

    @patch("sys.platform", "linux")
    @patch(
        "authy_local.doctor.detect_linux_package_manager", return_value=("arch", "/usr/bin/pacman")
    )
    @patch("authy_local.doctor.report")
    @patch("authy_local.doctor.run", side_effect=AppError(7))
    def test_install_missing_timeout(self, mock_run, mock_report, mock_detect) -> None:
        mock_report.return_value = {"pam": {"state": "missing"}}
        out = io.StringIO()
        err = io.StringIO()
        success = doctor.install_missing({"PATH": "/usr/bin"}, stdout=out, stderr=err)

        self.assertFalse(success)
        self.assertIn("Installation timed out after 15 minutes", err.getvalue())

    @patch("sys.platform", "linux")
    @patch(
        "authy_local.doctor.detect_linux_package_manager", return_value=("arch", "/usr/bin/pacman")
    )
    @patch("authy_local.doctor.report")
    @patch("authy_local.doctor.run", side_effect=AppError(130))
    def test_install_missing_interrupt(self, mock_run, mock_report, mock_detect) -> None:
        mock_report.return_value = {"pam": {"state": "missing"}}
        out = io.StringIO()
        err = io.StringIO()
        success = doctor.install_missing({"PATH": "/usr/bin"}, stdout=out, stderr=err)

        self.assertFalse(success)
        self.assertIn("Installation was interrupted by user", err.getvalue())

    @patch("sys.platform", "linux")
    @patch(
        "authy_local.doctor.detect_linux_package_manager", return_value=("arch", "/usr/bin/pacman")
    )
    @patch("authy_local.doctor.report")
    @patch("authy_local.doctor.run", side_effect=AppError(4))
    def test_install_missing_unexpected_error(self, mock_run, mock_report, mock_detect) -> None:
        mock_report.return_value = {"pam": {"state": "missing"}}
        out = io.StringIO()
        err = io.StringIO()
        success = doctor.install_missing({"PATH": "/usr/bin"}, stdout=out, stderr=err)

        self.assertFalse(success)
        self.assertIn("Installation encountered an unexpected execution error", err.getvalue())

    @patch("sys.platform", "linux")
    @patch(
        "authy_local.doctor.detect_linux_package_manager", return_value=("arch", "/usr/bin/pacman")
    )
    @patch("authy_local.doctor.report")
    def test_install_missing_no_packages_needed(self, mock_report, mock_detect) -> None:
        mock_report.return_value = {
            "platform": {"state": "available"},
            "python": {"state": "available"},
            "op": {"state": "available"},
            "clock": {"state": "available"},
        }
        out = io.StringIO()
        err = io.StringIO()
        success = doctor.install_missing({"PATH": "/usr/bin"}, stdout=out, stderr=err)

        self.assertTrue(success)
        self.assertIn("No installable software packages are missing.", out.getvalue())

    @patch("sys.platform", "linux")
    @patch("authy_local.doctor.detect_linux_package_manager", return_value=None)
    def test_install_missing_unsupported_linux(self, mock_detect) -> None:
        out = io.StringIO()
        err = io.StringIO()
        success = doctor.install_missing({"PATH": "/usr/bin"}, stdout=out, stderr=err)

        self.assertFalse(success)
        self.assertIn(
            "Automatic install on Linux requires apt-get, pacman, or dnf.", err.getvalue()
        )


class TestDoctorCheckDiagnostics(unittest.TestCase):
    """Tests for doctor_check() structured return and recommendation engine."""

    def test_doctor_check_keys(self) -> None:
        res = doctor.doctor_check()
        for key in (
            "status",
            "report",
            "missing",
            "package_manager",
            "packages_to_install",
            "command",
            "recommendations",
            "healthy",
        ):
            self.assertIn(key, res)

    @patch("sys.platform", "linux")
    @patch(
        "authy_local.doctor.detect_linux_package_manager", return_value=("arch", "/usr/bin/pacman")
    )
    @patch("authy_local.doctor.report")
    @patch("os.geteuid", return_value=1000)
    def test_doctor_check_linux_remediation_command(
        self, mock_euid, mock_report, mock_detect
    ) -> None:
        mock_report.return_value = {
            "platform": {"state": "available"},
            "python": {"state": "available"},
            "op": {"state": "available"},
            "clock": {"state": "available"},
            "pam": {"state": "missing"},
        }
        res = doctor.doctor_check({"PATH": "/usr/bin"})
        self.assertEqual(res["package_manager"]["family"], "arch")
        self.assertEqual(res["packages_to_install"], ["pam"])
        self.assertTrue(res["command"][0].endswith("sudo"))
        self.assertEqual(res["command"][1:], ["/usr/bin/pacman", "-S", "--noconfirm", "pam"])
        self.assertTrue(any("pacman" in r for r in res["recommendations"]))
        self.assertFalse(res["healthy"])

    @patch("authy_local.doctor.report")
    def test_doctor_check_healthy_when_all_available(self, mock_report) -> None:
        mock_report.return_value = {
            "platform": {"state": "available"},
            "python": {"state": "available"},
            "op": {"state": "available"},
            "clock": {"state": "available"},
        }
        res = doctor.doctor_check({})
        self.assertTrue(res["healthy"])
        self.assertEqual(res["status"], 0)
        self.assertEqual(res["missing"], [])

    @patch("sys.platform", "darwin")
    @patch("shutil.which", return_value="/opt/homebrew/bin/brew")
    @patch("authy_local.doctor.report")
    def test_doctor_check_darwin_remediation(self, mock_report, mock_which) -> None:
        mock_report.return_value = {
            "platform": {"state": "available"},
            "python": {"state": "available"},
            "op": {"state": "available"},
            "clock": {"state": "available"},
            "fish": {"state": "missing"},
        }
        res = doctor.doctor_check({"PATH": "/opt/homebrew/bin"})
        self.assertEqual(res["package_manager"]["family"], "homebrew")
        self.assertEqual(res["packages_to_install"], ["fish"])
        self.assertEqual(res["command"], ["/opt/homebrew/bin/brew", "install", "fish"])
        self.assertTrue(any("brew install" in r for r in res["recommendations"]))

    @patch("sys.platform", "win32")
    @patch("shutil.which")
    @patch("authy_local.doctor.report")
    def test_doctor_check_windows_winget_remediation(self, mock_report, mock_which) -> None:
        mock_which.side_effect = lambda cmd, path="": "C:\\winget.exe" if cmd == "winget" else None
        mock_report.return_value = {
            "platform": {"state": "available"},
            "python": {"state": "available"},
            "op": {"state": "available"},
            "clock": {"state": "available"},
            "keepass": {"state": "missing"},
        }
        res = doctor.doctor_check({"PATH": "C:\\"})
        self.assertEqual(res["package_manager"]["family"], "winget")
        self.assertEqual(res["packages_to_install"], ["KeePassXCTeam.KeePassXC"])
        self.assertEqual(res["command"], ["C:\\winget.exe", "install", "KeePassXCTeam.KeePassXC"])

    @patch("authy_local.doctor.report")
    def test_doctor_check_clock_missing_recommendation(self, mock_report) -> None:
        mock_report.return_value = {
            "platform": {"state": "available"},
            "python": {"state": "available"},
            "op": {"state": "available"},
            "clock": {"state": "missing"},
        }
        res = doctor.doctor_check({})
        self.assertTrue(any("timedatectl" in r for r in res["recommendations"]))


class TestCliDoctorFlags(unittest.TestCase):
    """Tests for CLI doctor --fix and --install flag wiring."""

    @patch("authy_local.doctor.install_missing", return_value=True)
    @patch("authy_local.doctor.report")
    def test_cli_doctor_fix_triggers_install_missing(self, mock_report, mock_install) -> None:
        mock_report.return_value = {
            "platform": {"state": "available"},
            "python": {"state": "available"},
            "op": {"state": "available"},
            "clock": {"state": "available"},
        }
        stdout = io.StringIO()
        stderr = io.StringIO()
        exit_code = cli.main(["doctor", "--fix"], stdout=stdout, stderr=stderr)
        self.assertEqual(exit_code, 0)
        mock_install.assert_called_once()

    @patch("authy_local.doctor.install_missing", return_value=True)
    @patch("authy_local.doctor.report")
    def test_cli_doctor_install_triggers_install_missing(self, mock_report, mock_install) -> None:
        mock_report.return_value = {
            "platform": {"state": "available"},
            "python": {"state": "available"},
            "op": {"state": "available"},
            "clock": {"state": "available"},
        }
        stdout = io.StringIO()
        stderr = io.StringIO()
        exit_code = cli.main(["doctor", "--install"], stdout=stdout, stderr=stderr)
        self.assertEqual(exit_code, 0)
        mock_install.assert_called_once()

    @patch("sys.platform", "linux")
    def test_pbcopy_not_applicable_on_linux(self) -> None:
        rep = doctor.report({"PATH": "/usr/bin"})
        self.assertEqual(rep.get("pbcopy", {}).get("state"), "not-applicable")


if __name__ == "__main__":
    unittest.main()
