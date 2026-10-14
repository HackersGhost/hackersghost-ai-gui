import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

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
        if action.text().replace("&", "") in ("App", "App Menu"):
            app_menu = action.menu()
            break
    if app_menu is None:
        app_menu = window.menuBar().addMenu("App Menu")
    else:
        app_menu.menuAction().setText("App Menu")
    app_menu.addSeparator()
    memory_action = app_menu.addAction("Manage memory…")
    memory_action.setToolTip("Review, search, clear or disable encrypted automatic memory.")

    def open_memory_dialog():
        MemoryDialog(window).exec()

    memory_action.triggered.connect(open_memory_dialog)
    window.memory_action = memory_action
    return window


def _show_startup_update_notice_when_ready(window: MainWindow) -> None:
    """Show one clear notice after the background startup check finishes."""
    if window._update_worker is not None:
        QTimer.singleShot(100, lambda: _show_startup_update_notice_when_ready(window))
        return
    release = window._available_release
    if release is None or not window.isVisible():
        return
    QMessageBox.information(
        window,
        "HackersGhost AI update available",
        f"HackersGhost AI {release.version} is available.\n\n"
        "Use Download in the Updates section to save the verified ZIP. "
        "Installation remains manual; nothing is installed or executed automatically.",
    )


def _schedule_automatic_update_check(window: MainWindow) -> None:
    """Check the signed GUI feed at startup at most once per 24 hours."""
    if window.backend_input.currentData() == "offline":
        return

    def run_check():
        try:
            if not window.update_service.automatic_check_due():
                return
            window.update_service.mark_automatic_check()
        except OSError:
            # A state-file problem must not hide an available update.
            pass
        window._check_updates()
        QTimer.singleShot(100, lambda: _show_startup_update_notice_when_ready(window))

    QTimer.singleShot(800, run_check)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("HackersGhost AI")
    app.setDesktopFileName(DESKTOP_ID)
    app.setApplicationVersion(AppInfo().version)
    app.setStyleSheet(APP_STYLE)

    window = build_window()
    window.show()
    _schedule_automatic_update_check(window)

    return app.exec()
