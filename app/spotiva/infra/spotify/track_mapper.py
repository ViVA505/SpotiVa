from __future__ import annotations

from collections.abc import Mapping

from spotiva.domain.entities.track import Album, Artist, Track, TrackImage


class SpotifyTrackMapper:
    def map_track(self, payload: Mapping[str, object]) -> Track:
        album_payload = self._as_mapping(payload.get("album"))
        album = self._map_album_value(album_payload)
        artists = self._map_artists(payload.get("artists", []))

        return Track(
            track_id=str(payload.get("id", "")),
            name=str(payload.get("name", "Unknown Track")),
            artists=artists,
            album=album,
            duration_ms=int(payload.get("duration_ms") or 0),
            spotify_url=str(
                self._as_mapping(payload.get("external_urls")).get("spotify", "")
            ),
            external_url=str(
                self._as_mapping(payload.get("external_urls")).get("spotify", "")
            ),
            source_label="Spotify",
            preview_url=self._to_optional_string(payload.get("preview_url")),
            is_explicit=bool(payload.get("explicit", False)),
            popularity=int(payload.get("popularity") or 0),
        )

    def map_album(self, payload: Mapping[str, object]) -> Track:
        album = self._map_album_value(payload)
        artists = self._map_artists(payload.get("artists", []))
        track_payloads = self._as_mapping(payload.get("tracks")).get("items", [])
        album_tracks = [
            self._map_album_track(item, album)
            for item in track_payloads
            if isinstance(item, Mapping)
        ]

        return Track(
            track_id=str(payload.get("id", "")),
            name=album.name or str(payload.get("name", "Unknown Album")),
            artists=artists or [Artist(name="Unknown Artist")],
            album=album,
            duration_ms=0,
            spotify_url=str(
                self._as_mapping(payload.get("external_urls")).get("spotify", "")
            ),
            external_url=str(
                self._as_mapping(payload.get("external_urls")).get("spotify", "")
            ),
            source_label="Spotify",
            is_downloadable=True,
            item_type="album",
            item_count=len(album_tracks),
            album_tracks=album_tracks,
        )

    def _map_album_track(
        self,
        payload: Mapping[str, object],
        album: Album,
    ) -> Track:
        track_id = str(payload.get("id", "")).strip()
        track_url = str(
            self._as_mapping(payload.get("external_urls")).get("spotify", "")
        )
        if not track_url and track_id:
            track_url = f"https://open.spotify.com/track/{track_id}"

        return Track(
            track_id=track_id or str(payload.get("uri", "")),
            name=str(payload.get("name", "Unknown Track")),
            artists=self._map_artists(payload.get("artists", []))
            or [Artist(name="Unknown Artist")],
            album=album,
            duration_ms=int(payload.get("duration_ms") or 0),
            spotify_url=track_url,
            external_url=track_url,
            source_label="Spotify",
            preview_url=self._to_optional_string(payload.get("preview_url")),
            is_explicit=bool(payload.get("explicit", False)),
            popularity=int(payload.get("popularity") or 0),
            is_downloadable=True,
        )

    def _map_album_value(self, payload: Mapping[str, object]) -> Album:
        images_payload = payload.get("images", [])
        return Album(
            name=str(payload.get("name", "Unknown Album")),
            release_date=str(payload.get("release_date", "")),
            images=[
                TrackImage(
                    url=str(image.get("url", "")),
                    width=int(image.get("width") or 0),
                    height=int(image.get("height") or 0),
                )
                for image in images_payload
                if isinstance(image, Mapping)
            ],
            spotify_url=str(
                self._as_mapping(payload.get("external_urls")).get("spotify", "")
            ),
        )

    def _map_artists(self, payload: object) -> list[Artist]:
        if not isinstance(payload, list):
            return []

        return [
            Artist(
                name=str(artist.get("name", "Unknown Artist")),
                spotify_url=str(
                    self._as_mapping(artist.get("external_urls")).get("spotify", "")
                ),
            )
            for artist in payload
            if isinstance(artist, Mapping)
        ]

    def _as_mapping(self, value: object) -> Mapping[str, object]:
        if isinstance(value, Mapping):
            return value
        return {}

    def _to_optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None
