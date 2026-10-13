"""Tests for ephemeral session agent daemon and Unix domain socket IPC."""

import io
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from authy_local import cli
from authy_local.agent import SessionAgent, send_agent_request, socket_location


class TestSessionAgent(unittest.TestCase):
    def setUp(self):

        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_dir.name)
        self.secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_socket_location_permissions(self):
        sock = socket_location(self.home, create=True)
        self.assertTrue(sock.parent.exists())
        mode = sock.parent.stat().st_mode & 0o777
        self.assertEqual(mode, 0o700)

    def test_agent_cache_and_get_code(self):
        agent = SessionAgent(home=self.home, idle_timeout=60.0)
        agent.cache("aws", self.secret)

        res = agent.get_code("aws")
        self.assertIsNotNone(res)
        code, remaining = res
        self.assertEqual(len(code), 6)
        self.assertTrue(0 <= remaining <= 30)

        # Nonexistent key returns None
        self.assertIsNone(agent.get_code("missing_key"))

    def test_agent_lock_wipes_secrets(self):
        agent = SessionAgent(home=self.home, idle_timeout=60.0)
        agent.cache("aws", self.secret)
        self.assertEqual(len(agent._secrets), 1)

        agent.lock()
        self.assertTrue(agent._locked)
        self.assertEqual(len(agent._secrets), 0)
        self.assertIsNone(agent.get_code("aws"))

    def test_agent_server_and_client_communication(self):
        agent = SessionAgent(home=self.home, idle_timeout=60.0)
        t = threading.Thread(target=agent.run, daemon=True)
        t.start()

        # Wait for socket
        sock_path = socket_location(self.home)
        for _ in range(50):
            if sock_path.exists():
                break
            time.sleep(0.05)
        self.assertTrue(sock_path.exists())

        try:
            # Ping
            ping_resp = send_agent_request("ping", home=self.home)
            self.assertEqual(ping_resp.get("status"), "ok")
            self.assertFalse(ping_resp.get("locked"))

            # Cache
            cache_resp = send_agent_request(
                "cache", {"key": "github", "secret": self.secret}, home=self.home
            )
            self.assertEqual(cache_resp.get("status"), "ok")

            # Get Code
            code_resp = send_agent_request("get_code", {"key": "github"}, home=self.home)
            self.assertEqual(code_resp.get("status"), "ok")
            self.assertEqual(len(code_resp.get("code")), 6)

            # Lock
            lock_resp = send_agent_request("lock", home=self.home)
            self.assertEqual(lock_resp.get("status"), "locked")

            # Code after lock
            code_after = send_agent_request("get_code", {"key": "github"}, home=self.home)
            self.assertEqual(code_after.get("status"), "locked")

            # Status
            st_resp = send_agent_request("status", home=self.home)
            self.assertEqual(st_resp.get("status"), "ok")
            self.assertTrue(st_resp.get("locked"))
        finally:
            send_agent_request("stop", home=self.home)
            t.join(timeout=3.0)


class TestAgentCLI(unittest.TestCase):
    def invoke(self, args, **env):
        out, err = io.StringIO(), io.StringIO()
        out.isatty = lambda: True
        full_env = {
            "PATH": "/usr/bin:/bin",
            "HOME": "/tmp",
        } | env
        with patch.dict(os.environ, full_env, clear=True):
            status = cli.main(args, stdout=out, stderr=err)
        return status, out.getvalue(), err.getvalue()

    def test_agent_status_when_stopped(self):
        with patch("authy_local.agent.send_agent_request", return_value=None):
            status, out, err = self.invoke(["agent", "status"])
            self.assertEqual(status, 0)
            self.assertIn("not running", out)

    def test_agent_status_when_running(self):
        mock_resp = {"locked": False, "cached_count": 3, "idle_seconds": 12.5}
        with patch("authy_local.agent.send_agent_request", return_value=mock_resp):
            status, out, err = self.invoke(["agent", "status"])
            self.assertEqual(status, 0)
            self.assertIn("Agent Status: active", out)
            self.assertIn("Cached Secrets: 3", out)

    def test_agent_lock_command(self):
        with patch("authy_local.agent.send_agent_request", return_value={"status": "locked"}):
            status, out, err = self.invoke(["agent", "lock"])
            self.assertEqual(status, 0)
            self.assertIn("daemon locked", err)
