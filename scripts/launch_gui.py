"""Desktop entry point using the existing environment; never installs dependencies."""

import os
from pathlib import Path
import sys


PROJECT_DIR = Path(__file__).resolve().parents[1]


def main():
    os.chdir(PROJECT_DIR)
    sys.path.insert(0, str(PROJECT_DIR))
    from hackersghost_ai.gui.app import main as run_gui
    return run_gui()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        message = "HackersGhost AI could not start. Run scripts/run_gui.sh from the application folder to check the installation."
        print(message, file=sys.stderr)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication([])
            QMessageBox.critical(None, "HackersGhost AI", message)
        except Exception:
            pass
        sys.exit(1)
