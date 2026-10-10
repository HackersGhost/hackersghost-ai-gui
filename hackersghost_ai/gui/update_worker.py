from PySide6.QtCore import QThread, Signal

from hackersghost_ai.core.update_service import UpdateError


class UpdateWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, service, parent=None, *, release=None, destination=None):
        super().__init__(parent)
        self.service = service
        self.release = release
        self.destination = destination

    def run(self):
        try:
            if self.release is None:
                result = self.service.check()
            else:
                result = self.service.download_release(self.release, self.destination)
            self.succeeded.emit(result)
        except UpdateError as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit("The update operation failed. The installed application was not changed.")
