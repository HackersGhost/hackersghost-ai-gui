"""Make all three GUI update actions accessible in the narrow sidebar."""
import os
from types import SimpleNamespace
import unittest

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QScrollArea, QVBoxLayout

from hackersghost_ai.gui.main_window import MainWindow
from hackersghost_ai.gui.styles import APP_STYLE


class UpdateButtonVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(APP_STYLE)

    def test_install_button_visible_in_fixed_width_sidebar_even_when_disabled(self):
        info = SimpleNamespace(
            name="HackersGhost AI", version="2.1.0", channel="stable",
            display_version="HackersGhost AI 2.1.0",
        )
        settings = SimpleNamespace(backend_mode="offline", model="offline")
        update_service = SimpleNamespace(get_status=lambda: SimpleNamespace(message="No newer release"))
        window = MainWindow(info, settings, SimpleNamespace(clear=lambda: None), update_service)
        self.addCleanup(window.close)
        window.resize(760, 520)
        window.show()
        self.app.processEvents()

        scroll = window.findChild(QScrollArea)
        self.assertIsNotNone(scroll)
        self.assertEqual(scroll.width(), 280)

        buttons = (
            window.check_update_button,
            window.download_update_button,
            window.install_update_button,
        )
        for button in buttons:
            with self.subTest(button=button.text()):
                self.assertTrue(button.isVisible())
                self.assertGreater(button.width(), 40)
                top_left = button.mapTo(scroll.viewport(), QPoint(0, 0))
                self.assertGreaterEqual(top_left.x(), 0)
                self.assertLessEqual(
                    top_left.x() + button.width(), scroll.viewport().width(),
                    f"{button.text()} must fit the narrow sidebar without being clipped",
                )
        self.assertFalse(window.install_update_button.isEnabled())
        self.assertFalse(window.download_update_button.isEnabled())
        self.assertTrue(window.check_update_button.isEnabled())

        # A newer release should activate the buttons without changing their layout.
        window._available_release = SimpleNamespace(version="2.2.0")
        window._sync_controls()
        self.assertTrue(window.install_update_button.isEnabled())
        self.assertTrue(window.download_update_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
