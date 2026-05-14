from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from spotiva.ui.ctrl.main_ctrl import MainWindowController


class TrackSearchWorker(QThread):
    completed = pyqtSignal(list, object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        controller: MainWindowController,
        query: str,
        search_mode: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._query = query
        self._search_mode = search_mode

    def run(self) -> None:
        try:
            tracks = self._controller.load_tracks(self._query, self._search_mode)
            self.completed.emit(tracks, {})
        except Exception as error:
            self.failed.emit(str(error))


class ArtworkResolveWorker(QThread):
    completed = pyqtSignal(str, str)
    failed = pyqtSignal(str, str)

    def __init__(
        self,
        controller: MainWindowController,
        track: Track,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._track = track

    def run(self) -> None:
        try:
            artwork_url = self._controller.resolve_track_artwork(self._track)
            if artwork_url:
                self.completed.emit(self._track.track_id, artwork_url)
        except Exception as error:
            self.failed.emit(self._track.track_id, str(error))


class TrackDownloadWorker(QThread):
    progressed = pyqtSignal(int, int)
    completed = pyqtSignal(object, str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        controller: MainWindowController,
        track: Track,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._track = track

    def run(self) -> None:
        try:
            file_path = self._controller.download_track(
                self._track,
                self._emit_progress,
            )
            self.completed.emit(self._track, file_path)
        except Exception as error:
            self.failed.emit(str(error))

    def _emit_progress(self, bytes_written: int, total_bytes: int) -> None:
        self.progressed.emit(bytes_written, total_bytes)
