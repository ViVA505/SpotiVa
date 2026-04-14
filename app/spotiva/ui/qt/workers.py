from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from spotiva.domain.entities.track import Track, TrackImage
from spotiva.ui.ctrl.main_ctrl import MainWindowController


class TrackSearchWorker(QThread):
    completed = pyqtSignal(list, object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        controller: MainWindowController,
        query: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._query = query

    def run(self) -> None:
        try:
            tracks = self._controller.load_tracks(self._query)
            prepared_tracks, artwork_payloads = self._warmup_artwork(tracks)
            self.completed.emit(prepared_tracks, artwork_payloads)
        except Exception as error:
            self.failed.emit(str(error))

    def _warmup_artwork(
        self,
        tracks: list[Track],
    ) -> tuple[list[Track], dict[str, bytes]]:
        resolved_tracks = self._resolve_artwork_urls(tracks)
        artwork_payloads = self._download_artwork_payloads(resolved_tracks)
        return resolved_tracks, artwork_payloads

    def _resolve_artwork_urls(self, tracks: list[Track]) -> list[Track]:
        if not tracks:
            return []

        with ThreadPoolExecutor(max_workers=min(6, len(tracks))) as executor:
            return list(executor.map(self._resolve_track_artwork, tracks))

    def _resolve_track_artwork(self, track: Track) -> Track:
        if track.best_image_url():
            return track

        artwork_url = self._controller.resolve_track_artwork(track)
        if not artwork_url:
            return track

        updated_album = replace(track.album, images=[TrackImage(url=artwork_url)])
        return replace(track, album=updated_album)

    def _download_artwork_payloads(self, tracks: list[Track]) -> dict[str, bytes]:
        unique_urls: list[str] = []
        seen: set[str] = set()
        for track in tracks:
            artwork_url = track.best_image_url()
            if not artwork_url or artwork_url in seen:
                continue
            seen.add(artwork_url)
            unique_urls.append(artwork_url)

        if not unique_urls:
            return {}

        with ThreadPoolExecutor(max_workers=min(6, len(unique_urls))) as executor:
            results = executor.map(self._download_artwork_payload, unique_urls)

        payloads: dict[str, bytes] = OrderedDict()
        for item in results:
            if item is None:
                continue
            url, payload = item
            payloads[url] = payload
        return payloads

    def _download_artwork_payload(self, url: str) -> tuple[str, bytes] | None:
        try:
            response = requests.get(
                url,
                timeout=self._controller.request_timeout(),
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
        except requests.RequestException:
            return None
        return (url, response.content)


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
