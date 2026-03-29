from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping

import yt_dlp

from spotiva.core.exceptions import CatalogApiError
from spotiva.core.title_sources import normalize_title_search_source, title_search_source_label
from spotiva.infra.downloader.models import DownloadSearchResult


class YtDlpSearchClient:
    def __init__(self, cache_size: int = 48) -> None:
        self._cache_size = max(8, cache_size)
        self._cache: OrderedDict[tuple[str, str, str, int], list[DownloadSearchResult]] = OrderedDict()

    def search(self, query: str, limit: int, source: str, artist_name: str = "") -> list[DownloadSearchResult]:
        normalized_source = normalize_title_search_source(source)
        normalized_query = query.strip()
        normalized_artist = artist_name.strip()
        normalized_limit = max(1, min(limit, 10))
        cache_key = (
            normalized_source,
            normalized_query.casefold(),
            normalized_artist.casefold(),
            normalized_limit,
        )
        cached_results = self._cache.get(cache_key)
        if cached_results is not None:
            self._cache.move_to_end(cache_key)
            return list(cached_results)

        search_target = self._build_search_target(
            query=normalized_query,
            limit=normalized_limit,
            source=normalized_source,
            artist_name=normalized_artist,
        )
        ydl_options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "extract_flat": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                payload = ydl.extract_info(search_target, download=False)
        except Exception as error:
            source_name = title_search_source_label(normalized_source)
            raise CatalogApiError(f"Could not search {source_name}: {error}") from error

        if not isinstance(payload, Mapping):
            return []

        entries = payload.get("entries")
        if not isinstance(entries, list):
            return []

        results: list[DownloadSearchResult] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            mapped = self._map_entry(entry, normalized_source)
            if mapped and mapped.page_url:
                results.append(mapped)
        self._remember(cache_key, results)
        return list(results)

    def _build_search_target(self, query: str, limit: int, source: str, artist_name: str) -> str:
        search_limit = max(1, min(limit, 10))
        search_text = " ".join(part for part in (artist_name.strip(), query.strip()) if part).strip()
        if source == "soundcloud":
            return f"scsearch{search_limit}:{search_text}"
        return f"ytsearch{search_limit}:{search_text} official audio"

    def _map_entry(self, entry: Mapping[str, object], source: str) -> DownloadSearchResult | None:
        title = self._clean_text(entry.get("title"), "Unknown Title")
        artist = self._clean_artist(entry)
        page_url = self._resolve_page_url(entry, source)
        if not page_url:
            return None

        duration_ms = self._extract_duration_ms(entry.get("duration"))
        image_url = self._extract_image_url(entry.get("thumbnails"))
        album = self._clean_text(
            entry.get("album") or entry.get("playlist_title") or entry.get("channel"),
            "Single",
        )
        source_id = self._clean_text(entry.get("id") or entry.get("url"), title)

        return DownloadSearchResult(
            source=source,
            source_id=source_id,
            title=title,
            artist=artist,
            page_url=page_url,
            image_url=image_url,
            album=album,
            duration_ms=duration_ms,
        )

    def _clean_artist(self, entry: Mapping[str, object]) -> str:
        artist = self._extract_artist_text(entry)
        return artist.removesuffix(" - Topic").strip() or "Unknown Artist"

    def _extract_artist_text(self, entry: Mapping[str, object]) -> str:
        explicit_artist = self._clean_text(entry.get("artist"), "")
        if explicit_artist:
            return explicit_artist

        raw_artists = entry.get("artists")
        if isinstance(raw_artists, list):
            artist_names: list[str] = []
            for item in raw_artists:
                if isinstance(item, Mapping):
                    name = self._clean_text(item.get("name"), "")
                else:
                    name = self._clean_text(item, "")
                if name:
                    artist_names.append(name)
            if artist_names:
                return ", ".join(artist_names)

        return self._clean_text(
            entry.get("uploader")
            or entry.get("channel")
            or entry.get("channel_uploader"),
            "Unknown Artist",
        )

    def _resolve_page_url(self, entry: Mapping[str, object], source: str) -> str:
        for key in ("webpage_url", "original_url", "permalink_url", "url"):
            value = self._clean_text(entry.get(key), "")
            if value.startswith("http://") or value.startswith("https://"):
                return value

        raw_id = self._clean_text(entry.get("id") or entry.get("url"), "")
        if not raw_id:
            return ""
        if source == "soundcloud":
            return raw_id
        return f"https://www.youtube.com/watch?v={raw_id}"

    @staticmethod
    def _extract_duration_ms(value: object) -> int:
        try:
            duration_seconds = int(float(value or 0))
        except (TypeError, ValueError):
            return 0
        return max(0, duration_seconds * 1000)

    @staticmethod
    def _extract_image_url(value: object) -> str:
        if not isinstance(value, list):
            return ""

        for item in reversed(value):
            if not isinstance(item, Mapping):
                continue
            url = str(item.get("url", "")).strip()
            if url:
                return url
        return ""

    @staticmethod
    def _clean_text(value: object, default: str) -> str:
        text = str(value or "").strip()
        return text or default

    def _remember(self, key: tuple[str, str, str, int], value: list[DownloadSearchResult]) -> None:
        self._cache[key] = list(value)
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
