import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox

from hackersghost_ai.core.app_info import AppInfo
from hackersghost_ai.core.attachments import TextAttachment
from hackersghost_ai.core.chat_service import ChatService
from hackersghost_ai.core.credentials import Credential
from hackersghost_ai.core.desktop_launcher import LauncherError, LauncherReplacementRequired, LauncherResult
from hackersghost_ai.core.errors import ChatError
from hackersghost_ai.core.settings import AppSettings
from hackersghost_ai.core.update_service import Release, UpdateError, UpdateService, UpdateStatus
from hackersghost_ai.gui.attachment_dialog import AttachmentDialog
from hackersghost_ai.gui.main_window import MainWindow
from hackersghost_ai.gui.styles import APP_STYLE


class TestBackend:
    def __init__(self):
        self.gate = threading.Event()
        self.calls = []
        self.error = None

    def ask(self, key, model, history):
        self.calls.append([item.copy() for item in history])
        if not self.gate.wait(3):
            raise ChatError("Test request timed out")
        if self.error:
            raise self.error
        return "Example answer <img src='https://example.invalid/image'>"


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(APP_STYLE)

    def setUp(self):
        self.backend = TestBackend()
        service = ChatService("openai", "test-model", self.backend, lambda _: Credential("fake", "test keyring"))
        self.window = MainWindow(AppInfo(), AppSettings(model="test-model"), service, UpdateService("0.1.3"))
        self.window.show()
        self.app.processEvents()

    def wait_for(self, condition):
        deadline = time.monotonic() + 5
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertTrue(condition())

    def tearDown(self):
        self.backend.gate.set()
        self.wait_for(lambda: not self.window._busy())
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_send_enter_and_empty_input(self):
        self.assertFalse(self.window.send_button.isEnabled())
        self.assertEqual(self.window.api_key_input.echoMode(), QLineEdit.EchoMode.Password)
        self.backend.gate.set()
        self.window.prompt_input.setText("First question")
        QTest.mouseClick(self.window.send_button, Qt.MouseButton.LeftButton)
        self.wait_for(lambda: self.window._worker is None)
        self.window.prompt_input.setText("Follow-up")
        QTest.keyClick(self.window.prompt_input, Qt.Key.Key_Return)
        self.wait_for(lambda: self.window._worker is None)
        self.assertEqual(len(self.backend.calls), 2)
        self.assertEqual(len(self.backend.calls[-1]), 3)
        self.assertIn("<img src=", self.window.chat_output.toPlainText())
        self.assertIn("test keyring", self.window.key_source_label.text())
        self.window._send_prompt()
        self.assertEqual(len(self.backend.calls), 2)
        self.assertFalse(self.window.model_input.isEnabled())
        self.window.new_chat_button.click()
        self.assertFalse(self.window.chat_service.history)
        self.assertTrue(self.window.model_input.isEnabled())

    def test_pending_request_keeps_ui_responsive_and_prevents_duplicates(self):
        self.window.prompt_input.setText("Wait for reply")
        self.window._send_prompt()
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        self.wait_for(lambda: bool(ticks) and len(self.backend.calls) == 1)
        self.window._send_prompt()
        self.assertEqual(len(self.backend.calls), 1)
        self.assertFalse(self.window.backend_input.isEnabled())
        self.assertFalse(self.window.new_chat_button.isEnabled())
        self.window.close()
        self.assertTrue(self.window.isVisible())
        self.backend.gate.set()
        self.wait_for(lambda: self.window._worker is None)
        self.assertFalse(self.window.isVisible())

    def test_failed_request_restores_prompt_and_can_retry(self):
        self.backend.error = ChatError("Connection failed")
        self.backend.gate.set()
        self.window.prompt_input.setText("Retry me")
        self.window._send_prompt()
        self.wait_for(lambda: self.window._worker is None)
        self.assertEqual(self.window.prompt_input.text(), "Retry me")
        self.assertFalse(self.window.chat_service.history)
        self.assertTrue(self.window.send_button.isEnabled())
        self.assertIn("Connection failed", self.window.chat_output.toPlainText())
        self.backend.error = None
        self.window._send_prompt()
        self.wait_for(lambda: self.window._worker is None)
        self.assertEqual(len(self.window.chat_service.history), 2)

    def test_offline_switch_has_no_network_or_keyring(self):
        self.window.chat_service.credential_loader = lambda _: self.fail("Offline credential access")
        self.window.backend_input.setCurrentIndex(self.window.backend_input.findData("offline"))
        self.window.prompt_input.setText("Demo")
        self.window._send_prompt()
        self.wait_for(lambda: self.window._worker is None)
        self.assertFalse(self.backend.calls)
        self.assertIn("Offline demo response", self.window.chat_output.toPlainText())

    def test_file_selection_preview_redaction_cancel_and_remove(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "example.log"
            path.write_text("fictional-secret", encoding="utf-8")

            def redact():
                dialog = self.app.activeModalWidget()
                self.assertIsInstance(dialog, AttachmentDialog)
                self.assertEqual(dialog.editor.toPlainText(), "fictional-secret")
                dialog.editor.setPlainText("redacted text")
                dialog.accept_button.click()

            with patch("hackersghost_ai.gui.main_window.QFileDialog.getOpenFileName", return_value=(str(path), "")):
                QTimer.singleShot(0, redact)
                self.window.attach_button.click()
            self.assertEqual(self.window._attachment.text, "redacted text")
            self.assertEqual(path.read_text(encoding="utf-8"), "fictional-secret")
            self.assertTrue(self.window.attachment_row.isVisible())
            self.assertFalse(self.backend.calls)
            QTimer.singleShot(0, lambda: self.app.activeModalWidget().reject())
            self.window.review_attachment_button.click()
            self.assertEqual(self.window._attachment.text, "redacted text")
            self.window.remove_attachment_button.click()
            self.assertIsNone(self.window._attachment)

    def test_file_consent_cancellation_failure_retry_and_followup(self):
        self.window._attachment = TextAttachment("example.log", "fictional test log")
        self.window.prompt_input.setText("Explain this file")
        QTimer.singleShot(0, lambda: self.app.activeModalWidget().reject())
        self.window._send_prompt()
        self.assertFalse(self.backend.calls)
        self.assertIsNone(self.window._worker)
        self.assertEqual(self.window.prompt_input.text(), "Explain this file")
        self.backend.error = ChatError("Connection failed")
        self.backend.gate.set()
        with patch.object(self.window, "_confirm_attachment", return_value=True):
            self.window._send_prompt()
        self.wait_for(lambda: not self.window._busy())
        self.assertIsNotNone(self.window._attachment)
        self.assertFalse(self.window.chat_service.history)
        self.backend.error = None

        def confirm():
            dialog = self.app.activeModalWidget()
            self.assertTrue(dialog.editor.isReadOnly())
            self.assertEqual(dialog.editor.toPlainText(), "fictional test log")
            self.assertEqual(dialog.accept_button.text(), "Send to OpenAI")
            dialog.accept_button.click()

        QTimer.singleShot(0, confirm)
        self.window._send_prompt()
        self.wait_for(lambda: not self.window._busy())
        self.assertIsNone(self.window._attachment)
        self.assertFalse(self.window.attachment_row.isVisible())
        self.window.prompt_input.setText("What should I check next?")
        self.window._send_prompt()
        self.wait_for(lambda: not self.window._busy())
        self.assertIn("fictional test log", self.backend.calls[-1][0]["content"])
        self.assertEqual(self.backend.calls[-1][2]["content"], "What should I check next?")
        self.window.new_chat_button.click()
        self.assertFalse(self.window.chat_service.history)

    def test_updates_are_explicit_background_operations_and_close_waits(self):
        self.assertFalse(self.window.download_update_button.isEnabled())
        ticks = []

        def check():
            self.backend.gate.wait(3)
            return UpdateStatus("0.1.3", "0.1.3", "No newer GUI release available.")

        self.window.update_service.check = Mock(side_effect=check)
        self.window.check_update_button.click()
        self.assertFalse(self.window.check_update_button.isEnabled())
        QTimer.singleShot(0, lambda: ticks.append(True))
        self.wait_for(lambda: bool(ticks) and self.window.update_service.check.called)
        self.window._check_updates()
        self.window.update_service.check.assert_called_once()
        self.window.close()
        self.assertTrue(self.window.isVisible())
        self.backend.gate.set()
        self.wait_for(lambda: not self.window._busy())
        self.assertFalse(self.window.isVisible())

    def test_update_available_save_cancel_download_and_failure(self):
        release = Release("0.1.4", "0" * 64, int(time.time()) + 3600, b"test fixture")
        self.window.update_service.check = Mock(return_value=UpdateStatus("0.1.3", "0.1.4", "GUI 0.1.4 available", release))
        self.window.update_service.download_release = Mock(return_value=Path("verified.zip"))
        self.window.check_update_button.click()
        self.wait_for(lambda: not self.window._busy())
        self.assertTrue(self.window.download_update_button.isEnabled())
        with patch("hackersghost_ai.gui.main_window.QFileDialog.getSaveFileName", return_value=("", "")):
            self.window.download_update_button.click()
        self.window.update_service.download_release.assert_not_called()
        with patch("hackersghost_ai.gui.main_window.QFileDialog.getSaveFileName", return_value=("verified.zip", "")), \
             patch("hackersghost_ai.gui.main_window.QMessageBox.exec", return_value=0):
            self.window.download_update_button.click()
            self.wait_for(lambda: not self.window._busy())
        self.window.update_service.download_release.assert_called_once_with(release, "verified.zip")
        self.assertIn("ZIP saved", self.window.update_label.text())
        self.assertFalse(self.window.download_update_button.isEnabled())
        self.window.update_service.check.side_effect = UpdateError("GUI update signature is invalid.")
        self.window.check_update_button.click()
        self.wait_for(lambda: not self.window._busy())
        self.assertIn("invalid", self.window.update_label.text())
        self.assertFalse(self.window.download_update_button.isEnabled())
        self.assertTrue(self.window.check_update_button.isEnabled())

    def test_launcher_action_installs_only_when_requested_and_reports_errors(self):
        result = LauncherResult(Path("/test/menu.desktop"), Path("/test/Desktop/menu.desktop"))
        with patch("hackersghost_ai.gui.main_window.install_launchers", return_value=result) as install, \
             patch("hackersghost_ai.gui.main_window.QMessageBox.exec", return_value=0), \
             patch("sys.platform", "linux"):
            self.window._sync_controls()
            self.assertTrue(self.window.install_launcher_action.isEnabled())
            install.assert_not_called()
            self.window.install_launcher_action.trigger()
            install.assert_called_once()
            self.assertEqual(self.window.status_label.text(), "GUI launcher installed.")
        with patch("hackersghost_ai.gui.main_window.install_launchers", side_effect=LauncherError("Unable to write shortcut")):
            self.window._install_launcher()
        self.assertIn("Unable to write", self.window.status_label.text())
        with patch("sys.platform", "linux"):
            self.window.prompt_input.setText("Wait for reply")
            self.window._send_prompt()
            self.assertFalse(self.window.install_launcher_action.isEnabled())

    def test_launcher_replacement_requires_yes_and_cancellation_writes_nothing(self):
        result = LauncherResult(Path("/test/menu.desktop"), None)
        with patch("hackersghost_ai.gui.main_window.install_launchers", side_effect=LauncherReplacementRequired()) as install, \
             patch("hackersghost_ai.gui.main_window.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
            self.window._install_launcher()
            install.assert_called_once()
        with patch("hackersghost_ai.gui.main_window.install_launchers", side_effect=[LauncherReplacementRequired(), result]) as install, \
             patch("hackersghost_ai.gui.main_window.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes), \
             patch("hackersghost_ai.gui.main_window.QMessageBox.exec", return_value=0):
            self.window._install_launcher()
            self.assertEqual(install.call_count, 2)
            self.assertTrue(install.call_args.kwargs["replace_existing"])


if __name__ == "__main__":
    unittest.main()
