from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from spotiva.core.constants import SUPPORTED_RESOURCE_TYPES
from spotiva.core.exceptions import (
    InvalidSpotifyLinkError,
    UnsupportedSpotifyResourceError,
)


@dataclass(frozen=True)
class SpotifyResource:
    resource_type: str
    resource_id: str


class SpotifyLinkParser:
    def looks_like_spotify_link(self, value: str) -> bool:
        normalized = value.strip()
        return "spotify.com/" in normalized or normalized.startswith("spotify:")

    def parse(self, value: str) -> SpotifyResource:
        normalized = value.strip()
        if not normalized:
            raise InvalidSpotifyLinkError("The Spotify link is empty.")

        if normalized.startswith("spotify:"):
            return self._parse_uri(normalized)
        return self._parse_web_url(normalized)

    def _parse_uri(self, value: str) -> SpotifyResource:
        parts = [part for part in value.split(":") if part]
        if len(parts) < 3:
            raise InvalidSpotifyLinkError("The Spotify URI format is invalid.")
        resource_type = parts[-2].lower()
        resource_id = parts[-1].strip()
        return self._build_resource(resource_type, resource_id)

    def _parse_web_url(self, value: str) -> SpotifyResource:
        parsed_url = urlparse(value)
        if "spotify.com" not in parsed_url.netloc:
            raise InvalidSpotifyLinkError("The provided URL is not a Spotify URL.")

        path_parts = [part for part in parsed_url.path.split("/") if part]
        if not path_parts:
            raise InvalidSpotifyLinkError("The Spotify URL does not contain a resource path.")

        resource_index = None
        for index, part in enumerate(path_parts):
            if part.lower() in {"track", "album", "artist", "playlist", "episode", "show"}:
                resource_index = index
                break

        if resource_index is None or resource_index + 1 >= len(path_parts):
            raise InvalidSpotifyLinkError("The Spotify URL does not contain a valid resource ID.")

        resource_type = path_parts[resource_index].lower()
        resource_id = path_parts[resource_index + 1].strip()
        return self._build_resource(resource_type, resource_id)

    def _build_resource(self, resource_type: str, resource_id: str) -> SpotifyResource:
        if not resource_id:
            raise InvalidSpotifyLinkError("The Spotify resource ID is missing.")
        if resource_type not in SUPPORTED_RESOURCE_TYPES:
            raise UnsupportedSpotifyResourceError(
                f"Only Spotify track links are supported right now, got '{resource_type}'."
            )
        return SpotifyResource(resource_type=resource_type, resource_id=resource_id)
