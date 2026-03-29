from __future__ import annotations

from spotiva.domain.entities.track import Track
from spotiva.domain.repos.spotify_repo import SpotifyCatalogRepository
from spotiva.infra.spotify.spotify_api_client import SpotifyApiClient
from spotiva.infra.spotify.track_mapper import SpotifyTrackMapper


class SpotifyCatalogRepositoryImpl(SpotifyCatalogRepository):
    def __init__(self, api_client: SpotifyApiClient, track_mapper: SpotifyTrackMapper) -> None:
        self._api_client = api_client
        self._track_mapper = track_mapper

    def search_tracks(self, query: str, limit: int) -> list[Track]:
        payloads = self._api_client.search_tracks(query, limit)
        return [self._track_mapper.map_track(payload) for payload in payloads]

    def get_track_by_id(self, track_id: str) -> Track:
        payload = self._api_client.get_track(track_id)
        return self._track_mapper.map_track(payload)
