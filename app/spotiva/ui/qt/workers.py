from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from spotiva.domain.entities.track import Track
from spotiva.ui.ctrl.main_ctrl import MainWindowController


class TrackSearchWorker(QThread):
    completed = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, controller: MainWindowController, query: str, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._query = query

    def run(self) -> None:
        try:
            tracks = self._controller.load_tracks(self._query)
            self.completed.emit(tracks)
        except Exception as error:
            self.failed.emit(str(error))


class TrackDownloadWorker(QThread):
    progressed = pyqtSignal(int, int)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, controller: MainWindowController, track: Track, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._track = track

    def run(self) -> None:
        try:
            file_path = self._controller.download_track(self._track, self._emit_progress)
            self.completed.emit(file_path)
        except Exception as error:
            self.failed.emit(str(error))

    def _emit_progress(self, bytes_written: int, total_bytes: int) -> None:
        self.progressed.emit(bytes_written, total_bytes)
