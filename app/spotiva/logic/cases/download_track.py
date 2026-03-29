from __future__ import annotations

from collections.abc import Callable

from spotiva.domain.entities.track import Track
from spotiva.domain.repos.audio_repo import AudioAssetRepository


class DownloadTrackAssetUseCase:
    def __init__(self, repository: AudioAssetRepository) -> None:
        self._repository = repository

    def execute(self, track: Track, progress_callback: Callable[[int, int], None] | None = None) -> str:
        if not track.is_downloadable:
            raise ValueError("This result cannot be downloaded.")
        return self._repository.download_track(track, progress_callback)
