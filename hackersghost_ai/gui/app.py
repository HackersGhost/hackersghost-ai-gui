import sys

from PySide6.QtWidgets import QApplication

from hackersghost_ai.core.app_info import AppInfo
from hackersghost_ai.core.chat_service import ChatService
from hackersghost_ai.core.desktop_launcher import DESKTOP_ID
from hackersghost_ai.core.settings import AppSettings
from hackersghost_ai.core.update_service import UpdateService
from hackersghost_ai.gui.main_window import MainWindow
from hackersghost_ai.gui.styles import APP_STYLE


def build_window() -> MainWindow:
    app_info = AppInfo()
    settings = AppSettings()
    chat_service = ChatService(backend_mode=settings.backend_mode, model=settings.model)
    update_service = UpdateService(current_version=app_info.version)
    return MainWindow(app_info, settings, chat_service, update_service)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("HackersGhost AI")
    app.setDesktopFileName(DESKTOP_ID)
    app.setApplicationVersion(AppInfo().version)
    app.setStyleSheet(APP_STYLE)

    window = build_window()
    window.show()

    return app.exec()
