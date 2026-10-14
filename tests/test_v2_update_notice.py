import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hackersghost_ai.gui.app import _show_startup_update_notice_when_ready


class V2StartupUpdateNoticeTests(unittest.TestCase):
    def test_available_release_shows_clear_startup_notice(self):
        window = SimpleNamespace(
            _update_worker=None,
            _available_release=SimpleNamespace(version="2.1.0"),
            isVisible=lambda: True,
        )
        with patch("hackersghost_ai.gui.app.QMessageBox.information") as notice:
            _show_startup_update_notice_when_ready(window)
        notice.assert_called_once()
        self.assertIn("2.1.0", notice.call_args.args[2])
        self.assertIn("Installation remains manual", notice.call_args.args[2])

    def test_no_startup_notice_without_available_release_or_visible_window(self):
        for release, visible in ((None, True), (SimpleNamespace(version="2.1.0"), False)):
            with self.subTest(release=release, visible=visible):
                window = SimpleNamespace(
                    _update_worker=None,
                    _available_release=release,
                    isVisible=lambda visible=visible: visible,
                )
                with patch("hackersghost_ai.gui.app.QMessageBox.information") as notice:
                    _show_startup_update_notice_when_ready(window)
                notice.assert_not_called()


if __name__ == "__main__":
    unittest.main()
