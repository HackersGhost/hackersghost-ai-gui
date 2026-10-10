APP_STYLE = """
QMainWindow, QDialog, QMessageBox {
    background: #111418;
}
QWidget {
    color: #e8edf2;
    font-family: Inter, Segoe UI, Arial, sans-serif;
    font-size: 14px;
}
QMenuBar, QMenu {
    background: #171b21;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: #303945;
}
QMenu::item {
    padding: 8px 16px;
}
QLabel#AppTitle {
    font-size: 22px;
    font-weight: 700;
}
QLabel#Muted {
    color: #9aa7b4;
}
QFrame#Sidebar {
    background: #171b21;
    border-right: 1px solid #2a313a;
}
QFrame#ChatPane {
    background: #0f1216;
    border: 1px solid #2a313a;
    border-radius: 8px;
}
QTextEdit#ChatOutput {
    background: transparent;
    border: none;
    color: #e8edf2;
    padding: 12px;
}
QLineEdit, QComboBox, QPlainTextEdit {
    background: #171b21;
    border: 1px solid #303945;
    border-radius: 6px;
    padding: 10px 12px;
    selection-background-color: #2f81f7;
}
QLineEdit:focus {
    border-color: #4da3ff;
}
QPushButton, QToolButton {
    background: #2f81f7;
    border: none;
    border-radius: 6px;
    color: white;
    font-weight: 600;
    padding: 10px 16px;
}
QPushButton:hover, QToolButton:hover {
    background: #4d96ff;
}
QToolButton {
    padding: 6px;
}
QPushButton:pressed {
    background: #1f6feb;
}
QPushButton:disabled, QToolButton:disabled {
    background: #303945;
    color: #8b949e;
}
QGroupBox {
    border: 1px solid #303945;
    border-radius: 8px;
    margin-top: 10px;
    padding: 12px;
    color: #cbd5df;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
"""
