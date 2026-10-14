"""User-controlled encrypted memory dialog for HackersGhost AI v2."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from hackersghost_ai.core import memory


class MemoryDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Memory")
        self.resize(780, 590)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Local Memory and automatic conversation memory are separate choices. Turning Local Memory on lets "
            "pinned facts and previously saved conversation memory be used as context, but it does not start "
            "saving new chats automatically. Automatic conversation memory requires its own explicit opt-in. "
            "When enabled, successful OpenAI conversations without file attachments are stored in encrypted local "
            "storage shared by the CLI and GUI for this Linux user. Secret detection is best effort, so never use "
            "Memory to store passwords, API keys, tokens or private keys. Remembered text is included as context "
            "in later OpenAI requests."
        )
        intro.setWordWrap(True)
        intro.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(intro)

        self.state_label = QLabel()
        self.state_label.setWordWrap(True)
        layout.addWidget(self.state_label)

        search_row = QHBoxLayout()
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Search memory")
        self.search_button = QPushButton("Search")
        self.show_all_button = QPushButton("Show all")
        search_row.addWidget(self.search_entry, 1)
        search_row.addWidget(self.search_button)
        search_row.addWidget(self.show_all_button)
        layout.addLayout(search_row)

        self.items = QListWidget()
        self.items.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.items, 1)

        memory_controls = QHBoxLayout()
        self.enable_button = QPushButton("Local Memory ON")
        self.disable_button = QPushButton("Local Memory OFF")
        self.auto_enable_button = QPushButton("Auto Memory ON")
        self.auto_disable_button = QPushButton("Auto Memory OFF")
        memory_controls.addWidget(self.enable_button)
        memory_controls.addWidget(self.disable_button)
        memory_controls.addWidget(self.auto_enable_button)
        memory_controls.addWidget(self.auto_disable_button)
        layout.addLayout(memory_controls)

        pin_label = QLabel("Optional: pin an important fact so it stays available independently of automatic conversation saving.")
        pin_label.setWordWrap(True)
        layout.addWidget(pin_label)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Fact to pin")
        layout.addWidget(self.entry)

        pin_controls = QHBoxLayout()
        self.add_button = QPushButton("Pin fact")
        self.remove_button = QPushButton("Forget selected pin")
        pin_controls.addWidget(self.add_button)
        pin_controls.addWidget(self.remove_button)
        pin_controls.addStretch(1)
        layout.addLayout(pin_controls)

        danger_row = QHBoxLayout()
        self.clear_button = QPushButton("Clear all memory")
        self.erase_button = QPushButton("Erase memory + key")
        self.close_button = QPushButton("Close")
        danger_row.addWidget(self.clear_button)
        danger_row.addWidget(self.erase_button)
        danger_row.addStretch(1)
        danger_row.addWidget(self.close_button)
        layout.addLayout(danger_row)

        self.enable_button.clicked.connect(self._enable)
        self.disable_button.clicked.connect(self._disable)
        self.auto_enable_button.clicked.connect(self._enable_auto)
        self.auto_disable_button.clicked.connect(self._disable_auto)
        self.add_button.clicked.connect(self._remember)
        self.remove_button.clicked.connect(self._forget)
        self.search_button.clicked.connect(self._search)
        self.show_all_button.clicked.connect(self._refresh)
        self.clear_button.clicked.connect(self._clear)
        self.erase_button.clicked.connect(self._erase)
        self.close_button.clicked.connect(self.accept)
        self.entry.returnPressed.connect(self._remember)
        self.search_entry.returnPressed.connect(self._search)
        self.search_entry.textChanged.connect(self._sync_controls)
        self.entry.textChanged.connect(self._sync_controls)
        self.items.itemSelectionChanged.connect(self._sync_controls)

        self._refresh()

    def _error(self, error: Exception) -> None:
        QMessageBox.warning(self, "Memory", str(error))
        self._refresh()

    def _add_item(self, text: str, kind: str, number: int) -> None:
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, (kind, number))
        self.items.addItem(item)

    def _refresh(self) -> None:
        self.items.clear()
        if not memory.is_enabled():
            self.state_label.setText(
                "Local Memory is OFF. Automatic conversation memory is OFF. Existing encrypted memory stays on "
                "this device until you clear or erase it."
            )
            self._sync_controls()
            return
        try:
            pinned = memory.list_items()
            turns = memory.list_turns()
        except (ValueError, OSError) as error:
            self.state_label.setText(f"Local Memory is ON, but unavailable: {error}")
            self._sync_controls()
            return

        for number, text in enumerate(pinned, 1):
            self._add_item(f"Pinned {number}: {text}", "pinned", number)
        for number, turn in enumerate(turns, 1):
            label = "You" if turn["role"] == "user" else "AI"
            self._add_item(f"{label}: {turn['text']}", turn["role"], number)

        auto_on = memory.is_auto_enabled()
        auto_text = (
            "Automatic conversation memory is ON. New successful OpenAI conversations without file attachments "
            "are remembered automatically."
            if auto_on
            else "Automatic conversation memory is OFF. New conversations are not being saved automatically."
        )
        self.state_label.setText(
            f"Local Memory is ON. {len(pinned)} pinned item{'s' if len(pinned) != 1 else ''} and "
            f"{len(turns)} remembered conversation turn{'s' if len(turns) != 1 else ''}. {auto_text}"
        )
        self._sync_controls()

    def _sync_controls(self) -> None:
        enabled = memory.is_enabled()
        auto_enabled = memory.is_auto_enabled()
        self.enable_button.setEnabled(not enabled)
        self.disable_button.setEnabled(enabled)
        self.auto_enable_button.setEnabled(enabled and not auto_enabled)
        self.auto_disable_button.setEnabled(enabled and auto_enabled)
        self.search_entry.setEnabled(enabled)
        self.search_button.setEnabled(enabled and bool(self.search_entry.text().strip()))
        self.show_all_button.setEnabled(enabled)
        self.entry.setEnabled(enabled)
        self.add_button.setEnabled(enabled and bool(self.entry.text().strip()))
        selected = self.items.currentItem()
        selected_data = selected.data(Qt.ItemDataRole.UserRole) if selected is not None else None
        self.remove_button.setEnabled(enabled and bool(selected_data) and selected_data[0] == "pinned")
        self.clear_button.setEnabled(enabled and self.items.count() > 0)
        self.erase_button.setEnabled(True)

    def _enable(self) -> None:
        answer = QMessageBox.question(
            self,
            "Turn Local Memory on?",
            "Local Memory lets pinned facts and previously saved conversation memory be used as context in later "
            "OpenAI requests. This does not enable automatic conversation saving. Turn Local Memory on?",
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

    def _enable_auto(self) -> None:
        answer = QMessageBox.question(
            self,
            "Enable automatic conversation memory?",
            "Successful OpenAI conversations without file attachments will be saved automatically in encrypted "
            "local storage and included as context in later OpenAI requests. Secret detection is best effort, so "
            "never use Memory for passwords, API keys, tokens or private keys. Enable automatic conversation memory?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            memory.enable_auto()
        except (ValueError, OSError) as error:
            self._error(error)
            return
        self._refresh()

    def _disable_auto(self) -> None:
        memory.disable_auto()
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
        selected = self.items.currentItem()
        if selected is None:
            return
        data = selected.data(Qt.ItemDataRole.UserRole)
        if not data or data[0] != "pinned":
            return
        try:
            memory.forget(int(data[1]))
        except (ValueError, OSError) as error:
            self._error(error)
            return
        self._refresh()

    def _search(self) -> None:
        query = self.search_entry.text().strip()
        if not query:
            self._refresh()
            return
        try:
            matches = memory.search(query)
        except (ValueError, OSError) as error:
            self._error(error)
            return
        self.items.clear()
        for kind, number, text in matches:
            label = "Pinned" if kind == "pinned" else "You" if kind == "user" else "AI"
            self._add_item(f"{label}: {text}", kind, number)
        self.state_label.setText(f"Search results for “{query}”: {len(matches)} match{'es' if len(matches) != 1 else ''}.")
        self._sync_controls()

    def _clear(self) -> None:
        answer = QMessageBox.warning(
            self,
            "Clear all memory?",
            "Remove every pinned item and all remembered conversation turns? Local Memory will remain ON and the "
            "automatic-memory setting will be unchanged, but removed memory cannot be recovered from HackersGhost AI.",
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
            "Erase Memory and key?",
            "This turns Local Memory and automatic conversation memory off and removes the encrypted memory file "
            "plus its encryption key from the Linux keyring. Saved memory cannot be recovered from HackersGhost AI "
            "after this. Continue?",
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
