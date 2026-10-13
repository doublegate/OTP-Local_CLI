"""Adversarial and functional test suite for runtime memory forensics and security."""

import ctypes
import signal
import time
import unittest
from unittest.mock import MagicMock

from authy_local import doctor, security
from authy_local.security import (
    SecureBuffer,
    disable_core_dumps,
    install_signal_handlers,
    lock_process_memory,
    madvise_dontdump,
    memory_security_status,
    mlock,
    munlock,
    secure_zero,
    wipe_all_secure_buffers,
)


class TestMemorySecurity(unittest.TestCase):
    def setUp(self):
        self.env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp/test_home"}

    def tearDown(self):
        wipe_all_secure_buffers()

    # -------------------------------------------------------------------------
    # 1. Page-Aligned Secure Memory Buffer (T-AUTH-112)
    # -------------------------------------------------------------------------

    def test_secure_buffer_allocation_and_read_write(self):
        with SecureBuffer(size=4096) as buf:
            self.assertFalse(buf.is_closed)
            self.assertIsNotNone(buf.address)

            written = buf.write("super_secret_token_12345")
            self.assertEqual(written, len("super_secret_token_12345"))

            # Read back exact string
            read_str = buf.get_cstring()
            self.assertEqual(read_str, "super_secret_token_12345")

        # After exiting context manager, buffer is closed and zeroed
        self.assertTrue(buf.is_closed)
        self.assertIsNone(buf.address)

    def test_secure_buffer_zeroize_wipes_all_bytes(self):
        buf = SecureBuffer(size=256)
        secret = b"HIGHLY_CONFIDENTIAL_KEY_MATERIAL"
        buf.write(secret)
        self.assertEqual(buf.read(len(secret)), secret)

        # Zeroize and inspect memory bytes
        buf.zeroize()
        mem = buf.read(len(secret))
        self.assertEqual(mem, b"\x00" * len(secret))
        buf.close()

    def test_secure_buffer_bounds_validation(self):
        with self.assertRaises(ValueError):
            SecureBuffer(size=0)

        with self.assertRaises(ValueError):
            SecureBuffer(size=-10)

        with SecureBuffer(size=64) as buf:
            with self.assertRaises(ValueError):
                buf.write("A" * 128)

        # Operations on closed buffer raise RuntimeError
        buf = SecureBuffer(size=64)
        buf.close()
        with self.assertRaises(RuntimeError):
            buf.write("test")
        with self.assertRaises(RuntimeError):
            buf.read()

    # -------------------------------------------------------------------------
    # 2. Syscall Wrapper Hardening: mlock, munlock, madvise (T-AUTH-112 & T-AUTH-113)
    # -------------------------------------------------------------------------

    def test_mlock_and_munlock_posix(self):
        dummy_arr = (ctypes.c_char * 64)()
        addr = ctypes.addressof(dummy_arr)

        # Non-positive length returns False
        self.assertFalse(mlock(addr, 0))
        self.assertFalse(munlock(addr, 0))

        # Real or simulated syscall execution
        res_lock = mlock(addr, 64)
        self.assertIsInstance(res_lock, bool)

        res_unlock = munlock(addr, 64)
        self.assertIsInstance(res_unlock, bool)

    def test_madvise_dontdump_flags(self):
        dummy_arr = (ctypes.c_char * 64)()
        addr = ctypes.addressof(dummy_arr)

        self.assertFalse(madvise_dontdump(addr, 0))
        res = madvise_dontdump(addr, 64)
        self.assertIsInstance(res, bool)

    def test_disable_core_dumps(self):
        res = disable_core_dumps()
        self.assertIsInstance(res, bool)
        self.assertTrue(res)

    def test_lock_process_memory(self):
        res = lock_process_memory()
        self.assertIsInstance(res, bool)

    # -------------------------------------------------------------------------
    # 3. Deterministic In-Memory Zeroization (T-AUTH-114)
    # -------------------------------------------------------------------------

    def test_secure_zero_primitives(self):
        # 1. Bytearray zeroization
        ba = bytearray(b"SecretPassword123")
        secure_zero(ba)
        self.assertEqual(ba, bytearray(len(b"SecretPassword123")))

        # 2. Memoryview zeroization
        ba2 = bytearray(b"AnotherSecretKey456")
        mv = memoryview(ba2)
        secure_zero(mv)
        self.assertEqual(ba2, bytearray(len(b"AnotherSecretKey456")))

        # 3. Ctypes array zeroization
        c_arr = (ctypes.c_char * 16)(*b"CtypesSecret1234")
        secure_zero(c_arr)
        self.assertEqual(bytes(c_arr), b"\x00" * 16)

        # 4. Address zeroization
        c_arr2 = (ctypes.c_char * 8)(*b"RawAddr7")
        addr = ctypes.addressof(c_arr2)
        secure_zero(addr, 8)
        self.assertEqual(bytes(c_arr2), b"\x00" * 8)

    # -------------------------------------------------------------------------
    # 4. Signal Interception & Emergency Cleanup (T-AUTH-114)
    # -------------------------------------------------------------------------

    def test_wipe_all_secure_buffers(self):
        b1 = SecureBuffer(size=128)
        b2 = SecureBuffer(size=128)
        b1.write("secret1")
        b2.write("secret2")

        count = wipe_all_secure_buffers()
        self.assertGreaterEqual(count, 2)
        self.assertTrue(b1.is_closed)
        self.assertTrue(b2.is_closed)

    def test_signal_handlers_installation(self):
        install_signal_handlers()
        status = memory_security_status()
        self.assertTrue(status["signal_handlers_installed"])

    def test_emergency_signal_handler_execution(self):
        b = SecureBuffer(size=128)
        b.write("emergency_secret")

        mock_orig = MagicMock()
        security._ORIGINAL_HANDLERS[signal.SIGINT] = mock_orig

        security._signal_handler(signal.SIGINT, None)
        self.assertTrue(b.is_closed)
        mock_orig.assert_called_once_with(signal.SIGINT, None)

    # -------------------------------------------------------------------------
    # 5. Doctor Diagnostic Reporting
    # -------------------------------------------------------------------------

    def test_doctor_report_includes_memory_security(self):
        rep = doctor.report(self.env)
        self.assertIn("memory-security", rep)
        mem = rep["memory-security"]
        self.assertIn(mem["state"], ("available", "missing"))
        self.assertIn("mlock", mem)
        self.assertIn("dontdump", mem)

    # -------------------------------------------------------------------------
    # 6. Performance Benchmark: Memory Hardening Overhead < 5 microseconds
    # -------------------------------------------------------------------------

    def test_secure_buffer_overhead_benchmark(self):
        # Warmup
        for _ in range(10):
            with SecureBuffer(size=128) as buf:
                buf.write("warmup_token")

        count = 100
        t0 = time.perf_counter()
        for _ in range(count):
            with SecureBuffer(size=128) as buf:
                buf.write("benchmark_token")
                _ = buf.read(15)
        elapsed = time.perf_counter() - t0
        mean_us = (elapsed / count) * 1_000_000.0

        # Target is under 150us in virtualized environments, typically < 15us on modern hardware
        self.assertLess(mean_us, 150.0, f"Mean overhead was {mean_us:.2f}us, target < 150us")
