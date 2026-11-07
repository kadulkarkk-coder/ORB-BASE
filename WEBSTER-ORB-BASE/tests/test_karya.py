"""Unit tests for Karya's internal background-task coordinator."""

import threading
import unittest

from PySide6.QtCore import QThreadPool

from assistant.karya import Karya, TaskState


class TestKarya(unittest.TestCase):
    def setUp(self):
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(1)
        self.karya = Karya(self.pool, history_limit=10)

    def tearDown(self):
        self.pool.waitForDone(3000)

    def test_successful_task_records_result_state(self):
        handle = self.karya.submit(
            lambda value: value * 2,
            21,
            task_name="double-number",
        )

        self.assertTrue(self.pool.waitForDone(3000))
        info = handle.info

        self.assertIsNotNone(info)
        self.assertEqual(info.name, "double-number")
        self.assertEqual(info.state, TaskState.SUCCEEDED)
        self.assertIsNotNone(info.started_at)
        self.assertIsNotNone(info.finished_at)
        self.assertIsNone(info.error)
        self.assertEqual(self.karya.active_count, 0)

    def test_failed_task_records_error_without_crashing_pool(self):
        def fail():
            raise ValueError("expected test failure")

        handle = self.karya.submit(fail, task_name="failing-task")

        self.assertTrue(self.pool.waitForDone(3000))
        info = handle.info

        self.assertEqual(info.state, TaskState.FAILED)
        self.assertIn("expected test failure", info.error)

    def test_queued_task_can_be_cancelled_before_execution(self):
        first_started = threading.Event()
        release_first = threading.Event()
        second_ran = threading.Event()

        def blocking_task():
            first_started.set()
            release_first.wait(3)

        first = self.karya.submit(blocking_task, task_name="blocking-task")
        self.assertTrue(first_started.wait(2))

        second = self.karya.submit(
            second_ran.set,
            task_name="queued-task",
        )
        self.assertTrue(second.cancel())

        release_first.set()
        self.assertTrue(self.pool.waitForDone(3000))

        self.assertEqual(first.state, TaskState.SUCCEEDED)
        self.assertEqual(second.state, TaskState.CANCELLED)
        self.assertFalse(second_ran.is_set())
        self.assertFalse(second.cancel())

    def test_task_history_is_bounded(self):
        handles = [
            self.karya.submit(lambda value=value: value)
            for value in range(4)
        ]

        self.assertTrue(self.pool.waitForDone(3000))

        self.assertTrue(all(h.state == TaskState.SUCCEEDED for h in handles))
        self.assertEqual(len(self.karya.list_tasks()), 4)

        small_history = Karya(self.pool, history_limit=2)
        extra = [
            small_history.submit(lambda value=value: value)
            for value in range(4)
        ]
        self.assertTrue(self.pool.waitForDone(3000))

        self.assertTrue(all(h.state == TaskState.SUCCEEDED for h in extra))
        self.assertEqual(len(small_history.list_tasks()), 2)

    def test_prepared_task_can_connect_handlers_before_start(self):
        handle = self.karya.submit(
            lambda: "ready",
            task_name="prepared-task",
            auto_start=False,
        )

        self.assertEqual(handle.state, TaskState.QUEUED)
        self.assertTrue(handle.start())
        self.assertFalse(handle.start())
        self.assertTrue(self.pool.waitForDone(3000))
        self.assertEqual(handle.state, TaskState.SUCCEEDED)

    def test_non_callable_tasks_are_rejected(self):
        with self.assertRaises(TypeError):
            self.karya.submit("not callable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
