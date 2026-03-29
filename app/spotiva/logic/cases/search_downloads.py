from __future__ import annotations

from spotiva.core.constants import DEFAULT_SEARCH_LIMIT, DEFAULT_TITLE_SEARCH_SOURCE
from spotiva.domain.entities.track import Track
from spotiva.domain.repos.catalog_repo import DownloadCatalogRepository


class SearchDownloadableTracksUseCase:
    def __init__(self, repository: DownloadCatalogRepository) -> None:
        self._repository = repository

    def execute(
        self,
        query: str,
        limit: int = DEFAULT_SEARCH_LIMIT,
        artist_name: str = "",
        source: str = DEFAULT_TITLE_SEARCH_SOURCE,
    ) -> list[Track]:
        normalized = query.strip()
        if not normalized:
            raise ValueError("Enter a track title or paste a Spotify track link.")
        return self._repository.search_tracks(
            query=normalized,
            limit=limit,
            artist_name=artist_name.strip(),
            source=source,
        )
