from __future__ import annotations

from difflib import SequenceMatcher

from spotiva.core.constants import DEFAULT_TITLE_SEARCH_SOURCE
from spotiva.domain.entities.track import Track
from spotiva.domain.repos.catalog_repo import DownloadCatalogRepository
from spotiva.infra.downloader.track_mapper import DownloadTrackMapper
from spotiva.infra.downloader.yt_dlp_search_client import YtDlpSearchClient


class YtDlpCatalogRepository(DownloadCatalogRepository):
    def __init__(self, search_client: YtDlpSearchClient, mapper: DownloadTrackMapper) -> None:
        self._search_client = search_client
        self._mapper = mapper

    def search_tracks(
        self,
        query: str,
        limit: int,
        artist_name: str = "",
        source: str = DEFAULT_TITLE_SEARCH_SOURCE,
    ) -> list[Track]:
        results = self._search_client.search(
            query=query,
            limit=limit,
            artist_name=artist_name,
            source=source,
        )
        tracks = [self._mapper.map_result(item) for item in results]
        ranked_tracks = sorted(
            tracks,
            key=lambda track: self._build_score(track, query, artist_name),
            reverse=True,
        )
        return ranked_tracks[:limit]

    def _build_score(self, track: Track, query: str, artist_name: str) -> float:
        query_text = query.lower().strip()
        title_text = track.name.lower().strip()
        title_score = SequenceMatcher(None, query_text, title_text).ratio()

        artist_score = 0.0
        if artist_name:
            artist_score = SequenceMatcher(
                None,
                artist_name.lower().strip(),
                track.primary_artist_name().lower().strip(),
            ).ratio()

        official_bonus = 0.04 if "official" in title_text else 0.0
        return (title_score * 0.8) + (artist_score * 0.2) + official_bonus
