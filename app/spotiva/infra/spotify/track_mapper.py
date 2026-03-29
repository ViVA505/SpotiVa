from __future__ import annotations

from collections.abc import Mapping

from spotiva.domain.entities.track import Album, Artist, Track, TrackImage


class SpotifyTrackMapper:
    def map_track(self, payload: Mapping[str, object]) -> Track:
        album_payload = self._as_mapping(payload.get("album"))
        images_payload = album_payload.get("images", [])
        artists_payload = payload.get("artists", [])

        album = Album(
            name=str(album_payload.get("name", "Unknown Album")),
            release_date=str(album_payload.get("release_date", "")),
            images=[
                TrackImage(
                    url=str(image.get("url", "")),
                    width=int(image.get("width") or 0),
                    height=int(image.get("height") or 0),
                )
                for image in images_payload
                if isinstance(image, Mapping)
            ],
            spotify_url=str(self._as_mapping(album_payload.get("external_urls")).get("spotify", "")),
        )

        artists = [
            Artist(
                name=str(artist.get("name", "Unknown Artist")),
                spotify_url=str(self._as_mapping(artist.get("external_urls")).get("spotify", "")),
            )
            for artist in artists_payload
            if isinstance(artist, Mapping)
        ]

        return Track(
            track_id=str(payload.get("id", "")),
            name=str(payload.get("name", "Unknown Track")),
            artists=artists,
            album=album,
            duration_ms=int(payload.get("duration_ms") or 0),
            spotify_url=str(self._as_mapping(payload.get("external_urls")).get("spotify", "")),
            external_url=str(self._as_mapping(payload.get("external_urls")).get("spotify", "")),
            source_label="Spotify",
            preview_url=self._to_optional_string(payload.get("preview_url")),
            is_explicit=bool(payload.get("explicit", False)),
            popularity=int(payload.get("popularity") or 0),
        )

    def _as_mapping(self, value: object) -> Mapping[str, object]:
        if isinstance(value, Mapping):
            return value
        return {}

    def _to_optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None
