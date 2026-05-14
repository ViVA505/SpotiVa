from __future__ import annotations

import json
import re
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor

import requests

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:
    BeautifulSoup = None

from spotiva.core.constants import DEFAULT_REQUEST_TIMEOUT
from spotiva.core.exceptions import SpotifyApiError
from spotiva.domain.entities.track import Album, Artist, Track, TrackImage
from spotiva.domain.repos.preview_repo import SpotifyPreviewRepository


class SpotifyPublicPreviewClient(SpotifyPreviewRepository):
    _NEXT_DATA_RE = re.compile(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        re.DOTALL,
    )
    _MUSIC_SONG_RE = re.compile(
        r'<meta name="music:song" content="([^"]+)"',
        re.IGNORECASE,
    )
    _META_SPLIT_RE = re.compile(r"\s*[·•|]\s*")

    def __init__(self, request_timeout: int = DEFAULT_REQUEST_TIMEOUT) -> None:
        self._request_timeout = max(5, int(request_timeout))
        self._session = requests.Session()

    def resolve_track(self, spotify_url: str, track_id: str) -> Track:
        page_html = self._request_page(spotify_url)
        page_data = self._extract_page_metadata(page_html)
        oembed_data = self._request_oembed(spotify_url)
        iframe_url = str(oembed_data.get("iframe_url", "")).strip()
        embed_html = self._request_embed_page(
            iframe_url or f"https://open.spotify.com/embed/track/{track_id}"
        )
        entity = self._extract_embed_entity(embed_html)

        title = (
            str(entity.get("title", "")).strip()
            or str(entity.get("name", "")).strip()
            or page_data["title"]
            or str(oembed_data.get("title", "Spotify track")).strip()
            or "Spotify track"
        )
        thumbnail_url = (
            self._extract_embed_image_url(entity)
            or page_data["image_url"]
            or str(oembed_data.get("thumbnail_url", "")).strip()
        )
        artists = self._extract_embed_artists(entity)
        if not artists:
            artist_name = page_data["artist"] or self._extract_artist_name(page_html)
            artists = self._build_artists(artist_name, spotify_url)
        album_name = page_data["album"] or "Spotify"
        release_date = page_data["release_date"] or self._extract_release_date(entity)
        duration_ms = self._normalize_duration_ms(entity.get("duration"))
        if duration_ms <= 0:
            duration_ms = self._extract_meta_duration_ms(page_html)
        preview_url = self._to_optional_string(
            self._as_mapping(entity.get("audioPreview")).get("url")
        )

        album = Album(
            name=album_name,
            release_date=release_date,
            images=[TrackImage(url=thumbnail_url)] if thumbnail_url else [],
            spotify_url=spotify_url,
        )

        return Track(
            track_id=track_id,
            name=title,
            artists=artists,
            album=album,
            duration_ms=duration_ms,
            spotify_url=spotify_url,
            external_url=spotify_url,
            source_label="Spotify",
            preview_url=preview_url,
            is_explicit=self._is_explicit_entity(entity),
        )

    def resolve_album(self, spotify_url: str, album_id: str) -> Track:
        page_html = self._request_page(spotify_url)
        page_data = self._extract_page_metadata(page_html)
        oembed_data = self._request_oembed(spotify_url)
        iframe_url = str(oembed_data.get("iframe_url", "")).strip()
        embed_html = self._request_embed_page(
            iframe_url or f"https://open.spotify.com/embed/album/{album_id}"
        )
        entity = self._extract_embed_entity(embed_html)

        title = (
            page_data["title"]
            or str(oembed_data.get("title", "")).strip()
            or str(entity.get("title", "")).strip()
            or str(entity.get("name", "")).strip()
            or "Spotify album"
        )
        artist_name = (
            page_data["artist"]
            or str(entity.get("subtitle", "")).strip()
            or "Unknown artist"
        )
        image_url = (
            page_data["image_url"]
            or str(oembed_data.get("thumbnail_url", "")).strip()
            or self._extract_embed_image_url(entity)
        )
        release_date = page_data["release_date"] or str(
            entity.get("releaseDate", "")
        ).strip()

        album = Album(
            name=title,
            release_date=release_date,
            images=[TrackImage(url=image_url)] if image_url else [],
            spotify_url=spotify_url,
        )
        artists = self._build_artists(artist_name, spotify_url)
        page_track_urls = self._extract_album_track_urls(page_html)
        embed_tracks = self._extract_album_tracks(entity, album)
        page_tracks = self._resolve_album_tracks_from_urls(
            page_track_urls,
            album,
            artist_name,
        )
        album_tracks = (
            page_tracks if len(page_tracks) > len(embed_tracks) else embed_tracks
        )
        if not album_tracks:
            album_tracks = page_tracks
        if not album_tracks:
            raise SpotifyApiError("Could not load the Spotify album track list.")

        return Track(
            track_id=album_id,
            name=title,
            artists=artists,
            album=album,
            duration_ms=0,
            spotify_url=spotify_url,
            external_url=spotify_url,
            source_label="Spotify",
            is_downloadable=True,
            item_type="album",
            item_count=len(album_tracks),
            album_tracks=album_tracks,
        )

    def _request_oembed(self, spotify_url: str) -> dict[str, object]:
        try:
            response = self._session.get(
                "https://open.spotify.com/oembed",
                params={"url": spotify_url},
                timeout=self._request_timeout,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise SpotifyApiError(
                f"Could not load Spotify link preview: {error}"
            ) from error

        data = response.json()
        if not isinstance(data, dict):
            raise SpotifyApiError("Spotify returned an unexpected oEmbed response.")
        return data

    def _resolve_album_tracks_from_urls(
        self,
        track_urls: list[str],
        album: Album,
        fallback_artist: str,
    ) -> list[Track]:
        if not track_urls:
            return []

        with ThreadPoolExecutor(max_workers=min(6, len(track_urls))) as executor:
            resolved_tracks = executor.map(
                lambda track_url: self._resolve_album_track_from_url(
                    track_url,
                    album,
                    fallback_artist,
                ),
                track_urls,
            )
            return [track for track in resolved_tracks if track is not None]

    def _request_page(self, spotify_url: str) -> str:
        return self._request_html(spotify_url)

    def _request_embed_page(self, embed_url: str) -> str:
        return self._request_html(embed_url)

    def _request_html(self, url: str) -> str:
        try:
            response = self._session.get(
                url,
                timeout=self._request_timeout,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; Googlebot/2.1; "
                        "+http://www.google.com/bot.html)"
                    ),
                    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                },
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            return ""

    def _extract_artist_name(self, html: str) -> str:
        if not html:
            return ""

        description = self._extract_meta_property(html, "og:description")
        if not description:
            return ""

        parts = self._split_meta_segments(description)
        return parts[0] if parts else ""

    def _extract_page_metadata(self, html: str) -> dict[str, str]:
        result = {
            "title": "",
            "artist": "",
            "image_url": "",
            "album": "Spotify",
            "release_date": "",
        }
        if not html:
            return result

        for raw_script in self._extract_json_ld_chunks(html):
            parsed = self._load_json_ld(raw_script)
            if not parsed:
                continue

            title = str(parsed.get("name", "")).strip()
            image_url = self._extract_image_url(parsed.get("image"))
            artist_name = self._extract_artist_from_json_ld(parsed)
            release_date = str(parsed.get("datePublished", "")).strip()
            item_type = str(parsed.get("@type", "")).strip()

            if title:
                result["title"] = title
            if image_url:
                result["image_url"] = image_url
            if artist_name:
                result["artist"] = artist_name
            if release_date:
                result["release_date"] = release_date
            if item_type == "MusicRecording":
                album_name = self._extract_album_name_from_json_ld(parsed)
                if album_name:
                    result["album"] = album_name
            elif item_type == "MusicAlbum" and title:
                result["album"] = title

        if not result["artist"]:
            content = self._extract_meta_property(html, "og:description")
            parts = self._split_meta_segments(content)
            if parts:
                result["artist"] = parts[0].replace("Song", "").strip()

        if not result["image_url"]:
            result["image_url"] = self._extract_meta_property(html, "og:image")

        if not result["title"]:
            result["title"] = self._extract_meta_property(html, "og:title")
            result["title"] = result["title"].replace(" | Spotify", "").strip()

        return result

    def _extract_json_ld_chunks(self, html: str) -> list[str]:
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            return [
                script_tag.get_text(strip=True)
                for script_tag in soup.find_all(
                    "script",
                    attrs={"type": "application/ld+json"},
                )
                if script_tag.get_text(strip=True)
            ]

        pattern = re.compile(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            re.IGNORECASE | re.DOTALL,
        )
        return [
            match.group(1).strip()
            for match in pattern.finditer(html)
            if match.group(1).strip()
        ]

    def _extract_meta_property(self, html: str, property_name: str) -> str:
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            tag = soup.find("meta", property=property_name)
            if tag:
                return str(tag.get("content", "")).strip()
            return ""

        pattern = re.compile(
            (
                rf'<meta[^>]+property=["\']{re.escape(property_name)}["\'][^>]+'
                rf'content=["\']([^"\']+)["\']'
            ),
            re.IGNORECASE,
        )
        match = pattern.search(html)
        if not match:
            return ""
        return match.group(1).strip()

    def _load_json_ld(self, raw_value: str) -> Mapping[str, object] | None:
        try:
            payload = json.loads(raw_value)
        except ValueError:
            return None

        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, Mapping):
                    return item
            return None

        if isinstance(payload, Mapping):
            return payload
        return None

    def _extract_artist_from_json_ld(self, payload: Mapping[str, object]) -> str:
        artist_payload = (
            payload.get("byArtist")
            or payload.get("creator")
            or payload.get("author")
        )
        if isinstance(artist_payload, list):
            artist_names = [
                str(item.get("name", "")).strip()
                for item in artist_payload
                if isinstance(item, Mapping) and str(item.get("name", "")).strip()
            ]
            return ", ".join(artist_names)
        if isinstance(artist_payload, Mapping):
            return str(artist_payload.get("name", "")).strip()
        return ""

    def _extract_album_name_from_json_ld(self, payload: Mapping[str, object]) -> str:
        album_payload = payload.get("inAlbum")
        if isinstance(album_payload, Mapping):
            return str(album_payload.get("name", "")).strip()
        return ""

    def _extract_image_url(self, value: object) -> str:
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
        if isinstance(value, str):
            return value.strip()
        return ""

    def _extract_embed_entity(self, html: str) -> Mapping[str, object]:
        if not html:
            return {}

        match = self._NEXT_DATA_RE.search(html)
        if not match:
            return {}

        try:
            payload = json.loads(match.group(1))
        except ValueError:
            return {}

        if not isinstance(payload, Mapping):
            return {}

        props = self._as_mapping(payload.get("props"))
        page_props = self._as_mapping(props.get("pageProps"))
        state = self._as_mapping(page_props.get("state"))
        data = self._as_mapping(state.get("data"))
        entity = self._as_mapping(data.get("entity"))
        return entity

    def _extract_album_track_urls(self, html: str) -> list[str]:
        if not html:
            return []

        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            urls = [
                str(tag.get("content", "")).strip()
                for tag in soup.find_all("meta", attrs={"name": "music:song"})
                if str(tag.get("content", "")).strip()
            ]
        else:
            urls = [
                match.group(1).strip()
                for match in self._MUSIC_SONG_RE.finditer(html)
                if match.group(1).strip()
            ]
        return self._unique_values(urls)

    def _extract_album_tracks(
        self,
        entity: Mapping[str, object],
        album: Album,
    ) -> list[Track]:
        raw_tracks = entity.get("trackList")
        if not isinstance(raw_tracks, list):
            return []

        album_tracks: list[Track] = []
        for index, item in enumerate(raw_tracks, start=1):
            if not isinstance(item, Mapping):
                continue

            track_uri = str(item.get("uri", "")).strip()
            track_id = self._spotify_id_from_uri(track_uri)
            track_url = (
                f"https://open.spotify.com/track/{track_id}" if track_id else ""
            )
            title = str(item.get("title", "")).strip() or f"Track {index}"
            artist_line = str(item.get("subtitle", "")).strip()
            artists = self._build_artists(artist_line, track_url)
            duration_ms = self._normalize_duration_ms(item.get("duration"))
            preview_url = self._to_optional_string(
                self._as_mapping(item.get("audioPreview")).get("url")
            )

            album_tracks.append(
                Track(
                    track_id=track_id or track_uri or f"{album.name}:{index}",
                    name=title,
                    artists=artists,
                    album=album,
                    duration_ms=duration_ms,
                    spotify_url=track_url,
                    external_url=track_url,
                    source_label="Spotify",
                    is_downloadable=True,
                    preview_url=preview_url,
                    is_explicit=bool(item.get("isExplicit", False)),
                )
            )

        return album_tracks

    def _resolve_album_track_from_url(
        self,
        track_url: str,
        album: Album,
        fallback_artist: str,
    ) -> Track | None:
        normalized_url = track_url.strip()
        if not normalized_url:
            return None

        page_html = self._request_page(normalized_url)
        page_data = self._extract_page_metadata(page_html)
        title = page_data["title"]
        if not title:
            return None

        artist_name = (
            page_data["artist"]
            or self._extract_artist_name(page_html)
            or fallback_artist
            or "Unknown artist"
        )
        track_id = self._spotify_id_from_url(normalized_url)

        return Track(
            track_id=track_id or normalized_url,
            name=title,
            artists=self._build_artists(artist_name, normalized_url),
            album=album,
            duration_ms=0,
            spotify_url=normalized_url,
            external_url=normalized_url,
            source_label="Spotify",
            is_downloadable=True,
        )

    def _extract_embed_image_url(self, entity: Mapping[str, object]) -> str:
        images = self._as_mapping(entity.get("visualIdentity")).get("image")
        if not isinstance(images, list):
            return ""

        best_url = ""
        best_size = -1
        for item in images:
            if not isinstance(item, Mapping):
                continue
            url = str(item.get("url", "")).strip()
            size = max(int(item.get("maxHeight") or 0), int(item.get("maxWidth") or 0))
            if url and size >= best_size:
                best_url = url
                best_size = size
        return best_url

    def _extract_embed_artists(self, entity: Mapping[str, object]) -> list[Artist]:
        raw_artists = entity.get("artists")
        if not isinstance(raw_artists, list):
            return []

        artists: list[Artist] = []
        for item in raw_artists:
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            artist_uri = str(item.get("uri", "")).strip()
            artist_id = self._spotify_id_from_uri(artist_uri)
            artist_url = (
                f"https://open.spotify.com/artist/{artist_id}" if artist_id else ""
            )
            artists.append(Artist(name=name, spotify_url=artist_url))
        return artists

    def _extract_release_date(self, entity: Mapping[str, object]) -> str:
        release_date = self._as_mapping(entity.get("releaseDate"))
        return str(release_date.get("isoString", "")).split("T", maxsplit=1)[0].strip()

    def _extract_meta_duration_ms(self, html: str) -> int:
        duration_seconds = self._extract_meta_name(html, "music:duration")
        try:
            return max(0, int(float(duration_seconds or 0) * 1000))
        except (TypeError, ValueError):
            return 0

    def _extract_meta_name(self, html: str, name: str) -> str:
        if not html:
            return ""
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            tag = soup.find("meta", attrs={"name": name})
            if tag:
                return str(tag.get("content", "")).strip()
            return ""

        pattern = re.compile(
            (
                rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+'
                rf'content=["\']([^"\']+)["\']'
            ),
            re.IGNORECASE,
        )
        match = pattern.search(html)
        if not match:
            return ""
        return match.group(1).strip()

    def _is_explicit_entity(self, entity: Mapping[str, object]) -> bool:
        if bool(entity.get("isExplicit", False)):
            return True
        labels = self._as_mapping(entity.get("contentRatings")).get("labels")
        if not isinstance(labels, list):
            return False
        return any(str(label).casefold() == "explicit" for label in labels)

    def _build_artists(self, artist_line: str, spotify_url: str) -> list[Artist]:
        normalized = artist_line.strip()
        if not normalized:
            return [Artist(name="Unknown artist", spotify_url=spotify_url)]

        artist_names = [
            part.strip()
            for part in re.split(r"\s*(?:,|&| feat\.?| ft\.?)\s*", normalized)
            if part.strip()
        ]
        return [
            Artist(name=name, spotify_url=spotify_url)
            for name in artist_names
        ] or [Artist(name="Unknown artist", spotify_url=spotify_url)]

    def _split_meta_segments(self, value: str) -> list[str]:
        return [
            part.strip()
            for part in self._META_SPLIT_RE.split(value or "")
            if part.strip()
        ]

    def _spotify_id_from_uri(self, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            return ""
        return normalized.rsplit(":", maxsplit=1)[-1].strip()

    def _spotify_id_from_url(self, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            return ""
        return normalized.rsplit("/", maxsplit=1)[-1].split("?", maxsplit=1)[0].strip()

    def _normalize_duration_ms(self, value: object) -> int:
        try:
            numeric_value = int(float(value or 0))
        except (TypeError, ValueError):
            return 0
        if 0 < numeric_value < 1000:
            return numeric_value * 1000
        return max(0, numeric_value)

    def _as_mapping(self, value: object) -> Mapping[str, object]:
        if isinstance(value, Mapping):
            return value
        return {}

    def _to_optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    def _unique_values(self, values: list[str]) -> list[str]:
        unique_values: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique_values.append(normalized)
        return unique_values
