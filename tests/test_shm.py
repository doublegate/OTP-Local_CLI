"""Dedicated automated test suite for POSIX shared memory circular ring buffer.

Tests atomic spinlock/flock synchronization, seqlock write ordering protocol,
bounded active count on overwrites, linear collision probing, and zero-copy latency.
"""

import concurrent.futures
import os
import struct
import threading
import time
import unittest

from authy_local.shm import (
    HEADER_FMT,
    SLOT_COUNT,
    ShmRingBuffer,
    _account_hash,
)


class TestShmRingBuffer(unittest.TestCase):
    def setUp(self) -> None:
        self.shm_name = f"test-shm-{os.getpid()}-{time.time_ns() % 1000000}"
        self.shm = ShmRingBuffer(name=self.shm_name, create=True)

    def tearDown(self) -> None:
        if self.shm is not None:
            self.shm.unlink()

    def test_shm_header_initialization(self) -> None:
        """Verify magic, version, spinlock (0), sequence (0), active count (0)."""
        magic, version, spinlock, slots, seq, count, _ = struct.unpack_from(
            HEADER_FMT, self.shm.buf, 0
        )
        self.assertEqual(magic, b"OTPS")
        self.assertEqual(version, 1)
        self.assertEqual(spinlock, 0)
        self.assertEqual(slots, SLOT_COUNT)
        self.assertEqual(seq, 0)
        self.assertEqual(count, 0)
        self.assertEqual(self.shm.sequence, 0)
        self.assertEqual(self.shm.active_count, 0)

    def test_shm_seqlock_transitions(self) -> None:
        """Verify sequence counter is even when idle, becomes odd during write, and even after."""
        self.assertEqual(self.shm.sequence % 2, 0)
        now = time.time()
        success = self.shm.write_slot("user1@example.com", "123456", now + 30, now + 30)
        self.assertTrue(success)
        # After write completes, sequence MUST be even
        seq_after = self.shm.sequence
        self.assertEqual(seq_after % 2, 0)
        self.assertGreaterEqual(seq_after, 2)

    def test_shm_seqlock_torn_read_rejection(self) -> None:
        """Verify that an in-progress write (odd sequence) causes reader to reject torn read."""
        now = time.time()
        self.shm.write_slot("user@example.com", "654321", now + 60, now + 60)

        # Artificially set sequence to odd (signaling write in progress)
        struct.pack_into(">Q", self.shm.buf, 16, 7)
        res = self.shm.read_slot("user@example.com")
        self.assertIsNone(res, "Reader must reject reads when seqlock counter is odd")

        # Restore even sequence
        struct.pack_into(">Q", self.shm.buf, 16, 8)
        res_valid = self.shm.read_slot("user@example.com")
        self.assertIsNotNone(res_valid)
        self.assertEqual(res_valid["code"], "654321")

    def test_shm_active_count_bounded_on_overwrites(self) -> None:
        """Verify overwriting an existing slot updates the entry without inflating active_count."""
        self.assertEqual(self.shm.active_count, 0)
        now = time.time()

        # Write account A first time -> active_count == 1
        self.shm.write_slot("alice@example.com", "111111", now + 30, now + 30)
        self.assertEqual(self.shm.active_count, 1)

        # Overwrite account A 25 times -> active_count MUST remain 1
        for i in range(25):
            self.shm.write_slot("alice@example.com", f"{i:06d}", now + 30, now + 30)
            self.assertEqual(self.shm.active_count, 1)

        # Write account B -> active_count MUST become 2
        self.shm.write_slot("bob@example.com", "222222", now + 30, now + 30)
        self.assertEqual(self.shm.active_count, 2)

        # Verify values
        res_a = self.shm.read_slot("alice@example.com")
        res_b = self.shm.read_slot("bob@example.com")
        self.assertIsNotNone(res_a)
        self.assertIsNotNone(res_b)
        self.assertEqual(res_a["code"], "000024")
        self.assertEqual(res_b["code"], "222222")

    def test_shm_collision_probing(self) -> None:
        """Verify linear collision probing handles hash collisions without data loss."""
        # Find two account names that produce the same base slot index
        base_h = _account_hash("account_alpha") % SLOT_COUNT
        colliding_account = None
        for i in range(1, 100_000):
            cand = f"collision_cand_{i}"
            if _account_hash(cand) % SLOT_COUNT == base_h:
                colliding_account = cand
                break

        self.assertIsNotNone(colliding_account, "Failed to find synthetic colliding account")

        now = time.time()
        self.shm.write_slot("account_alpha", "111222", now + 60, now + 60)
        self.shm.write_slot(colliding_account, "333444", now + 60, now + 60)

        self.assertEqual(self.shm.active_count, 2)

        read_alpha = self.shm.read_slot("account_alpha")
        read_colliding = self.shm.read_slot(colliding_account)

        self.assertIsNotNone(read_alpha)
        self.assertIsNotNone(read_colliding)
        self.assertEqual(read_alpha["code"], "111222")
        self.assertEqual(read_colliding["code"], "333444")

    def test_shm_atomic_lock_contention(self) -> None:
        """Verify acquire_lock provides mutual exclusion across threads."""
        acquired_order = []
        lock_held_event = threading.Event()
        release_event = threading.Event()

        def worker1():
            if self.shm.acquire_lock(timeout=1.0):
                acquired_order.append("w1")
                lock_held_event.set()
                release_event.wait(timeout=2.0)
                self.shm.release_lock()

        def worker2():
            lock_held_event.wait(timeout=2.0)
            # Should fail or wait while worker1 holds lock
            t0 = time.perf_counter()
            got_lock = self.shm.acquire_lock(timeout=0.05)
            _ = time.perf_counter() - t0
            if not got_lock:
                acquired_order.append("w2_timeout")
            else:
                self.shm.release_lock()
                acquired_order.append("w2_got")

        t1 = threading.Thread(target=worker1)
        t2 = threading.Thread(target=worker2)
        t1.start()
        t2.start()

        t2.join(timeout=1.0)
        release_event.set()
        t1.join(timeout=1.0)

        self.assertIn("w1", acquired_order)
        self.assertIn("w2_timeout", acquired_order)

    def test_shm_sub_millisecond_read_latency(self) -> None:
        """Verify zero-copy read latency is < 100 microseconds under concurrent queries."""
        now = time.time()
        self.shm.write_slot("perf_user@example.com", "999888", now + 120, now + 120)

        reader_count = 8
        queries_per_thread = 500

        def read_loop():
            latencies = []
            for _ in range(queries_per_thread):
                t0 = time.perf_counter()
                res = self.shm.read_slot("perf_user@example.com")
                latencies.append(time.perf_counter() - t0)
                if not res or res["code"] != "999888":
                    raise ValueError("Corrupt read during performance test")
            return latencies

        with concurrent.futures.ThreadPoolExecutor(max_workers=reader_count) as ex:
            futures = [ex.submit(read_loop) for _ in range(reader_count)]
            all_latencies = []
            for f in futures:
                all_latencies.extend(f.result())

        avg_latency_sec = sum(all_latencies) / len(all_latencies)
        avg_latency_us = avg_latency_sec * 1_000_000
        # Assert average read latency is well below 100us (0.1ms) SLA
        self.assertLess(
            avg_latency_us, 100.0, f"Average read latency {avg_latency_us:.2f}µs exceeded 100µs SLA"
        )


if __name__ == "__main__":
    unittest.main()
