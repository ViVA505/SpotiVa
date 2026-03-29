from __future__ import annotations

from collections.abc import Mapping

import requests

from spotiva.core.constants import DEFAULT_MARKET, DEFAULT_REQUEST_TIMEOUT, SPOTIFY_API_BASE_URL
from spotiva.core.exceptions import SpotifyApiError
from spotiva.infra.spotify.token_provider import SpotifyAccessTokenProvider


class SpotifyApiClient:
    def __init__(
        self,
        token_provider: SpotifyAccessTokenProvider,
        market: str = DEFAULT_MARKET,
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        self._token_provider = token_provider
        self._market = market.strip().upper() or DEFAULT_MARKET
        self._request_timeout = max(5, int(request_timeout))
        self._session = requests.Session()

    def search_tracks(self, query: str, limit: int) -> list[Mapping[str, object]]:
        response = self._request(
            "search",
            params={
                "q": query,
                "type": "track",
                "limit": max(1, min(limit, 20)),
                "market": self._market,
            },
        )
        tracks = self._as_mapping(response.get("tracks"))
        items = tracks.get("items", [])
        return [item for item in items if isinstance(item, Mapping)]

    def get_track(self, track_id: str) -> Mapping[str, object]:
        return self._request(
            f"tracks/{track_id}",
            params={"market": self._market},
        )

    def _request(
        self,
        path: str,
        params: Mapping[str, object] | None = None,
        retry_on_unauthorized: bool = True,
    ) -> Mapping[str, object]:
        token = self._token_provider.get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{SPOTIFY_API_BASE_URL}/{path.lstrip('/')}"

        try:
            response = self._session.get(
                url,
                headers=headers,
                params=params,
                timeout=self._request_timeout,
            )
        except requests.RequestException as error:
            raise SpotifyApiError(f"Spotify request failed: {error}") from error

        if response.status_code == 401 and retry_on_unauthorized:
            self._token_provider.invalidate()
            return self._request(path, params=params, retry_on_unauthorized=False)

        if response.status_code >= 400:
            message = self._extract_error_message(response)
            raise SpotifyApiError(message)

        data = response.json()
        if not isinstance(data, Mapping):
            raise SpotifyApiError("Spotify returned an unexpected response payload.")
        return data

    def _extract_error_message(self, response: requests.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            data = {}

        error_payload = data.get("error", {}) if isinstance(data, Mapping) else {}
        if isinstance(error_payload, Mapping):
            detail = str(error_payload.get("message", "")).strip()
            if detail:
                return f"Spotify API error ({response.status_code}): {detail}"
        return f"Spotify API error ({response.status_code})."

    def _as_mapping(self, value: object) -> Mapping[str, object]:
        if isinstance(value, Mapping):
            return value
        return {}
