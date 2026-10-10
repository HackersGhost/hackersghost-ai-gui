from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout

from hackersghost_ai.core.attachments import TextAttachment
from hackersghost_ai.core.errors import ChatError


class AttachmentDialog(QDialog):
    def __init__(self, attachment: TextAttachment, parent=None, *, confirm_send=False):
        super().__init__(parent)
        self.attachment = attachment
        self.confirm_send = confirm_send
        self.setWindowTitle("Send file to OpenAI?" if confirm_send else "Review attachment")
        self.resize(620, 460)
        self.setMinimumSize(420, 300)
        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        if confirm_send:
            notice = QLabel(
                "This text will be sent to OpenAI and included in later messages in this chat. "
                "Confirm that it contains no secrets. New chat clears the local history."
            )
        else:
            notice = QLabel("Remove secrets before attaching. Changes here do not modify your file.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(attachment.text)
        self.editor.setReadOnly(confirm_send)
        layout.addWidget(self.editor, 1)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.accept_button = buttons.addButton(
            "Send to OpenAI" if confirm_send else "Attach", QDialogButtonBox.ButtonRole.AcceptRole
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)
        self.accept_button.setAutoDefault(False)
        buttons.accepted.connect(self._accept_snapshot)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.editor.textChanged.connect(self._refresh_size)
        self._refresh_size()

    def _refresh_size(self):
        size = len(self.editor.toPlainText().encode("utf-8"))
        self.summary.setText(f"{self.attachment.name}\n{size:,} bytes / 65,536 bytes")

    def _accept_snapshot(self):
        if not self.confirm_send:
            try:
                self.attachment = TextAttachment(self.attachment.name, self.editor.toPlainText())
            except ChatError as error:
                self.error_label.setText(str(error))
                return
        self.accept()
