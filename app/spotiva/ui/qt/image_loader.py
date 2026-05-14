from __future__ import annotations

from urllib.request import urlopen

from PyQt6.QtCore import QThread, pyqtSignal


class ImageBytesLoader(QThread):
    completed = pyqtSignal(str, bytes)
    failed = pyqtSignal(str)

    def __init__(self, url: str, timeout: int, parent=None) -> None:
        super().__init__(parent)
        self._url = url
        self._timeout = timeout

    def run(self) -> None:
        try:
            with urlopen(self._url, timeout=self._timeout) as response:
                self.completed.emit(self._url, response.read())
        except Exception:
            self.failed.emit(self._url)
