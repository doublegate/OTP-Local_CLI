"""Comprehensive automated test suite for native Linux PAM integration module."""

import ctypes
import ctypes.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from authy_local.cli import main
from authy_local.daemon import DaemonServer
from authy_local.enrollment import generate_totp_code, parse_secret_or_uri
from authy_local.ipc import send_ipc_request, socket_path
from authy_local.pam_check import (
    check_daemon_socket,
    doctor_pam_cli,
    generate_pam_snippet,
    inspect_pam_configurations,
    probe_pam_module_binary,
    probe_pam_subsystem,
    run_pam_doctor_check,
    validate_pam_config_syntax,
)

PAM_SUCCESS = 0
PAM_AUTH_ERR = 7
PAM_AUTHINFO_UNAVAIL = 9
PAM_USER_UNKNOWN = 10
PAM_CONV_ERR = 19


class PamMessage(ctypes.Structure):
    _fields_ = [("msg_style", ctypes.c_int), ("msg", ctypes.c_char_p)]


class PamResponse(ctypes.Structure):
    _fields_ = [("resp", ctypes.c_void_p), ("resp_retcode", ctypes.c_int)]


PAM_CONV_FUNC = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(ctypes.POINTER(PamMessage)),
    ctypes.POINTER(ctypes.POINTER(PamResponse)),
    ctypes.c_void_p,
)


class PamConv(ctypes.Structure):
    _fields_ = [("conv", PAM_CONV_FUNC), ("appdata_ptr", ctypes.c_void_p)]


@unittest.skipUnless(sys.platform == "linux", "Linux PAM module is specific to Linux platforms")
class TestPamIntegration(unittest.TestCase):
    """Test harness for pam_otp_local.so C module and python diagnostic tools."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pam_so_path = Path(__file__).resolve().parents[1] / "pam" / "pam_otp_local.so"
        if not cls.pam_so_path.exists():
            try:
                subprocess.run(
                    ["make", "-C", str(cls.pam_so_path.parent), "all"],
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError, OSError:
                tmp_build = Path(tempfile.gettempdir()) / "pam_otp_local_test"
                tmp_build.mkdir(exist_ok=True)
                cls.pam_so_path = tmp_build / "pam_otp_local.so"
                c_src = Path(__file__).resolve().parents[1] / "pam" / "pam_otp_local.c"
                try:
                    subprocess.run(
                        [
                            "gcc",
                            "-Wall",
                            "-Wextra",
                            "-O2",
                            "-fPIC",
                            "-fstack-protector-strong",
                            "-D_FORTIFY_SOURCE=2",
                            "-shared",
                            "-Wl,-z,relro,-z,now,-z,noexecstack",
                            str(c_src),
                            "-o",
                            str(cls.pam_so_path),
                            "-lpam",
                        ],
                        check=True,
                        capture_output=True,
                    )
                except (subprocess.CalledProcessError, OSError) as exc:
                    raise unittest.SkipTest(
                        f"Native Linux PAM module compilation failed: {exc}. "
                        "libpam development headers or gcc are missing on host."
                    ) from exc

        if not cls.pam_so_path.exists():
            raise unittest.SkipTest(f"pam_otp_local.so binary does not exist at {cls.pam_so_path}")

        libpam_name = ctypes.util.find_library("pam")
        if not libpam_name:
            raise unittest.SkipTest("libpam.so is not available on host system")
        try:
            cls.libpam = ctypes.CDLL(libpam_name)
        except OSError as exc:
            raise unittest.SkipTest(f"Failed to load libpam ({libpam_name}): {exc}") from exc

        libc_name = ctypes.util.find_library("c")
        if not libc_name:
            raise unittest.SkipTest("libc is not available on host system")
        try:
            cls.libc = ctypes.CDLL(libc_name)
        except OSError as exc:
            raise unittest.SkipTest(f"Failed to load libc ({libc_name}): {exc}") from exc
        cls.libc.strdup.restype = ctypes.c_void_p
        cls.libc.strdup.argtypes = [ctypes.c_char_p]
        cls.libc.malloc.restype = ctypes.c_void_p
        cls.libc.malloc.argtypes = [ctypes.c_size_t]

        try:
            cls.pam_mod = ctypes.CDLL(str(cls.pam_so_path))
        except OSError as exc:
            raise unittest.SkipTest(
                f"Failed to load compiled PAM module {cls.pam_so_path}: {exc}"
            ) from exc

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.test_sock = self.tmp_path / "test-otp.sock"
        self.test_pid = self.tmp_path / "test-otp.pid"
        self.test_shm = f"test-pam-shm-{os.getpid()}"
        self.env = {
            "HOME": str(self.tmp_path),
            "XDG_RUNTIME_DIR": str(self.tmp_path),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "USER": os.environ.get("USER", "testuser"),
        }

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _create_pam_handle(self, conv_func, username: str = "testuser"):
        pam_conv = PamConv(conv=conv_func, appdata_ptr=None)
        pamh = ctypes.c_void_p()
        u_bytes = username.encode("utf-8")
        rc = self.libpam.pam_start(b"sudo", u_bytes, ctypes.byref(pam_conv), ctypes.byref(pamh))
        self.assertEqual(rc, PAM_SUCCESS)
        return pamh, pam_conv

    def test_pam_subsystem_probing(self) -> None:
        """Verify probe_pam_subsystem correctly identifies Linux PAM infrastructure."""
        res = probe_pam_subsystem()
        self.assertEqual(res["state"], "available")
        self.assertTrue(len(res["headers"]) > 0 or len(res["security_dirs"]) > 0)

    def test_pam_module_binary_probing(self) -> None:
        """Verify probe_pam_module_binary finds compiled pam_otp_local.so."""
        res = probe_pam_module_binary(self.pam_so_path)
        self.assertEqual(res["state"], "available")
        self.assertTrue(res["path"].endswith("pam_otp_local.so"))

    def test_check_daemon_socket(self) -> None:
        """Verify check_daemon_socket correctly detects missing vs active sockets."""
        # 1. Missing socket
        res_missing = check_daemon_socket(self.env)
        self.assertEqual(res_missing["state"], "missing")

        # 2. Online socket
        target_sock = socket_path(self.env)
        server = DaemonServer(
            sock_path=target_sock,
            shm_name=self.test_shm,
            pid_file=self.test_pid,
            env=self.env,
        )
        t = threading.Thread(target=server.start, daemon=True)
        t.start()
        for _ in range(50):
            if target_sock.exists():
                break
            time.sleep(0.05)

        try:
            res_online = check_daemon_socket(self.env)
            self.assertEqual(res_online["state"], "available")
            self.assertEqual(res_online["ping"], "ok")
        finally:
            server._running = False
            t.join(timeout=2.0)
            server.cleanup()

    def test_pam_authentication_success_with_daemon(self) -> None:
        """Verify successful PAM authentication against running daemon with valid TOTP code."""
        server = DaemonServer(
            sock_path=self.test_sock,
            shm_name=self.test_shm,
            pid_file=self.test_pid,
            env=self.env,
        )
        t = threading.Thread(target=server.start, daemon=True)
        t.start()
        for _ in range(50):
            if self.test_sock.exists():
                break
            time.sleep(0.05)

        try:
            # Cache token for alice
            secret = "JBSWY3DPEHPK3PXP"
            cache_res = send_ipc_request(
                {"action": "cache_token", "account": "alice", "secret": secret},
                sock_path=self.test_sock,
            )
            self.assertEqual(cache_res["status"], "ok")

            params = parse_secret_or_uri(secret, fallback_label="alice")
            valid_code, _ = generate_totp_code(params)

            @PAM_CONV_FUNC
            def success_conv(num_msg, msg, resp_out, appdata):
                resp_ptr = self.libc.malloc(ctypes.sizeof(PamResponse) * num_msg)
                p_resp = ctypes.cast(resp_ptr, ctypes.POINTER(PamResponse))
                for i in range(num_msg):
                    p_resp[i].resp = self.libc.strdup(valid_code.encode("utf-8"))
                    p_resp[i].resp_retcode = 0
                resp_out[0] = p_resp
                return 0

            pamh, pam_conv = self._create_pam_handle(success_conv, username="alice")
            args = (ctypes.c_char_p * 3)(
                f"socket_path={self.test_sock}".encode("utf-8"),
                b"account=alice",
                b"debug",
            )

            rc = self.pam_mod.pam_sm_authenticate(pamh, 0, 3, args)
            self.assertEqual(rc, PAM_SUCCESS)

            cred_rc = self.pam_mod.pam_sm_setcred(pamh, 0, 3, args)
            self.assertEqual(cred_rc, PAM_SUCCESS)

            self.libpam.pam_end(pamh, rc)
        finally:
            server._running = False
            t.join(timeout=2.0)
            server.cleanup()

    def test_pam_authentication_rejected_incorrect_code(self) -> None:
        """Verify pam_sm_authenticate returns PAM_AUTH_ERR when given wrong code."""
        server = DaemonServer(
            sock_path=self.test_sock,
            shm_name=self.test_shm,
            pid_file=self.test_pid,
            env=self.env,
        )
        t = threading.Thread(target=server.start, daemon=True)
        t.start()
        for _ in range(50):
            if self.test_sock.exists():
                break
            time.sleep(0.05)

        try:
            send_ipc_request(
                {"action": "cache_token", "account": "bob", "secret": "JBSWY3DPEHPK3PXP"},
                sock_path=self.test_sock,
            )

            @PAM_CONV_FUNC
            def bad_code_conv(num_msg, msg, resp_out, appdata):
                resp_ptr = self.libc.malloc(ctypes.sizeof(PamResponse) * num_msg)
                p_resp = ctypes.cast(resp_ptr, ctypes.POINTER(PamResponse))
                for i in range(num_msg):
                    p_resp[i].resp = self.libc.strdup(b"000000")
                    p_resp[i].resp_retcode = 0
                resp_out[0] = p_resp
                return 0

            pamh, pam_conv = self._create_pam_handle(bad_code_conv, username="bob")
            args = (ctypes.c_char_p * 2)(
                f"socket_path={self.test_sock}".encode("utf-8"),
                b"debug",
            )

            rc = self.pam_mod.pam_sm_authenticate(pamh, 0, 2, args)
            self.assertEqual(rc, PAM_AUTH_ERR)
            self.libpam.pam_end(pamh, rc)
        finally:
            server._running = False
            t.join(timeout=2.0)
            server.cleanup()

    def test_pam_authentication_unknown_account(self) -> None:
        """Verify pam_sm_authenticate returns PAM_USER_UNKNOWN when account not cached."""
        server = DaemonServer(
            sock_path=self.test_sock,
            shm_name=self.test_shm,
            pid_file=self.test_pid,
            env=self.env,
        )
        t = threading.Thread(target=server.start, daemon=True)
        t.start()
        for _ in range(50):
            if self.test_sock.exists():
                break
            time.sleep(0.05)

        try:

            @PAM_CONV_FUNC
            def dummy_conv(num_msg, msg, resp_out, appdata):
                resp_ptr = self.libc.malloc(ctypes.sizeof(PamResponse) * num_msg)
                p_resp = ctypes.cast(resp_ptr, ctypes.POINTER(PamResponse))
                for i in range(num_msg):
                    p_resp[i].resp = self.libc.strdup(b"123456")
                    p_resp[i].resp_retcode = 0
                resp_out[0] = p_resp
                return 0

            pamh, pam_conv = self._create_pam_handle(dummy_conv, username="uncached_user")
            args = (ctypes.c_char_p * 2)(
                f"socket_path={self.test_sock}".encode("utf-8"),
                b"debug",
            )

            rc = self.pam_mod.pam_sm_authenticate(pamh, 0, 2, args)
            self.assertEqual(rc, PAM_USER_UNKNOWN)
            self.libpam.pam_end(pamh, rc)
        finally:
            server._running = False
            t.join(timeout=2.0)
            server.cleanup()

    def test_pam_fail_closed_daemon_offline(self) -> None:
        """Verify pam_sm_authenticate fails closed with PAM_AUTHINFO_UNAVAIL when socket offline."""

        @PAM_CONV_FUNC
        def dummy_conv(num_msg, msg, resp_out, appdata):
            resp_ptr = self.libc.malloc(ctypes.sizeof(PamResponse) * num_msg)
            p_resp = ctypes.cast(resp_ptr, ctypes.POINTER(PamResponse))
            for i in range(num_msg):
                p_resp[i].resp = self.libc.strdup(b"123456")
                p_resp[i].resp_retcode = 0
            resp_out[0] = p_resp
            return 0

        pamh, pam_conv = self._create_pam_handle(dummy_conv, username="anyone")
        nonexistent = self.tmp_path / "nonexistent.sock"
        args = (ctypes.c_char_p * 2)(
            f"socket_path={nonexistent}".encode("utf-8"),
            b"debug",
        )

        rc = self.pam_mod.pam_sm_authenticate(pamh, 0, 2, args)
        self.assertEqual(rc, PAM_AUTHINFO_UNAVAIL)
        self.libpam.pam_end(pamh, rc)

    def test_pam_conversation_failure(self) -> None:
        """Verify pam_sm_authenticate returns PAM_CONV_ERR when user cancels prompt."""

        @PAM_CONV_FUNC
        def failing_conv(num_msg, msg, resp_out, appdata):
            # User hit Ctrl+C or conversation error
            return 19  # PAM_CONV_ERR

        pamh, pam_conv = self._create_pam_handle(failing_conv, username="alice")
        args = (ctypes.c_char_p * 1)(f"socket_path={self.test_sock}".encode("utf-8"))

        rc = self.pam_mod.pam_sm_authenticate(pamh, 0, 1, args)
        self.assertEqual(rc, PAM_CONV_ERR)
        self.libpam.pam_end(pamh, rc)

    def test_pam_config_syntax_and_snippet_generation(self) -> None:
        """Verify PAM syntax checking and snippet generation."""
        # 1. Valid syntax
        valid_lines = [
            "# PAM sudo configuration",
            "auth    required    pam_unix.so",
            "auth    required    pam_otp_local.so try_first_pass",
            "account required    pam_unix.so",
        ]
        self.assertEqual(validate_pam_config_syntax(valid_lines), [])

        # 2. Invalid syntax errors
        invalid_lines = [
            "badtype required pam_otp_local.so",
            "auth badflag pam_otp_local.so",
            "auth required",  # missing module
        ]
        errs = validate_pam_config_syntax(invalid_lines)
        self.assertEqual(len(errs), 3)

        # 3. Snippet generation
        snippet = generate_pam_snippet("sshd", "sufficient", ["debug", "echo_code"])
        self.assertIn("auth    sufficient    pam_otp_local.so debug echo_code", snippet)

    def test_pam_configuration_inspection(self) -> None:
        """Verify inspect_pam_configurations finds pam_otp_local.so entries."""
        fake_pam_d = self.tmp_path / "pam.d"
        fake_pam_d.mkdir(parents=True)

        sudo_file = fake_pam_d / "sudo"
        sudo_file.write_text(
            "# Sudo pam config\nauth required pam_unix.so\nauth required pam_otp_local.so\n",
            encoding="utf-8",
        )

        res = inspect_pam_configurations(fake_pam_d)
        self.assertEqual(res["state"], "available")
        self.assertIn("sudo", res["matches"])
        self.assertEqual(res["matches"]["sudo"], ["auth required pam_otp_local.so"])

    def test_doctor_pam_cli_and_report(self) -> None:
        """Verify doctor_pam_cli structured text and JSON outputs."""
        # 1. Text report
        out_buf = io.StringIO()
        rc = doctor_pam_cli(self.env, stdout=out_buf, as_json=False)
        self.assertIn("OTP-Local Linux PAM Subsystem Diagnostics", out_buf.getvalue())
        self.assertIsInstance(rc, int)

        # 2. JSON report
        json_buf = io.StringIO()
        rc_json = doctor_pam_cli(self.env, stdout=json_buf, as_json=True)
        self.assertIsInstance(rc_json, int)
        data = json.loads(json_buf.getvalue())
        self.assertIn("subsystem", data)
        self.assertIn("binary", data)
        self.assertIn("daemon", data)
        self.assertIn("overall_status", data)

        # 3. Direct run_pam_doctor_check
        direct_rep = run_pam_doctor_check(self.env)
        self.assertEqual(direct_rep["overall_status"], data["overall_status"])

        # 3. CLI integration: main(["doctor", "--pam"])
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cli_rc = main(["doctor", "--pam"])
            self.assertIn("OTP-Local Linux PAM Subsystem Diagnostics", mock_out.getvalue())
            self.assertIsInstance(cli_rc, int)

        # 4. CLI integration: main(["doctor", "--pam", "--json"])
        with patch("sys.stdout", new_callable=io.StringIO) as mock_json_out:
            cli_json_rc = main(["doctor", "--pam", "--json"])
            parsed = json.loads(mock_json_out.getvalue())
            self.assertIn("overall_status", parsed)
            self.assertIsInstance(cli_json_rc, int)

    def test_pam_json_escaping_special_characters(self) -> None:
        """Verify accounts with quotes/backslashes and codes with special chars are escaped safely."""
        server = DaemonServer(
            sock_path=self.test_sock,
            shm_name=self.test_shm,
            pid_file=self.test_pid,
            env=self.env,
        )
        t = threading.Thread(target=server.start, daemon=True)
        t.start()
        for _ in range(50):
            if self.test_sock.exists():
                break
            time.sleep(0.05)

        try:
            # 1. Account with backslash (Active Directory style: DOMAIN\user)
            ad_account = r"DOMAIN\user"
            secret = "JBSWY3DPEHPK3PXP"
            cache_res = send_ipc_request(
                {"action": "cache_token", "account": ad_account, "secret": secret},
                sock_path=self.test_sock,
            )
            self.assertEqual(cache_res["status"], "ok")

            params = parse_secret_or_uri(secret, fallback_label=ad_account)
            valid_code, _ = generate_totp_code(params)

            @PAM_CONV_FUNC
            def ad_conv(num_msg, msg, resp_out, appdata):
                resp_ptr = self.libc.malloc(ctypes.sizeof(PamResponse) * num_msg)
                p_resp = ctypes.cast(resp_ptr, ctypes.POINTER(PamResponse))
                for i in range(num_msg):
                    p_resp[i].resp = self.libc.strdup(valid_code.encode("utf-8"))
                    p_resp[i].resp_retcode = 0
                resp_out[0] = p_resp
                return 0

            pamh, pam_conv = self._create_pam_handle(ad_conv, username=ad_account)
            args = (ctypes.c_char_p * 3)(
                f"socket_path={self.test_sock}".encode("utf-8"),
                f"account={ad_account}".encode("utf-8"),
                b"debug",
            )
            rc = self.pam_mod.pam_sm_authenticate(pamh, 0, 3, args)
            self.assertEqual(
                rc, PAM_SUCCESS, "Authentication failed on escaped backslash account name"
            )
            self.libpam.pam_end(pamh, rc)

            # 2. Account with double quote (alice"admin)
            quote_account = 'alice"admin'
            send_ipc_request(
                {"action": "cache_token", "account": quote_account, "secret": secret},
                sock_path=self.test_sock,
            )
            pamh2, pam_conv2 = self._create_pam_handle(ad_conv, username=quote_account)
            args2 = (ctypes.c_char_p * 3)(
                f"socket_path={self.test_sock}".encode("utf-8"),
                f"account={quote_account}".encode("utf-8"),
                b"debug",
            )
            rc2 = self.pam_mod.pam_sm_authenticate(pamh2, 0, 3, args2)
            self.assertEqual(
                rc2, PAM_SUCCESS, "Authentication failed on escaped quote account name"
            )
            self.libpam.pam_end(pamh2, rc2)

            # 3. Code containing special characters (must not crash daemon)
            @PAM_CONV_FUNC
            def malformed_conv(num_msg, msg, resp_out, appdata):
                resp_ptr = self.libc.malloc(ctypes.sizeof(PamResponse) * num_msg)
                p_resp = ctypes.cast(resp_ptr, ctypes.POINTER(PamResponse))
                for i in range(num_msg):
                    p_resp[i].resp = self.libc.strdup(b'123"456')
                    p_resp[i].resp_retcode = 0
                resp_out[0] = p_resp
                return 0

            pamh3, pam_conv3 = self._create_pam_handle(malformed_conv, username=ad_account)
            args3 = (ctypes.c_char_p * 3)(
                f"socket_path={self.test_sock}".encode("utf-8"),
                f"account={ad_account}".encode("utf-8"),
                b"debug",
            )
            rc3 = self.pam_mod.pam_sm_authenticate(pamh3, 0, 3, args3)
            self.assertEqual(rc3, PAM_AUTH_ERR)
            self.libpam.pam_end(pamh3, rc3)
        finally:
            server._running = False
            t.join(timeout=2.0)
            server.cleanup()

    def test_pam_concurrent_authentication_threads(self) -> None:
        """Verify multiple threads can authenticate simultaneously against the daemon."""
        server = DaemonServer(
            sock_path=self.test_sock,
            shm_name=self.test_shm,
            pid_file=self.test_pid,
            env=self.env,
        )
        t = threading.Thread(target=server.start, daemon=True)
        t.start()
        for _ in range(50):
            if self.test_sock.exists():
                break
            time.sleep(0.05)

        try:
            secret = "JBSWY3DPEHPK3PXP"
            send_ipc_request(
                {"action": "cache_token", "account": "conc_user", "secret": secret},
                sock_path=self.test_sock,
            )
            params = parse_secret_or_uri(secret, fallback_label="conc_user")
            valid_code, _ = generate_totp_code(params)

            def auth_worker():
                @PAM_CONV_FUNC
                def c_conv(num_msg, msg, resp_out, appdata):
                    resp_ptr = self.libc.malloc(ctypes.sizeof(PamResponse) * num_msg)
                    p_resp = ctypes.cast(resp_ptr, ctypes.POINTER(PamResponse))
                    for i in range(num_msg):
                        p_resp[i].resp = self.libc.strdup(valid_code.encode("utf-8"))
                        p_resp[i].resp_retcode = 0
                    resp_out[0] = p_resp
                    return 0

                pamh, pam_conv = self._create_pam_handle(c_conv, username="conc_user")
                args = (ctypes.c_char_p * 3)(
                    f"socket_path={self.test_sock}".encode("utf-8"),
                    b"account=conc_user",
                    b"debug",
                )
                rc = self.pam_mod.pam_sm_authenticate(pamh, 0, 3, args)
                self.libpam.pam_end(pamh, rc)
                return rc

            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                futures = [ex.submit(auth_worker) for _ in range(8)]
                results = [f.result() for f in futures]

            self.assertEqual(len(results), 8)
            for r in results:
                self.assertEqual(r, PAM_SUCCESS)
        finally:
            server._running = False
            t.join(timeout=2.0)
            server.cleanup()


if __name__ == "__main__":
    unittest.main()
