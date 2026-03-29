from __future__ import annotations

from spotiva.logic.cases.search_tracks import SearchTracksUseCase
from spotiva.core.constants import DEFAULT_SEARCH_LIMIT
from spotiva.domain.entities.track import Track
from spotiva.domain.repos.spotify_repo import SpotifyCatalogRepository
from spotiva.domain.services.link_parser import SpotifyLinkParser


class ResolveTrackInputUseCase:
    def __init__(
        self,
        link_parser: SpotifyLinkParser,
        repository: SpotifyCatalogRepository,
        search_tracks_use_case: SearchTracksUseCase,
    ) -> None:
        self._link_parser = link_parser
        self._repository = repository
        self._search_tracks_use_case = search_tracks_use_case

    def execute(self, value: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[Track]:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Enter a track title or paste a Spotify track link.")

        if self._link_parser.looks_like_spotify_link(normalized):
            resource = self._link_parser.parse(normalized)
            return [self._repository.get_track_by_id(resource.resource_id)]

        return self._search_tracks_use_case.execute(normalized, limit)
