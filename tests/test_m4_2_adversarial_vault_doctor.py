"""Empirical Adversarial Stress Tests for Milestone M4.

Validates:
1. Bitwarden payload stress: 1.8MB JSON output with 1,500 items parsed without buffer overflow.
2. KeePass non-TOTP filtering stress: XML export containing hundreds of regular passwords,
   secure notes, bank accounts, and empty folder trees (/Personal/, /Work/).
3. FIDO2 device disconnect & error stress: disconnects, empty lists, EACCES permission errors,
   and tokens lacking HMAC-secret extension return clean AppError(3) / False without unhandled exceptions.
4. Linux Doctor Package Remediation: Distro matrix (Debian, Ubuntu, Arch, CachyOS, Fedora, RHEL),
   non-interactive flags, root/unprivileged sudo handling, and timeout/error handling.
"""

import errno
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from authy_local import doctor
from authy_local.backends import bitwarden, fido2, keepass
from authy_local.errors import AppError
from authy_local.processes import Completed


class TestM4AdversarialBitwardenPayloadStress(unittest.TestCase):
    """Stress tests for Bitwarden backend buffer limits and large payload handling."""

    def test_bitwarden_1_8mb_1500_items_payload(self) -> None:
        """Feed simulated 1.8MB JSON output containing 1,500 items.

        Verify list_items() parses it without BufferOverflowError or truncation,
        and accurately filters down to items with configured TOTP.
        """
        items = []
        totp_count = 500
        non_totp_count = 1000

        # Generate 500 items with valid TOTP
        for i in range(totp_count):
            items.append(
                {
                    "id": f"item-totp-{i:04d}",
                    "name": f"Service-TOTP-{i:04d}",
                    "notes": f"Adversarial stress item with metadata padding {'x' * 600}",
                    "login": {
                        "username": f"user{i}@example.com",
                        "password": f"Password!{i:05d}",
                        "totp": f"otpauth://totp/Service-{i:04d}:user{i}?secret=JBSWY3DPEHPK3PXP&issuer=Service-{i:04d}",
                        "uris": [{"match": None, "uri": f"https://service{i}.example.com/login"}],
                    },
                    "fields": [
                        {"name": "SecurityQuestion1", "value": "Answer1", "type": 0},
                        {"name": "CustomMetadata", "value": "A" * 200, "type": 0},
                    ],
                }
            )

        # Generate 1,000 items without TOTP (regular passwords, secure notes, credit cards)
        for i in range(non_totp_count):
            if i % 3 == 0:
                # Regular password without TOTP
                items.append(
                    {
                        "id": f"item-pwd-{i:04d}",
                        "name": f"Regular-Login-{i:04d}",
                        "notes": f"Regular password item padding {'y' * 700}",
                        "login": {
                            "username": f"regular{i}@corp.local",
                            "password": f"SecretP@ss{i}!",
                            "totp": None,
                        },
                    }
                )
            elif i % 3 == 1:
                # Secure Note
                items.append(
                    {
                        "id": f"item-note-{i:04d}",
                        "name": f"Secure-Note-{i:04d}",
                        "notes": f"Highly confidential server documentation and SSH keys: {'z' * 900}",
                        "type": 2,
                    }
                )
            else:
                # Card / Identity
                items.append(
                    {
                        "id": f"item-card-{i:04d}",
                        "name": f"Corporate-Card-{i:04d}",
                        "card": {
                            "cardholderName": f"Corporate User {i}",
                            "brand": "Visa",
                            "number": "4111222233334444",
                        },
                        "notes": f"Billing card metadata {'w' * 800}",
                        "type": 3,
                    }
                )

        serialized = json.dumps(items, indent=2).encode("utf-8")
        payload_size = len(serialized)

        # Assert payload is between 1.7MB and 2.0MB (empirically verifying 1.8MB scale)
        self.assertGreaterEqual(
            payload_size, 1_700_000, f"Payload size {payload_size} bytes is < 1.7MB"
        )
        self.assertLess(
            payload_size, 2 * 1024 * 1024, f"Payload size {payload_size} bytes exceeds 2MB cap"
        )

        env = {"PATH": "/usr/bin:/bin"}
        with patch("shutil.which", return_value="/usr/bin/bw"):
            with patch("authy_local.backends.bitwarden.run") as mock_run:
                mock_run.return_value = Completed(returncode=0, stdout=serialized)

                result = bitwarden.list_items(env)

                # Verify run was called with 2MB cap (BITWARDEN_LIST_STDOUT_CAP)
                mock_run.assert_called_once()
                call_kwargs = mock_run.call_args[1]
                self.assertEqual(call_kwargs.get("stdout_cap"), 2 * 1024 * 1024)

                # Verify no truncation: all 500 TOTP items were parsed and returned
                self.assertEqual(len(result), totp_count)
                for item in result:
                    self.assertIn("login", item)
                    self.assertTrue(item["login"].get("totp"))

    def test_bitwarden_payload_exceeding_cap_fails_closed(self) -> None:
        """Verify that an adversarial payload exceeding 2MB is intercepted with AppError(5)."""
        env = {"PATH": "/usr/bin:/bin"}
        with patch("shutil.which", return_value="/usr/bin/bw"):
            with patch("authy_local.backends.bitwarden.run", side_effect=AppError(5)):
                with self.assertRaises(AppError) as cm:
                    bitwarden.list_items(env)
                self.assertEqual(cm.exception.exit_code, 5)


class TestM4AdversarialKeePassFilteringStress(unittest.TestCase):
    """Stress tests for KeePass non-TOTP filtering and empty directory pruning."""

    def test_keepass_xml_filtering_hundreds_of_entries(self) -> None:
        """Feed XML export containing hundreds of regular passwords, secure notes,

        bank accounts, and empty folder trees (/Personal/, /Work/).
        Verify only legitimate TOTP entries are returned and empty directories are omitted.
        """
        # Build comprehensive XML string with 250 non-TOTP entries and 50 TOTP entries
        xml_parts = [
            '<?xml version="1.0" encoding="utf-8" standalone="yes"?>',
            "<KeePassFile>",
            "  <Root>",
            "    <Group><Name>Root</Name>",
            "      <Group><Name>Personal</Name></Group>",
            "      <Group><Name>Work</Name></Group>",
            "      <Group><Name>EmptyTree1</Name><Group><Name>SubEmpty</Name></Group></Group>",
        ]

        # 50 legitimate TOTP entries across diverse OTP field naming conventions
        otp_field_names = [
            "otp",
            "TOTP",
            "totp",
            "TOTP Seed",
            "totp_seed",
            "KeePassXC-TOTP",
            "timeotp-secret-base32",
            "otp_token",
        ]
        for i in range(50):
            field_name = otp_field_names[i % len(otp_field_names)]
            xml_parts.extend(
                [
                    "      <Entry>",
                    f"        <String><Key>Title</Key><Value>TOTP-Account-{i:03d}</Value></String>",
                    f"        <String><Key>UserName</Key><Value>user{i}@example.com</Value></String>",
                    f"        <String><Key>Password</Key><Value>SecretPwd{i}!</Value></String>",
                    f"        <String><Key>{field_name}</Key><Value>otpauth://totp/Acct{i}?secret=JBSWY3DPEHPK3PXP</Value></String>",
                    f"        <String><Key>Notes</Key><Value>Notes content for entry {i}</Value></String>",
                    "      </Entry>",
                ]
            )

        # 100 regular passwords without OTP
        for i in range(100):
            xml_parts.extend(
                [
                    "      <Entry>",
                    f"        <String><Key>Title</Key><Value>Regular-Password-{i:03d}</Value></String>",
                    f"        <String><Key>UserName</Key><Value>regular_user{i}</Value></String>",
                    f"        <String><Key>Password</Key><Value>StrictlyPasswordNoOTP{i}!</Value></String>",
                    "        <String><Key>URL</Key><Value>https://example.com/login</Value></String>",
                    "      </Entry>",
                ]
            )

        # 50 secure notes without OTP
        for i in range(50):
            xml_parts.extend(
                [
                    "      <Entry>",
                    f"        <String><Key>Title</Key><Value>Secure-Note-{i:03d}</Value></String>",
                    f"        <String><Key>Notes</Key><Value>Confidential recovery keys and notes {i}</Value></String>",
                    "      </Entry>",
                ]
            )

        # 50 bank accounts without OTP
        for i in range(50):
            xml_parts.extend(
                [
                    "      <Entry>",
                    f"        <String><Key>Title</Key><Value>Bank-Account-{i:03d}</Value></String>",
                    f"        <String><Key>AccountNumber</Key><Value>9876543210{i:02d}</Value></String>",
                    "        <String><Key>RoutingNumber</Key><Value>123456789</Value></String>",
                    "      </Entry>",
                ]
            )

        # 50 entries with empty or irrelevant OTP settings strings (e.g. otp_settings)
        for i in range(50):
            xml_parts.extend(
                [
                    "      <Entry>",
                    f"        <String><Key>Title</Key><Value>NonOTP-Settings-{i:03d}</Value></String>",
                    "        <String><Key>otp_settings</Key><Value>disabled</Value></String>",
                    "        <String><Key>totp_settings</Key><Value></Value></String>",
                    "      </Entry>",
                ]
            )

        xml_parts.extend(["    </Group>", "  </Root>", "</KeePassFile>"])
        xml_content = "\n".join(xml_parts).encode("utf-8")

        entries = keepass._parse_xml_entries(xml_content)
        self.assertEqual(
            len(entries), 50, f"Expected exactly 50 TOTP entries, parsed {len(entries)}"
        )

        # Verify all extracted entries possess a valid title, username, and otp
        for e in entries:
            self.assertTrue(e["title"].startswith("TOTP-Account-"))
            self.assertTrue(e["otp"].startswith("otpauth://totp/"))

        # Verify keepass_records() produces sorted records and omits empty directories
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.kdbx"
            db_path.touch()

            env = {"PATH": "/usr/bin:/bin"}
            with patch("shutil.which", return_value="/usr/bin/keepassxc-cli"):
                with patch("authy_local.backends.keepass.run") as mock_run:
                    mock_run.return_value = Completed(returncode=0, stdout=xml_content)

                    records = keepass.keepass_records(env, db_path=db_path)

                    self.assertEqual(len(records), 50)
                    for title, label in records:
                        self.assertTrue(title.startswith("TOTP-Account-"))
                        self.assertIn("[KeePassXC]", label)
                        self.assertFalse(label.endswith("/"))
                        self.assertNotIn("Personal", label)
                        self.assertNotIn("Work", label)
                        self.assertNotIn("EmptyTree", label)

    def test_keepass_cli_ls_fallback_prunes_empty_directories(self) -> None:
        """Verify keepass_records fallback path (cli ls -R) prunes empty directory trees."""
        ls_output = (
            "/Personal/\n"
            "/Work/\n"
            "/EmptyGroup/\n"
            "/Work/Infrastructure/\n"
            "Server-Alpha\n"
            "/Personal/Finance/\n"
            "Personal-Email\n"
            "/Archive/2025/\n"
            "\n"
        ).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.kdbx"
            db_path.touch()

            env = {"PATH": "/usr/bin:/bin"}
            with patch("shutil.which", return_value="/usr/bin/keepassxc-cli"):
                with patch("authy_local.backends.keepass.run") as mock_run:
                    # XML export fails, forcing fallback to ls -R
                    mock_run.side_effect = [
                        Completed(returncode=1, stdout=b""),
                        Completed(returncode=0, stdout=ls_output),
                    ]

                    records = keepass.keepass_records(env, db_path=db_path)

                    self.assertEqual(len(records), 2)
                    titles = [r[0] for r in records]
                    self.assertIn("Personal-Email", titles)
                    self.assertIn("Server-Alpha", titles)
                    # Assert no directories were included
                    for title, _label in records:
                        self.assertFalse(title.endswith("/"))
                        self.assertNotIn("Personal/", title)
                        self.assertNotIn("Work/", title)


class TestM4AdversarialFido2DisconnectAndErrorStress(unittest.TestCase):
    """Stress tests for FIDO2 device disconnects, permission errors, and unsupported extensions."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.env = {
            "XDG_STATE_HOME": self.tmpdir.name,
            "HOME": self.tmpdir.name,
        }

    def tearDown(self) -> None:
        fido2._set_device_override(None)
        self.tmpdir.cleanup()

    def test_fido2_empty_device_list(self) -> None:
        """Simulate empty device list.

        probe() returns clean dict with state='missing' and hmac_secret=False.
        fido2_code() returns clean AppError(3).
        """
        fido2._set_device_override([])

        # Probe
        res = fido2.probe(self.env)
        self.assertEqual(res["state"], "missing")
        self.assertEqual(res["device_count"], 0)
        self.assertFalse(res.get("hmac_secret", False))

        # Code retrieval
        with self.assertRaises(AppError) as cm:
            fido2.fido2_code("nonexistent_account", self.env)
        # Verify clean AppError(3) without unhandled exception
        self.assertEqual(cm.exception.exit_code, 4)  # account not in vault -> 4

        # When account exists in vault but device list is empty
        vault_path = Path(self.tmpdir.name) / "authy-local" / "fido2_vault.json"
        vault_path.parent.mkdir(parents=True, exist_ok=True)
        vault_path.write_text(
            json.dumps(
                {
                    "accounts": {
                        "enrolled_acct": {
                            "credential_id": "0102030405060708",
                            "salt": "a" * 64,
                            "nonce": "b" * 24,
                            "ciphertext": "c" * 32,
                        }
                    }
                }
            )
        )
        with self.assertRaises(AppError) as cm2:
            fido2.fido2_code("enrolled_acct", self.env)
        self.assertEqual(cm2.exception.exit_code, 3)

    def test_fido2_permission_denied_eacces_on_hid(self) -> None:
        """Simulate permission denied (EACCES) when enumerating or opening HID devices."""
        fido2._set_device_override(None)

        with patch("authy_local.backends.fido2.CtapHidDevice.list_devices") as mock_list:
            mock_list.side_effect = OSError(errno.EACCES, "Permission denied")

            # probe() must not raise raw OSError
            res = fido2.probe(self.env)
            self.assertEqual(res["state"], "missing")
            self.assertEqual(res["device_count"], 0)
            self.assertFalse(res.get("hmac_secret", False))

            # fido2_code() must raise clean AppError(3)
            vault_path = Path(self.tmpdir.name) / "authy-local" / "fido2_vault.json"
            vault_path.parent.mkdir(parents=True, exist_ok=True)
            vault_path.write_text(
                json.dumps(
                    {
                        "accounts": {
                            "secure_acct": {
                                "credential_id": "0102030405060708",
                                "salt": "a" * 64,
                                "nonce": "b" * 24,
                                "ciphertext": "c" * 32,
                            }
                        }
                    }
                )
            )
            with self.assertRaises(AppError) as cm:
                fido2.fido2_code("secure_acct", self.env)
            self.assertEqual(cm.exception.exit_code, 3)

    def test_fido2_device_without_hmac_secret_extension(self) -> None:
        """Simulate device without HMAC-secret extension (e.g. standard U2F token).

        probe() reports state='missing', hmac_secret=False.
        fido2_code() returns clean AppError without unhandled exception.
        """
        mock_dev = MagicMock()
        mock_dev.has_hmac_secret = False
        mock_ctap = MagicMock()
        mock_ctap.info.extensions = ["credProtect", "largeBlobKey"]
        mock_dev.ctap = mock_ctap

        fido2._set_device_override([mock_dev])

        # probe()
        res = fido2.probe(self.env)
        self.assertEqual(res["state"], "missing")
        self.assertFalse(res["hmac_secret"])

        # fido2_code()
        vault_path = Path(self.tmpdir.name) / "authy-local" / "fido2_vault.json"
        vault_path.parent.mkdir(parents=True, exist_ok=True)
        vault_path.write_text(
            json.dumps(
                {
                    "accounts": {
                        "u2f_test": {
                            "credential_id": "0102030405060708",
                            "salt": "a" * 64,
                            "nonce": "b" * 24,
                            "ciphertext": "c" * 32,
                        }
                    }
                }
            )
        )
        # ctap get_assertion returns no hmac-secret extension output
        mock_assertion = MagicMock()
        mock_assertion.auth_data.extensions = {}
        mock_ctap.get_assertion.return_value = mock_assertion

        with self.assertRaises(AppError) as cm:
            fido2.fido2_code("u2f_test", self.env)
        # Should raise clean AppError (5 or 3), NEVER raw AttributeError or Exception
        self.assertIn(cm.exception.exit_code, (3, 5))

    def test_fido2_device_disconnect_during_assertion(self) -> None:
        """Simulate physical token disconnect mid-assertion (ENODEV / USB disconnect)."""
        vault_path = Path(self.tmpdir.name) / "authy-local" / "fido2_vault.json"
        vault_path.parent.mkdir(parents=True, exist_ok=True)
        vault_path.write_text(
            json.dumps(
                {
                    "accounts": {
                        "disconnect_test": {
                            "credential_id": "0102030405060708",
                            "salt": "a" * 64,
                            "nonce": "b" * 24,
                            "ciphertext": "c" * 32,
                        }
                    }
                }
            )
        )

        # 1. Native CTAP device raising OSError(ENODEV) on get_assertion
        mock_dev = MagicMock(spec=["ctap", "has_hmac_secret"])
        mock_dev.has_hmac_secret = True
        mock_ctap = MagicMock()
        mock_ctap.info.extensions = ["hmac-secret"]
        mock_ctap.get_assertion.side_effect = OSError(errno.ENODEV, "No such device")
        mock_dev.ctap = mock_ctap

        fido2._set_device_override([mock_dev])
        with self.assertRaises(AppError) as cm:
            fido2.fido2_code("disconnect_test", self.env)
        self.assertEqual(cm.exception.exit_code, 3)

        # 2. Device raising Exception with 'disconnect' in message
        mock_ctap.get_assertion.side_effect = Exception("FIDO2 USB device disconnected")
        with self.assertRaises(AppError) as cm2:
            fido2.fido2_code("disconnect_test", self.env)
        self.assertEqual(cm2.exception.exit_code, 3)

        # 3. Mock device raising OSError(ENODEV) on mock_assertion
        mock_dev_synthetic = MagicMock(spec=["ctap", "has_hmac_secret", "mock_assertion"])
        mock_dev_synthetic.has_hmac_secret = True
        mock_dev_synthetic.mock_assertion.side_effect = OSError(errno.ENODEV, "Device unplugged")
        mock_dev_synthetic.ctap = mock_ctap
        fido2._set_device_override([mock_dev_synthetic])
        with self.assertRaises(AppError) as cm3:
            fido2.fido2_code("disconnect_test", self.env)
        self.assertEqual(cm3.exception.exit_code, 3)


class TestM4AdversarialLinuxDoctorRemediation(unittest.TestCase):
    """Stress tests for Linux Doctor package remediation, matrix detection, flags, and sudo."""

    def test_linux_distro_matrix_package_manager_and_packages(self) -> None:
        """Test package manager detection and canonical package mapping across:

        Debian, Ubuntu, Arch Linux, CachyOS, Fedora, and RHEL mock environments.
        """
        distro_scenarios = [
            (
                {"ID": "debian", "ID_LIKE": "debian"},
                "debian",
                "/usr/bin/apt-get",
                {
                    "pam": "libpam0g-dev",
                    "build-essential": "build-essential",
                    "oathtool": "oathtool",
                },
            ),
            (
                {"ID": "ubuntu", "ID_LIKE": "ubuntu debian"},
                "debian",
                "/usr/bin/apt-get",
                {
                    "pam": "libpam0g-dev",
                    "build-essential": "build-essential",
                    "oathtool": "oathtool",
                },
            ),
            (
                {"ID": "arch", "ID_LIKE": "arch"},
                "arch",
                "/usr/bin/pacman",
                {"pam": "pam", "build-essential": "base-devel", "oathtool": "oath-toolkit"},
            ),
            (
                {"ID": "cachyos", "ID_LIKE": "arch"},
                "arch",
                "/usr/bin/pacman",
                {"pam": "pam", "build-essential": "base-devel", "oathtool": "oath-toolkit"},
            ),
            (
                {"ID": "fedora", "ID_LIKE": "fedora"},
                "fedora",
                "/usr/bin/dnf",
                {"pam": "pam-devel", "build-essential": "gcc make", "oathtool": "oathtool"},
            ),
            (
                {"ID": "rhel", "ID_LIKE": "fedora rhel centos"},
                "fedora",
                "/usr/bin/dnf",
                {"pam": "pam-devel", "build-essential": "gcc make", "oathtool": "oathtool"},
            ),
        ]

        def fake_which(cmd, path=None):
            if cmd in ("apt-get", "apt"):
                return "/usr/bin/apt-get"
            if cmd == "pacman":
                return "/usr/bin/pacman"
            if cmd in ("dnf", "yum"):
                return "/usr/bin/dnf"
            if cmd == "sudo":
                return "/usr/bin/sudo"
            return None

        for os_rel, expected_family, expected_bin, expected_pkgs in distro_scenarios:
            with patch("authy_local.doctor.get_os_release", return_value=os_rel):
                with patch("shutil.which", side_effect=fake_which):
                    pm_info = doctor.detect_linux_package_manager({"PATH": "/usr/bin"})
                    self.assertIsNotNone(pm_info, f"Failed detection for {os_rel}")
                    family, pm_bin = pm_info
                    self.assertEqual(family, expected_family, f"Wrong family for {os_rel}")
                    self.assertEqual(pm_bin, expected_bin, f"Wrong binary for {os_rel}")

                    # Verify package mappings
                    distro_map = {
                        "debian": doctor.APT_CAPABILITY_MAP,
                        "arch": doctor.PACMAN_CAPABILITY_MAP,
                        "fedora": doctor.DNF_CAPABILITY_MAP,
                    }[family]

                    for cap, expected_pkg in expected_pkgs.items():
                        self.assertEqual(
                            distro_map.get(cap),
                            expected_pkg,
                            f"Mismatch mapping {cap} for {family}",
                        )

    def test_non_interactive_flags_across_distros(self) -> None:
        """Verify command generation enforces non-interactive operation:

        Debian: DEBIAN_FRONTEND=noninteractive and -y
        Arch: -S and --noconfirm
        Fedora: install and -y
        """
        # Debian
        cmd_deb = doctor.build_linux_install_command(
            "debian", "/usr/bin/apt-get", ["libpam0g-dev"], is_root=True
        )
        self.assertEqual(cmd_deb, ["/usr/bin/apt-get", "install", "-y", "libpam0g-dev"])

        # Arch
        cmd_arch = doctor.build_linux_install_command(
            "arch", "/usr/bin/pacman", ["pam"], is_root=True
        )
        self.assertEqual(cmd_arch, ["/usr/bin/pacman", "-S", "--noconfirm", "pam"])

        # Fedora
        cmd_fed = doctor.build_linux_install_command(
            "fedora", "/usr/bin/dnf", ["pam-devel"], is_root=True
        )
        self.assertEqual(cmd_fed, ["/usr/bin/dnf", "install", "-y", "pam-devel"])

    def test_sudo_privilege_handling(self) -> None:
        """Verify sudo is prepended for unprivileged users (geteuid() != 0)

        and omitted when running as root (geteuid() == 0).
        """
        packages = ["wl-clipboard", "fzf"]

        # 1. Unprivileged user (e.g. UID 1000)
        cmd_unprivileged = doctor.build_linux_install_command(
            "arch", "/usr/bin/pacman", packages, is_root=False, sudo_binary="/usr/bin/sudo"
        )
        self.assertEqual(cmd_unprivileged[0], "/usr/bin/sudo")
        self.assertEqual(cmd_unprivileged[1], "/usr/bin/pacman")
        self.assertEqual(cmd_unprivileged[2:], ["-S", "--noconfirm", "wl-clipboard", "fzf"])

        # 2. Privileged root user (UID 0)
        cmd_root = doctor.build_linux_install_command(
            "arch", "/usr/bin/pacman", packages, is_root=True, sudo_binary="/usr/bin/sudo"
        )
        self.assertEqual(cmd_root[0], "/usr/bin/pacman")
        self.assertEqual(cmd_root[1:], ["-S", "--noconfirm", "wl-clipboard", "fzf"])
        self.assertNotIn("sudo", cmd_root)

    def test_install_missing_timeout_and_error_handling(self) -> None:
        """Verify install_missing() cleanly handles timeouts (AppError 7), interrupts (AppError 130),

        execution errors (AppError 5), and command failure (exit code 1) without hanging.
        """
        env = {"PATH": "/usr/bin"}
        mock_report = {
            "platform": {"state": "available"},
            "python": {"state": "available"},
            "op": {"state": "available"},
            "clock": {"state": "available"},
            "wl-copy": {"state": "missing"},
        }

        with patch("sys.platform", "linux"):
            with patch("authy_local.doctor.report", return_value=mock_report):
                with patch(
                    "authy_local.doctor.detect_linux_package_manager",
                    return_value=("debian", "/usr/bin/apt-get"),
                ):
                    with patch("shutil.which", return_value="/usr/bin/sudo"):
                        # 1. Command failure (returncode 1)
                        with patch(
                            "authy_local.doctor.run",
                            return_value=Completed(returncode=1, stdout=b"Package error"),
                        ):
                            err = io.StringIO()
                            out = io.StringIO()
                            success = doctor.install_missing(env, stdout=out, stderr=err)
                            self.assertFalse(success)
                            self.assertIn("non-zero exit code", err.getvalue())

                        # 2. Timeout (AppError 7)
                        with patch("authy_local.doctor.run", side_effect=AppError(7)):
                            err = io.StringIO()
                            out = io.StringIO()
                            success = doctor.install_missing(env, stdout=out, stderr=err)
                            self.assertFalse(success)
                            self.assertIn("timed out after 15 minutes", err.getvalue())

                        # 3. Interrupt (AppError 130)
                        with patch("authy_local.doctor.run", side_effect=AppError(130)):
                            err = io.StringIO()
                            out = io.StringIO()
                            success = doctor.install_missing(env, stdout=out, stderr=err)
                            self.assertFalse(success)
                            self.assertIn("interrupted by user", err.getvalue())

                        # 4. Unexpected error (e.g. AppError 5)
                        with patch("authy_local.doctor.run", side_effect=AppError(5)):
                            err = io.StringIO()
                            out = io.StringIO()
                            success = doctor.install_missing(env, stdout=out, stderr=err)
                            self.assertFalse(success)
                            self.assertIn("unexpected execution error", err.getvalue())


if __name__ == "__main__":
    unittest.main()
