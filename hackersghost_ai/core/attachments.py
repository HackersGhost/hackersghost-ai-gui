"""Bounded text snapshots. Selecting a file never makes a network request."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import stat

from hackersghost_ai.core.errors import ChatError


FILE_LIMIT = 64 * 1024


@dataclass(frozen=True)
class TextAttachment:
    name: str
    text: str = field(repr=False)

    def __post_init__(self):
        if not self.name or len(self.name) > 255 or any(ord(c) < 32 for c in self.name):
            raise ChatError("The file name is not supported.")
        if not self.text:
            raise ChatError("The file is empty.")
        if self.size > FILE_LIMIT:
            raise ChatError("The file exceeds 64 KiB. Select a smaller text file.")
        if any(ord(c) < 32 and c not in "\t\r\n" or ord(c) == 127 for c in self.text):
            raise ChatError("Only plain UTF-8 text files are supported, not binary files.")

    @property
    def size(self) -> int:
        return len(self.text.encode("utf-8"))


def read_attachment(path: str | Path) -> TextAttachment:
    path = Path(path)
    try:
        # A FIFO must not block the UI; inspect the opened descriptor, not just the path.
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(path, flags), "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ChatError("Select a regular text file.")
            raw = handle.read(FILE_LIMIT + 1)
        if len(raw) > FILE_LIMIT:
            raise ChatError("The file exceeds 64 KiB. Select a smaller text file.")
        return TextAttachment(path.name, raw.decode("utf-8"))
    except UnicodeDecodeError:
        raise ChatError("Only plain UTF-8 text files are supported, not binary files.") from None
    except OSError:
        raise ChatError("The file could not be read. Check its location and permissions.") from None
