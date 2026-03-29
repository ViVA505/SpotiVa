from __future__ import annotations

from spotiva.core.constants import DEFAULT_SEARCH_LIMIT
from spotiva.domain.entities.track import Track
from spotiva.domain.repos.spotify_repo import SpotifyCatalogRepository


class SearchTracksUseCase:
    def __init__(self, repository: SpotifyCatalogRepository) -> None:
        self._repository = repository

    def execute(self, query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[Track]:
        normalized = query.strip()
        if not normalized:
            raise ValueError("Enter a track title or paste a Spotify track link.")
        return self._repository.search_tracks(normalized, limit)
