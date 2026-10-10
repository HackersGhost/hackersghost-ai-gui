from datetime import datetime
from html import escape
from pathlib import Path
import sys

from PySide6.QtCore import QStandardPaths, Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from hackersghost_ai.core.app_info import AppInfo
from hackersghost_ai.core.attachments import read_attachment
from hackersghost_ai.core.chat_service import ChatMessage, ChatService
from hackersghost_ai.core.desktop_launcher import LauncherError, LauncherReplacementRequired, install_launchers
from hackersghost_ai.core.errors import ChatError
from hackersghost_ai.core.settings import AppSettings
from hackersghost_ai.core.update_service import UpdateService, UpdateStatus
from hackersghost_ai.gui.attachment_dialog import AttachmentDialog
from hackersghost_ai.gui.chat_worker import ChatWorker
from hackersghost_ai.gui.update_worker import UpdateWorker


class MainWindow(QMainWindow):
    def __init__(
        self,
        app_info: AppInfo,
        settings: AppSettings,
        chat_service: ChatService,
        update_service: UpdateService,
    ) -> None:
        super().__init__()
        self.app_info = app_info
        self.settings = settings
        self.chat_service = chat_service
        self.update_service = update_service
        self._worker = None
        self._update_worker = None
        self._available_release = None
        self._attachment = None
        self._conversation_started = False
        self._close_pending = False
        self._pending_prompt = ""

        self.setWindowTitle(app_info.display_version)
        self.resize(980, 680)
        self.setMinimumSize(760, 520)

        self.chat_output = QTextEdit()
        self.prompt_input = QLineEdit()
        self.send_button = QPushButton("Send")
        self.send_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        self.new_chat_button = QToolButton()
        self.new_chat_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        self.new_chat_button.setToolTip("New chat")
        self.new_chat_button.setAccessibleName("New chat")
        self.backend_input = QComboBox()
        self.backend_input.addItem("OpenAI", "openai")
        self.backend_input.addItem("Offline demo", "offline")
        self.backend_input.setCurrentIndex(max(0, self.backend_input.findData(settings.backend_mode)))
        self.model_input = QLineEdit(settings.model)
        self.model_input.setPlaceholderText("Model ID")
        self.model_input.setToolTip("Use a model available to your API account. Start a new chat to change it.")
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Use existing CLI key")
        self.api_key_input.setToolTip("Optional override for this window only. Never saved to a file.")
        self.key_source_label = QLabel("Key source: not loaded")
        self.session_label = QLabel()
        self.status_label = QLabel("Ready")
        self.update_label = QLabel()
        self.check_update_button = QPushButton("Check")
        self.check_update_button.setToolTip("Check for GUI updates")
        self.check_update_button.setAccessibleName("Check for updates")
        self.check_update_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.download_update_button = QPushButton("Download")
        self.download_update_button.setAccessibleName("Download update")
        self.download_update_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.download_update_button.setToolTip("Download a verified GUI ZIP. Installation is manual.")
        self.attach_button = self._tool_button(QStyle.StandardPixmap.SP_DirOpenIcon, "Attach text file")
        self.review_attachment_button = self._tool_button(QStyle.StandardPixmap.SP_FileDialogDetailedView, "Review attachment")
        self.remove_attachment_button = self._tool_button(QStyle.StandardPixmap.SP_DialogCloseButton, "Remove attachment")
        self.attachment_label = QLabel()
        self.attachment_label.setTextFormat(Qt.TextFormat.PlainText)
        self.attachment_label.setWordWrap(True)
        self.attachment_label.setMinimumWidth(0)
        self.attachment_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self._build_ui()
        app_menu = self.menuBar().addMenu("App")
        self.install_launcher_action = app_menu.addAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DesktopIcon), "Install desktop launcher"
        )
        self.install_launcher_action.setToolTip("Create Linux application-menu and desktop shortcuts for this GUI version.")
        self.install_launcher_action.triggered.connect(self._install_launcher)
        self._connect_signals()
        self._sync_controls()
        self._show_welcome_message()

    def _tool_button(self, icon, title):
        button = QToolButton()
        button.setIcon(self.style().standardIcon(icon))
        button.setToolTip(title)
        button.setAccessibleName(title)
        button.setFixedSize(38, 38)
        return button

    def _busy(self):
        return self._worker is not None or self._update_worker is not None

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())
        root_layout.addWidget(self._build_chat_area(), stretch=1)

        self.setCentralWidget(root)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel(self.app_info.name)
        title.setObjectName("AppTitle")
        title.setWordWrap(True)

        version = QLabel(f"v{self.app_info.version} ({self.app_info.channel})")
        version.setObjectName("Muted")
        version.setWordWrap(True)

        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setSpacing(8)
        for caption, control in (
            ("Mode", self.backend_input),
            ("Model", self.model_input),
            ("Session API key (optional)", self.api_key_input),
        ):
            label = QLabel(caption)
            label.setBuddy(control)
            settings_layout.addWidget(label)
            settings_layout.addWidget(control)
        self.key_source_label.setObjectName("Muted")
        self.key_source_label.setWordWrap(True)
        settings_layout.addWidget(self.key_source_label)

        update_status = self.update_service.get_status()
        self.update_label.setText(update_status.message)
        self.update_label.setObjectName("Muted")
        self.update_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(version)
        layout.addWidget(settings_group)
        layout.addWidget(QLabel("Updates"))
        layout.addWidget(self.update_label)
        update_actions = QHBoxLayout()
        update_actions.addWidget(self.check_update_button)
        update_actions.addWidget(self.download_update_button)
        layout.addLayout(update_actions)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedWidth(280)
        scroll.setWidget(sidebar)
        return scroll

    def _build_chat_area(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        heading = QLabel("HackersGhost AI")
        heading.setObjectName("AppTitle")
        heading.setWordWrap(True)

        self.session_label.setObjectName("Muted")
        self.session_label.setWordWrap(True)
        heading_layout = QHBoxLayout()
        heading_layout.addWidget(heading, stretch=1)
        heading_layout.addWidget(self.new_chat_button)

        chat_frame = QFrame()
        chat_frame.setObjectName("ChatPane")
        chat_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        chat_layout = QVBoxLayout(chat_frame)
        chat_layout.setContentsMargins(0, 0, 0, 0)

        self.chat_output.setObjectName("ChatOutput")
        self.chat_output.setReadOnly(True)
        self.chat_output.setAcceptRichText(True)
        chat_layout.addWidget(self.chat_output)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)
        self.prompt_input.setPlaceholderText("Type a message...")
        self.send_button.setDefault(True)
        input_layout.addWidget(self.attach_button)
        input_layout.addWidget(self.prompt_input, stretch=1)
        input_layout.addWidget(self.send_button)

        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        layout.addLayout(heading_layout)
        layout.addWidget(self.session_label)
        layout.addWidget(chat_frame, stretch=1)
        self.attachment_row = QWidget()
        attachment_layout = QHBoxLayout(self.attachment_row)
        attachment_layout.setContentsMargins(0, 0, 0, 0)
        attachment_layout.addWidget(self.attachment_label, 1)
        attachment_layout.addWidget(self.review_attachment_button)
        attachment_layout.addWidget(self.remove_attachment_button)
        layout.addWidget(self.attachment_row)
        layout.addWidget(self.status_label)
        layout.addLayout(input_layout)

        return content

    def _connect_signals(self) -> None:
        self.send_button.clicked.connect(self._send_prompt)
        self.prompt_input.returnPressed.connect(self._send_prompt)
        self.prompt_input.textChanged.connect(self._sync_controls)
        self.backend_input.currentIndexChanged.connect(self._sync_controls)
        self.new_chat_button.clicked.connect(self._new_chat)
        self.attach_button.clicked.connect(self._choose_attachment)
        self.review_attachment_button.clicked.connect(self._review_attachment)
        self.remove_attachment_button.clicked.connect(self._remove_attachment)
        self.check_update_button.clicked.connect(self._check_updates)
        self.download_update_button.clicked.connect(self._download_update)

    def _show_welcome_message(self) -> None:
        self._append_message(
            ChatMessage(
                sender="HackersGhost AI",
                text=(
                    "Welcome to HackersGhost AI."
                ),
                created_at=datetime.now(),
            )
        )

    @Slot()
    def _sync_controls(self) -> None:
        busy = self._busy() or self._close_pending
        online = self.backend_input.currentData() == "openai"
        self.backend_input.setEnabled(not busy and not self._conversation_started)
        self.backend_input.setToolTip("Start a new chat to change mode.")
        self.model_input.setEnabled(online and not busy and not self._conversation_started)
        self.api_key_input.setEnabled(online and not busy)
        self.new_chat_button.setEnabled(not busy)
        self.prompt_input.setEnabled(not busy)
        self.send_button.setEnabled(not busy and bool(self.prompt_input.text().strip()))
        self.attach_button.setEnabled(not busy and online)
        self.review_attachment_button.setEnabled(not busy)
        self.remove_attachment_button.setEnabled(not busy)
        self.attachment_row.setVisible(self._attachment is not None)
        self.check_update_button.setEnabled(not busy)
        self.install_launcher_action.setEnabled(not busy and sys.platform == "linux")
        self.download_update_button.setEnabled(not busy and self._available_release is not None)
        if self._attachment is not None:
            name = self._attachment.name
            short_name = name if len(name) <= 28 else name[:25] + "..."
            self.attachment_label.setText(f"{short_name} | {self._attachment.size:,} bytes")
            self.attachment_label.setToolTip(f"<qt>{escape(name)}</qt>")
        self.session_label.setText(
            "OpenAI | Messages and session history are sent to OpenAI."
            if online else "Offline demo | No messages are sent."
        )

    @Slot()
    def _new_chat(self) -> None:
        if self._busy() or self._close_pending:
            return
        self.chat_service.clear()
        self._attachment = None
        self._conversation_started = False
        self.chat_output.clear()
        self.prompt_input.clear()
        self.key_source_label.setText("Key source: not loaded")
        self.status_label.setText("Ready")
        self._sync_controls()
        self._show_welcome_message()
        self.prompt_input.setFocus()

    @Slot()
    def _send_prompt(self) -> None:
        if self._busy() or self._close_pending:
            return
        prompt = self.prompt_input.text().strip()
        if not prompt:
            return
        online = self.backend_input.currentData() == "openai"
        model = self.model_input.text().strip()
        if online and not model:
            self.status_label.setText("Enter a model name in Settings.")
            self.model_input.setFocus()
            return
        if self._attachment is not None:
            if not online:
                self.status_label.setText("Remove the attachment or select OpenAI mode.")
                return
            if not self._confirm_attachment():
                return
        self.chat_service.backend_mode = self.backend_input.currentData()
        self.chat_service.model = model

        display_prompt = prompt
        if self._attachment is not None:
            display_prompt += f"\n[File: {self._attachment.name}]"
        self._append_message(ChatMessage("You", display_prompt, datetime.now()))
        self._pending_prompt = prompt
        self._worker = ChatWorker(
            self.chat_service, prompt, self.api_key_input.text(), self,
            attachment=self._attachment, attachment_confirmed=self._attachment is not None,
        )
        self._worker.succeeded.connect(self._on_reply)
        self._worker.failed.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self.prompt_input.clear()
        self.status_label.setText("Waiting for OpenAI..." if online else "Preparing demo response...")
        self._sync_controls()
        self._worker.start()

    @Slot(object)
    def _on_reply(self, response: ChatMessage) -> None:
        self._conversation_started = True
        self._attachment = None
        self._append_message(response)
        online = self.chat_service.backend_mode == "openai"
        self.key_source_label.setText(
            f"Key source: {self.chat_service.credential_source}" if online else "Key source: not used"
        )
        self.status_label.setText("Ready")

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._append_message(ChatMessage("Request failed", message, datetime.now()))
        self.status_label.setText(message)
        self.prompt_input.setText(self._pending_prompt)

    @Slot()
    def _on_finished(self) -> None:
        worker = self._worker
        self._worker = None
        self._pending_prompt = ""
        if worker is not None:
            worker.deleteLater()
        self._sync_controls()
        if self._close_pending:
            self.close()
        else:
            self.prompt_input.setFocus()

    def closeEvent(self, event) -> None:
        if self._busy():
            self._close_pending = True
            self.status_label.setText("Closing after the current request finishes...")
            self._sync_controls()
            event.ignore()
            return
        self.api_key_input.clear()
        self.chat_service.clear()
        self._attachment = None
        super().closeEvent(event)

    @Slot()
    def _install_launcher(self):
        if self._busy() or self._close_pending:
            return
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        arguments = {"desktop_dir": Path(desktop) if desktop else None}
        try:
            try:
                result = install_launchers(**arguments)
            except LauncherReplacementRequired:
                answer = QMessageBox.question(
                    self, "Replace GUI shortcuts?",
                    "Existing HackersGhost AI GUI shortcuts will point to this version. "
                    "The old application folder and CLI will not be changed. Replace the shortcuts?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
                result = install_launchers(**arguments, replace_existing=True)
        except LauncherError as error:
            self.status_label.setText(str(error))
            return
        self.status_label.setText("GUI launcher installed.")
        message = QMessageBox(self)
        message.setWindowTitle("GUI launcher installed")
        message.setTextFormat(Qt.TextFormat.PlainText)
        text = f"Application menu:\n{result.menu_path}"
        if result.desktop_path is not None:
            text += f"\n\nDesktop:\n{result.desktop_path}\n\nYour desktop may ask you to allow launching this shortcut."
        else:
            text += "\n\nNo separate desktop folder is configured; only the menu shortcut was installed."
        message.setText(text + "\n\nKeep this application folder and its Python environment in place.")
        message.exec()
        message.deleteLater()

    @Slot()
    def _choose_attachment(self):
        if self._busy() or self._close_pending or self.backend_input.currentData() != "openai":
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a text file", "", "Text files (*.txt *.log *.conf *.cfg *.json *.yaml *.yml *.md *.csv);;All files (*)"
        )
        if not path:
            return
        try:
            attachment = read_attachment(path)
        except ChatError as error:
            self.status_label.setText(str(error))
            return
        self._edit_attachment(attachment)

    def _edit_attachment(self, attachment):
        dialog = AttachmentDialog(attachment, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._attachment = dialog.attachment
            self.status_label.setText("File attached; not sent.")
            self._sync_controls()
        dialog.deleteLater()

    @Slot()
    def _review_attachment(self):
        if not self._busy() and not self._close_pending and self._attachment is not None:
            self._edit_attachment(self._attachment)

    @Slot()
    def _remove_attachment(self):
        if not self._busy() and not self._close_pending:
            self._attachment = None
            self.status_label.setText("Attachment removed.")
            self._sync_controls()

    def _confirm_attachment(self):
        dialog = AttachmentDialog(self._attachment, self, confirm_send=True)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        dialog.deleteLater()
        return accepted

    @Slot()
    def _check_updates(self):
        if self._busy() or self._close_pending:
            return
        self._available_release = None
        self.update_label.setText("Checking GUI updates...")
        self._start_update_worker(UpdateWorker(self.update_service, self))

    @Slot()
    def _download_update(self):
        if self._busy() or self._close_pending or self._available_release is None:
            return
        folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        path, _ = QFileDialog.getSaveFileName(
            self, "Save verified GUI update", str(Path(folder) / self._available_release.filename), "ZIP archive (*.zip)"
        )
        if not path:
            return
        self.update_label.setText("Downloading and verifying...")
        self._start_update_worker(UpdateWorker(
            self.update_service, self, release=self._available_release, destination=path,
        ))

    def _start_update_worker(self, worker):
        self._update_worker = worker
        worker.succeeded.connect(self._on_update_result)
        worker.failed.connect(self._on_update_error)
        worker.finished.connect(self._on_update_finished)
        self._sync_controls()
        worker.start()

    @Slot(object)
    def _on_update_result(self, result):
        if isinstance(result, UpdateStatus):
            self._available_release = result.release
            self.update_label.setText(result.message)
        else:
            self._available_release = None
            self.update_label.setText("Verified GUI ZIP saved. Installation is manual.")
            if not self._close_pending:
                message = QMessageBox(self)
                message.setWindowTitle("GUI update downloaded")
                message.setTextFormat(Qt.TextFormat.PlainText)
                message.setText(
                    f"Verified download saved to:\n{result}\n\n"
                    "Extract it into a new folder and launch its scripts/run_gui.sh. "
                    "Keep the old folder until the new version works. The running app and CLI were not changed."
                )
                message.exec()
                message.deleteLater()

    @Slot(str)
    def _on_update_error(self, message):
        self._available_release = None
        self.update_label.setText(message)

    @Slot()
    def _on_update_finished(self):
        worker = self._update_worker
        self._update_worker = None
        if worker is not None:
            worker.deleteLater()
        self._sync_controls()
        if self._close_pending:
            self.close()

    def _append_message(self, message: ChatMessage) -> None:
        timestamp = message.created_at.strftime("%H:%M")
        safe_sender = escape(message.sender)
        safe_text = escape(message.text).replace("\n", "<br>")
        self.chat_output.append(
            f"<p><b>{safe_sender}</b> "
            f"<span style='color:#8b949e'>({timestamp})</span><br>"
            f"{safe_text}</p>"
        )
        self.chat_output.verticalScrollBar().setValue(
            self.chat_output.verticalScrollBar().maximum()
        )

