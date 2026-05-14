from __future__ import annotations

from abc import ABC, abstractmethod

from spotiva.domain.entities.track import Track


class SpotifyPreviewRepository(ABC):
    @abstractmethod
    def resolve_track(self, spotify_url: str, track_id: str) -> Track:
        raise NotImplementedError

    @abstractmethod
    def resolve_album(self, spotify_url: str, album_id: str) -> Track:
        raise NotImplementedError
