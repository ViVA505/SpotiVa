from __future__ import annotations

from abc import ABC, abstractmethod

from spotiva.core.constants import DEFAULT_TITLE_SEARCH_SOURCE
from spotiva.domain.entities.track import Track


class DownloadCatalogRepository(ABC):
    @abstractmethod
    def search_tracks(
        self,
        query: str,
        limit: int,
        artist_name: str = "",
        source: str = DEFAULT_TITLE_SEARCH_SOURCE,
    ) -> list[Track]:
        raise NotImplementedError
