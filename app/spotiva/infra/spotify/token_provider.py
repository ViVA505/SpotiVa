from __future__ import annotations

import base64
import threading
import time

import requests

from spotiva.core.constants import DEFAULT_REQUEST_TIMEOUT
from spotiva.core.constants import SPOTIFY_ACCOUNTS_URL
from spotiva.core.exceptions import ConfigurationError, SpotifyApiError


class SpotifyAccessTokenProvider:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        self._client_id = client_id.strip()
        self._client_secret = client_secret.strip()
        self._request_timeout = max(5, int(request_timeout))
        self._access_token = ""
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def get_access_token(self) -> str:
        if not self._has_credentials():
            raise ConfigurationError("Spotify credentials are missing.")

        with self._lock:
            if self._access_token and time.time() < self._expires_at:
                return self._access_token

            credentials = f"{self._client_id}:{self._client_secret}"
            encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
            headers = {"Authorization": f"Basic {encoded}"}
            payload = {"grant_type": "client_credentials"}

            try:
                response = requests.post(
                    SPOTIFY_ACCOUNTS_URL,
                    data=payload,
                    headers=headers,
                    timeout=self._request_timeout,
                )
                response.raise_for_status()
            except requests.RequestException as error:
                raise SpotifyApiError(f"Could not get a Spotify access token: {error}") from error

            data = response.json()
            self._access_token = str(data.get("access_token", ""))
            expires_in = int(data.get("expires_in", 3600))
            self._expires_at = time.time() + max(60, expires_in - 30)

            if not self._access_token:
                raise SpotifyApiError("Spotify did not return an access token.")

            return self._access_token

    def invalidate(self) -> None:
        with self._lock:
            self._access_token = ""
            self._expires_at = 0.0

    def _has_credentials(self) -> bool:
        placeholder_values = {"", "your_client_id", "your_client_secret"}
        return (
            self._client_id not in placeholder_values
            and self._client_secret not in placeholder_values
        )
