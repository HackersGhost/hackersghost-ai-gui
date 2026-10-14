import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hackersghost_ai.core import update_service
from hackersghost_ai.core.update_service import AUTO_CHECK_INTERVAL, UpdateService


class AutomaticUpdateNoticeTests(unittest.TestCase):
    def test_startup_check_is_due_once_per_day(self):
        with tempfile.TemporaryDirectory() as folder:
            state_file = Path(folder) / "state" / "gui-last-update-check"
            with patch.object(update_service, "AUTO_CHECK_FILE", state_file):
                service = UpdateService("2.0.0")
                self.assertTrue(service.automatic_check_due(now=100000.0))
                service.mark_automatic_check(now=100000.0)
                self.assertFalse(service.automatic_check_due(now=100000.0 + AUTO_CHECK_INTERVAL - 1))
                self.assertTrue(service.automatic_check_due(now=100000.0 + AUTO_CHECK_INTERVAL))
                self.assertEqual(state_file.read_text(), "100000")
                self.assertEqual(state_file.stat().st_mode & 0o777, 0o600)

    def test_clock_rollback_allows_a_fresh_check(self):
        with tempfile.TemporaryDirectory() as folder:
            state_file = Path(folder) / "gui-last-update-check"
            state_file.write_text("test")
            with patch.object(update_service, "AUTO_CHECK_FILE", state_file), \
                 patch("os.path.getmtime", return_value=200000.0):
                # Set the real mtime through the supported filesystem API.
                import os
                os.utime(state_file, (200000.0, 200000.0))
                service = UpdateService("2.0.0")
                self.assertTrue(service.automatic_check_due(now=100000.0))


if __name__ == "__main__":
    unittest.main()
