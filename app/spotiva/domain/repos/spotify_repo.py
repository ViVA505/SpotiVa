from __future__ import annotations

from abc import ABC, abstractmethod

from spotiva.domain.entities.track import Track


class SpotifyCatalogRepository(ABC):
    @abstractmethod
    def search_tracks(self, query: str, limit: int) -> list[Track]:
        raise NotImplementedError

    @abstractmethod
    def get_track_by_id(self, track_id: str) -> Track:
        raise NotImplementedError
