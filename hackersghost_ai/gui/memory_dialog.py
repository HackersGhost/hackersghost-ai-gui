"""User-controlled local-memory management dialog."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from hackersghost_ai.core import memory


class MemoryDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Local memory")
        self.resize(640, 460)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "HackersGhost AI local memory is optional, encrypted at rest and shared by the CLI and GUI "
            "for this Linux user. When memory is on and contains saved items, those items are included in "
            "every OpenAI request; the model is instructed to use them only when relevant. Do not store "
            "passwords, API keys, tokens, private keys or other secrets."
        )
        intro.setWordWrap(True)
        intro.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(intro)

        self.state_label = QLabel()
        self.state_label.setWordWrap(True)
        layout.addWidget(self.state_label)

        self.items = QListWidget()
        self.items.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.items, 1)

        self.entry = QLineEdit()
        self.entry.setPlaceholderText("A fact you explicitly want HackersGhost AI to remember")
        layout.addWidget(self.entry)

        row = QHBoxLayout()
        self.enable_button = QPushButton("Turn on")
        self.disable_button = QPushButton("Turn off")
        self.add_button = QPushButton("Remember")
        self.remove_button = QPushButton("Forget selected")
        row.addWidget(self.enable_button)
        row.addWidget(self.disable_button)
        row.addWidget(self.add_button)
        row.addWidget(self.remove_button)
        layout.addLayout(row)

        danger_row = QHBoxLayout()
        self.clear_button = QPushButton("Clear items")
        self.erase_button = QPushButton("Erase memory and key")
        self.close_button = QPushButton("Close")
        danger_row.addWidget(self.clear_button)
        danger_row.addWidget(self.erase_button)
        danger_row.addStretch(1)
        danger_row.addWidget(self.close_button)
        layout.addLayout(danger_row)

        self.enable_button.clicked.connect(self._enable)
        self.disable_button.clicked.connect(self._disable)
        self.add_button.clicked.connect(self._remember)
        self.remove_button.clicked.connect(self._forget)
        self.clear_button.clicked.connect(self._clear)
        self.erase_button.clicked.connect(self._erase)
        self.close_button.clicked.connect(self.accept)
        self.entry.returnPressed.connect(self._remember)
        self.entry.textChanged.connect(self._sync_controls)
        self.items.itemSelectionChanged.connect(self._sync_controls)

        self._refresh()

    def _error(self, error: Exception) -> None:
        QMessageBox.warning(self, "Local memory", str(error))
        self._refresh()

    def _refresh(self) -> None:
        self.items.clear()
        if not memory.is_enabled():
            self.state_label.setText(
                "Memory is off. Existing encrypted items, if any, remain on this device until you erase them."
            )
            self._sync_controls()
            return
        try:
            saved = memory.list_items()
        except (ValueError, OSError) as error:
            self.state_label.setText(f"Memory is on, but unavailable: {error}")
            self._sync_controls()
            return
        for number, text in enumerate(saved, 1):
            self.items.addItem(f"{number}. {text}")
        self.state_label.setText(
            f"Memory is on. {len(saved)} saved item{'s' if len(saved) != 1 else ''}. "
            "Only explicitly saved items are remembered."
        )
        self._sync_controls()

    def _sync_controls(self) -> None:
        enabled = memory.is_enabled()
        self.enable_button.setEnabled(not enabled)
        self.disable_button.setEnabled(enabled)
        self.entry.setEnabled(enabled)
        self.add_button.setEnabled(enabled and bool(self.entry.text().strip()))
        self.remove_button.setEnabled(enabled and self.items.currentRow() >= 0)
        self.clear_button.setEnabled(enabled and self.items.count() > 0)
        self.erase_button.setEnabled(True)

    def _enable(self) -> None:
        answer = QMessageBox.question(
            self,
            "Turn on local memory?",
            "Saved items are encrypted locally. When memory is on and contains saved items, those items are "
            "included in every OpenAI request; the model is instructed to use them only when relevant. "
            "Memory never stores items automatically in this version. Turn local memory on?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            memory.enable()
        except (ValueError, OSError) as error:
            self._error(error)
            return
        self._refresh()

    def _disable(self) -> None:
        memory.disable()
        self._refresh()

    def _remember(self) -> None:
        text = self.entry.text().strip()
        if not text:
            return
        try:
            memory.remember(text)
        except (ValueError, OSError) as error:
            self._error(error)
            return
        self.entry.clear()
        self._refresh()

    def _forget(self) -> None:
        row = self.items.currentRow()
        if row < 0:
            return
        try:
            memory.forget(row + 1)
        except (ValueError, OSError) as error:
            self._error(error)
            return
        self._refresh()

    def _clear(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear saved memory?",
            "Remove every saved memory item? Memory will remain enabled.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            memory.clear_items()
        except (ValueError, OSError) as error:
            self._error(error)
            return
        self._refresh()

    def _erase(self) -> None:
        answer = QMessageBox.warning(
            self,
            "Erase local memory?",
            "This removes the encrypted memory file and its encryption key from the Linux keyring. "
            "Saved memory cannot be recovered from HackersGhost AI after this. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            memory.erase()
        except (ValueError, OSError) as error:
            self._error(error)
            return
        self._refresh()
