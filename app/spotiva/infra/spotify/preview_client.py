from __future__ import annotations

import json
import re
from collections.abc import Mapping

import requests
try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:
    BeautifulSoup = None

from spotiva.core.constants import DEFAULT_REQUEST_TIMEOUT
from spotiva.core.exceptions import SpotifyApiError
from spotiva.domain.entities.track import Album, Artist, Track, TrackImage


class SpotifyPublicPreviewClient:
    def __init__(self, request_timeout: int = DEFAULT_REQUEST_TIMEOUT) -> None:
        self._request_timeout = max(5, int(request_timeout))
        self._session = requests.Session()

    def resolve_track(self, spotify_url: str, track_id: str) -> Track:
        page_html = self._request_page(spotify_url)
        page_data = self._extract_page_metadata(page_html)
        oembed_data = self._request_oembed(spotify_url)

        title = page_data["title"] or str(oembed_data.get("title", "Spotify track")).strip() or "Spotify track"
        thumbnail_url = page_data["image_url"] or str(oembed_data.get("thumbnail_url", "")).strip()
        artist_name = page_data["artist"] or self._extract_artist_name(page_html)
        album_name = page_data["album"] or "Spotify"

        album = Album(
            name=album_name,
            images=[TrackImage(url=thumbnail_url)] if thumbnail_url else [],
            spotify_url=spotify_url,
        )

        artist = Artist(name=artist_name or "Unknown artist", spotify_url=spotify_url)

        return Track(
            track_id=track_id,
            name=title,
            artists=[artist],
            album=album,
            duration_ms=0,
            spotify_url=spotify_url,
            external_url=spotify_url,
            source_label="Spotify",
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
            raise SpotifyApiError(f"Could not load Spotify link preview: {error}") from error

        data = response.json()
        if not isinstance(data, dict):
            raise SpotifyApiError("Spotify returned an unexpected oEmbed response.")
        return data

    def _request_page(self, spotify_url: str) -> str:
        try:
            response = self._session.get(
                spotify_url,
                timeout=self._request_timeout,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
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

        match = re.search(r'<meta property="og:description" content="([^"]+)"', html)
        if not match:
            return ""

        description = match.group(1).strip()
        if not description:
            return ""

        parts = [part.strip() for part in re.split(r"\s*[В·вЂў]\s*", description) if part.strip()]
        if not parts:
            return ""
        return parts[0]

    def _extract_page_metadata(self, html: str) -> dict[str, str]:
        result = {
            "title": "",
            "artist": "",
            "image_url": "",
            "album": "Spotify",
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

            if title:
                result["title"] = title
            if image_url:
                result["image_url"] = image_url
            if artist_name:
                result["artist"] = artist_name

            if result["title"] and result["artist"]:
                break

        if not result["artist"]:
            content = self._extract_meta_property(html, "og:description")
            parts = [part.strip() for part in re.split(r"\s*[Р’В·РІР‚Сћ]\s*", content) if part.strip()]
            if parts:
                result["artist"] = parts[0].replace("Song", "").strip()

        if not result["image_url"]:
            result["image_url"] = self._extract_meta_property(html, "og:image")

        return result

    def _extract_json_ld_chunks(self, html: str) -> list[str]:
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            return [
                script_tag.get_text(strip=True)
                for script_tag in soup.find_all("script", attrs={"type": "application/ld+json"})
                if script_tag.get_text(strip=True)
            ]

        pattern = re.compile(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            re.IGNORECASE | re.DOTALL,
        )
        return [match.group(1).strip() for match in pattern.finditer(html) if match.group(1).strip()]

    def _extract_meta_property(self, html: str, property_name: str) -> str:
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            tag = soup.find("meta", property=property_name)
            if tag:
                return str(tag.get("content", "")).strip()
            return ""

        pattern = re.compile(
            rf'<meta[^>]+property=["\']{re.escape(property_name)}["\'][^>]+content=["\']([^"\']+)["\']',
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
        artist_payload = payload.get("byArtist") or payload.get("creator") or payload.get("author")
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

    def _extract_image_url(self, value: object) -> str:
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
        if isinstance(value, str):
            return value.strip()
        return ""
