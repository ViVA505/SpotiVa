from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from spotiva.domain.entities.track import Track


class AudioAssetRepository(ABC):
    @abstractmethod
    def download_track(self, track: Track, progress_callback: Callable[[int, int], None] | None = None) -> str:
        raise NotImplementedError
