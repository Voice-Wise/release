"""验证计时分类，避免把依赖等待或编译时间误报为排队、测试。"""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("timing", Path(__file__).with_name("actions-timing.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TimingTests(unittest.TestCase):
    def setUp(self):
        self.run = {"databaseId": 1, "workflowName": "CI", "headSha": "abc",
                    "createdAt": "2026-11-01T10:00:00Z", "url": "https://example.com"}
        self.job = {"id": 2, "name": "Tests", "conclusion": "success",
                    "created_at": "2026-11-01T10:00:10Z",
                    "started_at": "2026-11-01T10:00:13Z",
                    "completed_at": "2026-11-01T10:01:13Z",
                    "steps": [{"name": "Run Rust tests", "conclusion": "success",
                               "started_at": "2026-11-01T10:00:20Z",
                               "completed_at": "2026-11-01T10:01:10Z"}]}

    def test_compilation_belongs_to_preparation(self):
        log = "Tests\tUNKNOWN STEP\t2026-11-01T10:01:00.500Z \x1b[1mFinished\x1b[0m `test` profile [unoptimized] target(s) in 40s"
        row = MODULE.job_row(self.run, self.job, log)
        self.assertEqual(row["dependency_wait_s"], 10)
        self.assertEqual(row["queue_s"], 3)
        self.assertEqual(row["compile_in_prepare_s"], 40.5)
        self.assertEqual(row["execute_s"], 9.5)
        self.assertEqual(row["prepare_s"], 50.5)
        self.assertEqual(row["prepare_s"] + row["execute_s"], row["job_elapsed_s"])

    def test_missing_logs_are_explicit(self):
        row = MODULE.job_row(self.run, self.job, "")
        self.assertFalse(row["log_available"])
        self.assertEqual(row["execute_s"], 50)

    def test_another_jobs_compile_line_is_ignored(self):
        log = "Other\tStep\t2026-11-01T10:01:00Z Finished `test` profile target(s) in 40s"
        self.assertEqual(MODULE.job_row(self.run, self.job, log)["compile_in_prepare_s"], 0)

    def test_skipped_job_has_no_execution_time(self):
        self.job.update(started_at=None, completed_at=None, steps=[], conclusion="skipped")
        row = MODULE.job_row(self.run, self.job, "")
        self.assertEqual(row["job_elapsed_s"], 0)
        self.assertEqual(row["execute_s"], 0)


if __name__ == "__main__":
    unittest.main()
