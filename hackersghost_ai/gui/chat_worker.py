from PySide6.QtCore import QThread, Signal

from hackersghost_ai.core.errors import ChatError


class ChatWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, service, prompt: str, session_key: str, parent=None, *,
                 attachment=None, attachment_confirmed=False):
        super().__init__(parent)
        self.service = service
        self.prompt = prompt
        self._session_key = session_key
        self.attachment = attachment
        self.attachment_confirmed = attachment_confirmed

    def run(self):
        try:
            self.succeeded.emit(self.service.send(
                self.prompt, self._session_key, attachment=self.attachment,
                attachment_confirmed=self.attachment_confirmed,
            ))
        except ChatError as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit("The request could not be completed. Please try again.")
        finally:
            self._session_key = ""
            self.prompt = ""
            self.attachment = None
