import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hackersghost_ai.core import update_service
from hackersghost_ai.core.update_service import UpdateService


class V2StartupUpdateTests(unittest.TestCase):
    def test_automatic_check_is_due_once_per_day(self):
        with tempfile.TemporaryDirectory() as folder:
            stamp = Path(folder) / "gui-last-update-check"
            with patch.object(update_service, "AUTO_CHECK_FILE", stamp):
                service = UpdateService("2.0.0")
                self.assertTrue(service.automatic_check_due(now=1_000_000))
                service.mark_automatic_check(now=1_000_000)
                self.assertFalse(service.automatic_check_due(now=1_000_001))
                self.assertFalse(service.automatic_check_due(now=1_000_000 + update_service.AUTO_CHECK_INTERVAL - 1))
                self.assertTrue(service.automatic_check_due(now=1_000_000 + update_service.AUTO_CHECK_INTERVAL))

    def test_future_timestamp_is_treated_as_due(self):
        with tempfile.TemporaryDirectory() as folder:
            stamp = Path(folder) / "gui-last-update-check"
            with patch.object(update_service, "AUTO_CHECK_FILE", stamp):
                service = UpdateService("2.0.0")
                service.mark_automatic_check(now=2_000_000)
                self.assertTrue(service.automatic_check_due(now=1_000_000))


if __name__ == "__main__":
    unittest.main()
