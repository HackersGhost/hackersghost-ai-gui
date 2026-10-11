import sys

from PySide6.QtWidgets import QApplication

from hackersghost_ai.core.app_info import AppInfo
from hackersghost_ai.core.chat_service import ChatService
from hackersghost_ai.core.desktop_launcher import DESKTOP_ID
from hackersghost_ai.core.settings import AppSettings
from hackersghost_ai.core.update_service import UpdateService
from hackersghost_ai.gui.main_window import MainWindow
from hackersghost_ai.gui.memory_dialog import MemoryDialog
from hackersghost_ai.gui.styles import APP_STYLE


def build_window() -> MainWindow:
    app_info = AppInfo()
    settings = AppSettings()
    chat_service = ChatService(backend_mode=settings.backend_mode, model=settings.model)
    update_service = UpdateService(current_version=app_info.version)
    window = MainWindow(app_info, settings, chat_service, update_service)

    app_menu = None
    for action in window.menuBar().actions():
        if action.text().replace("&", "") == "App":
            app_menu = action.menu()
            break
    if app_menu is None:
        app_menu = window.menuBar().addMenu("App")
    app_menu.addSeparator()
    memory_action = app_menu.addAction("Manage local memory…")
    memory_action.setToolTip("Review, add, remove or disable encrypted local memory.")

    def open_memory_dialog():
        MemoryDialog(window).exec()

    memory_action.triggered.connect(open_memory_dialog)
    window.memory_action = memory_action
    return window


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("HackersGhost AI")
    app.setDesktopFileName(DESKTOP_ID)
    app.setApplicationVersion(AppInfo().version)
    app.setStyleSheet(APP_STYLE)

    window = build_window()
    window.show()

    return app.exec()
