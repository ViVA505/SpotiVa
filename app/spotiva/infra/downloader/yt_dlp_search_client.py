from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests
import yt_dlp

from spotiva.core.constants import DEFAULT_REQUEST_TIMEOUT
from spotiva.core.exceptions import CatalogApiError
from spotiva.core.title_sources import (
    normalize_title_search_source,
    title_search_source_label,
)
from spotiva.domain.repos.artwork_repo import ArtworkRepository
from spotiva.infra.downloader.models import DownloadSearchResult


class YtDlpSearchClient(ArtworkRepository):
    def __init__(
        self,
        cache_size: int = 48,
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        self._cache_size = max(8, cache_size)
        self._cache: OrderedDict[
            tuple[str, str, str, int],
            list[DownloadSearchResult],
        ] = OrderedDict()
        self._artwork_cache: OrderedDict[str, str] = OrderedDict()
        self._soundcloud_link_cache: OrderedDict[
            str,
            list[DownloadSearchResult],
        ] = OrderedDict()
        self._request_timeout = max(5, int(request_timeout))
        self._session = requests.Session()

    def search(
        self,
        query: str,
        limit: int,
        source: str,
        artist_name: str = "",
    ) -> list[DownloadSearchResult]:
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

        album_limit = self._album_search_limit(normalized_source, normalized_limit)
        with ThreadPoolExecutor(max_workers=2) as executor:
            track_future = executor.submit(
                self._search_track_results,
                normalized_query,
                normalized_limit,
                normalized_source,
                normalized_artist,
            )
            album_future = executor.submit(
                self._search_album_results,
                normalized_query,
                album_limit,
                normalized_source,
                normalized_artist,
            )

            track_results = track_future.result()
            try:
                album_results = album_future.result()
            except Exception:
                album_results = []

        results = self._dedupe_results(track_results + album_results)
        if normalized_source == "soundcloud":
            linked_results = self._resolve_soundcloud_linked_results(results[:4])
            results = self._dedupe_results(results + linked_results)
        self._remember(cache_key, results)
        return list(results)

    def resolve_artwork_url(self, item_url: str) -> str:
        normalized_url = item_url.strip()
        if not normalized_url:
            return ""

        cached = self._artwork_cache.get(normalized_url)
        if cached is not None:
            self._artwork_cache.move_to_end(normalized_url)
            return cached

        if "soundcloud.com" in normalized_url.casefold():
            resolved = self._resolve_soundcloud_artwork_url(normalized_url)
        else:
            resolved = self._resolve_youtube_artwork_url(normalized_url)

        self._artwork_cache[normalized_url] = resolved
        self._artwork_cache.move_to_end(normalized_url)
        while len(self._artwork_cache) > self._cache_size:
            self._artwork_cache.popitem(last=False)
        return resolved

    def _search_track_results(
        self,
        query: str,
        limit: int,
        source: str,
        artist_name: str,
    ) -> list[DownloadSearchResult]:
        search_target = self._build_track_search_target(
            query=query,
            limit=limit,
            source=source,
            artist_name=artist_name,
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
            source_name = title_search_source_label(source)
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
            mapped = self._map_track_entry(entry, source)
            if mapped and mapped.page_url:
                results.append(mapped)
        return results

    def _search_album_results(
        self,
        query: str,
        limit: int,
        source: str,
        artist_name: str,
    ) -> list[DownloadSearchResult]:
        if source == "soundcloud":
            return self._search_soundcloud_album_results(query, limit, artist_name)
        return self._search_youtube_album_results(query, limit, artist_name)

    def _search_youtube_album_results(
        self,
        query: str,
        limit: int,
        artist_name: str,
    ) -> list[DownloadSearchResult]:
        search_text = " ".join(
            part for part in (artist_name.strip(), query.strip()) if part
        ).strip()
        search_url = (
            "https://www.youtube.com/results?search_query="
            f"{quote(search_text)}&sp=EgIQAw%3D%3D"
        )
        ydl_options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "playlistend": max(1, min(limit, 5)),
        }

        try:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                payload = ydl.extract_info(search_url, download=False)
        except Exception:
            return []

        if not isinstance(payload, Mapping):
            return []

        entries = payload.get("entries")
        if not isinstance(entries, list):
            return []

        results: list[DownloadSearchResult] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            mapped = self._map_album_entry(entry, "youtube")
            if mapped and mapped.page_url:
                results.append(mapped)
        return results[:limit]

    def _search_soundcloud_album_results(
        self,
        query: str,
        limit: int,
        artist_name: str,
    ) -> list[DownloadSearchResult]:
        search_text = " ".join(
            part for part in (artist_name.strip(), query.strip()) if part
        ).strip()
        search_url = f"https://soundcloud.com/search/sets?q={quote(search_text)}"

        try:
            response = self._session.get(
                search_url,
                timeout=self._request_timeout,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
            )
            response.raise_for_status()
        except requests.RequestException:
            return []

        urls = self._extract_soundcloud_album_urls(response.text)
        if not urls:
            return []

        results: list[DownloadSearchResult] = []
        selected_urls = urls[:limit]
        if not selected_urls:
            return results

        with ThreadPoolExecutor(max_workers=min(3, len(selected_urls))) as executor:
            for mapped in executor.map(
                self._load_soundcloud_album_result,
                selected_urls,
            ):
                if mapped and mapped.page_url:
                    results.append(mapped)
        return results

    def _build_track_search_target(
        self,
        query: str,
        limit: int,
        source: str,
        artist_name: str,
    ) -> str:
        search_limit = max(1, min(limit, 10))
        search_text = " ".join(
            part for part in (artist_name.strip(), query.strip()) if part
        ).strip()
        if source == "soundcloud":
            return f"scsearch{search_limit}:{search_text}"
        return f"ytsearch{search_limit}:{search_text} official audio"

    def _resolve_soundcloud_linked_results(
        self,
        results: list[DownloadSearchResult],
    ) -> list[DownloadSearchResult]:
        candidate_urls = [
            item.page_url
            for item in results
            if item.source == "soundcloud"
            and item.item_type == "track"
            and item.page_url
            and self._looks_like_derivative_soundcloud_result(item)
        ]
        if not candidate_urls:
            return []

        resolved_results: list[DownloadSearchResult] = []
        with ThreadPoolExecutor(max_workers=min(3, len(candidate_urls))) as executor:
            for linked_items in executor.map(
                self._resolve_soundcloud_linked_items,
                candidate_urls,
            ):
                resolved_results.extend(linked_items)
        return resolved_results

    def _resolve_soundcloud_linked_items(
        self,
        item_url: str,
    ) -> list[DownloadSearchResult]:
        normalized_url = item_url.strip()
        if not normalized_url:
            return []

        cached = self._soundcloud_link_cache.get(normalized_url)
        if cached is not None:
            self._soundcloud_link_cache.move_to_end(normalized_url)
            return list(cached)

        info = self._load_soundcloud_info(normalized_url)
        if not isinstance(info, Mapping):
            self._remember_soundcloud_links(normalized_url, [])
            return []

        description = self._clean_text(info.get("description"), "")
        linked_urls = self._extract_soundcloud_urls(description)
        if not linked_urls:
            self._remember_soundcloud_links(normalized_url, [])
            return []

        linked_results: list[DownloadSearchResult] = []
        for linked_url in linked_urls:
            if linked_url.casefold() == normalized_url.casefold():
                continue
            linked_info = self._load_soundcloud_info(linked_url)
            if not isinstance(linked_info, Mapping):
                continue
            mapped = self._map_track_entry(linked_info, "soundcloud")
            if mapped and mapped.page_url:
                linked_results.append(mapped)

        linked_results = self._dedupe_results(linked_results)
        self._remember_soundcloud_links(normalized_url, linked_results)
        return list(linked_results)

    def _map_track_entry(
        self,
        entry: Mapping[str, object],
        source: str,
    ) -> DownloadSearchResult | None:
        title = self._clean_text(entry.get("title"), "Unknown Title")
        artist = self._clean_artist(entry)
        page_url = self._resolve_page_url(entry, source, item_type="track")
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

    def _load_soundcloud_info(self, url: str) -> Mapping[str, object] | None:
        ydl_options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception:
            return None
        if not isinstance(info, Mapping):
            return None
        return info

    def _map_album_entry(
        self,
        entry: Mapping[str, object],
        source: str,
    ) -> DownloadSearchResult | None:
        title = self._clean_text(entry.get("title"), "Unknown Album")
        artist = self._clean_artist(entry)
        page_url = self._resolve_page_url(entry, source, item_type="album")
        if not page_url:
            return None

        image_url = self._extract_image_url(entry.get("thumbnails"))
        source_id = self._clean_text(entry.get("id") or entry.get("url"), title)
        item_count = self._extract_item_count(
            entry.get("playlist_count")
            or entry.get("n_entries")
            or entry.get("entries")
        )

        return DownloadSearchResult(
            source=source,
            source_id=source_id,
            title=title,
            artist=artist,
            page_url=page_url,
            image_url=image_url,
            album=title,
            item_type="album",
            item_count=item_count,
        )

    def _map_soundcloud_album_info(
        self,
        info: Mapping[str, object],
        url: str,
    ) -> DownloadSearchResult | None:
        title = self._clean_text(info.get("title"), "Unknown Album")
        artist = self._clean_text(info.get("uploader"), "Unknown Artist")
        image_url = self._extract_image_url(info.get("thumbnails"))
        item_count = self._extract_item_count(info.get("entries"))
        source_id = self._clean_text(info.get("id") or url, title)

        return DownloadSearchResult(
            source="soundcloud",
            source_id=source_id,
            title=title,
            artist=artist,
            page_url=url,
            image_url=image_url,
            album=title,
            item_type="album",
            item_count=item_count,
        )

    def _load_soundcloud_album_result(self, url: str) -> DownloadSearchResult | None:
        ydl_options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "ignoreerrors": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception:
            return None
        if not isinstance(info, Mapping) or "entries" not in info:
            return None
        return self._map_soundcloud_album_info(info, url)

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

    def _resolve_page_url(
        self,
        entry: Mapping[str, object],
        source: str,
        item_type: str,
    ) -> str:
        for key in ("webpage_url", "original_url", "permalink_url", "url"):
            value = self._clean_text(entry.get(key), "")
            if value.startswith("http://") or value.startswith("https://"):
                return value

        raw_id = self._clean_text(entry.get("id") or entry.get("url"), "")
        if not raw_id:
            return ""
        if source == "soundcloud":
            return raw_id
        if item_type == "album":
            return f"https://www.youtube.com/playlist?list={raw_id}"
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

    @staticmethod
    def _looks_like_derivative_soundcloud_result(item: DownloadSearchResult) -> bool:
        normalized_title = item.title.casefold()
        derivative_markers = (
            "cover",
            "кавер",
            "remix",
            "bootleg",
            "edit",
            "nightcore",
            "sped up",
            "slowed",
        )
        return any(marker in normalized_title for marker in derivative_markers)

    @staticmethod
    def _extract_soundcloud_urls(text: str) -> list[str]:
        matches = re.findall(
            r"https?://soundcloud\.com/[^\s)\]}]+",
            text,
            flags=re.IGNORECASE,
        )
        filtered_urls: list[str] = []
        for match in matches:
            normalized = match.rstrip(".,!?;:")
            if "/sets/" in normalized.casefold():
                continue
            filtered_urls.append(normalized)
        return YtDlpSearchClient._unique_values(filtered_urls)

    @staticmethod
    def _album_search_limit(source: str, limit: int) -> int:
        if source == "soundcloud":
            return min(max(2, limit), 3)
        return min(max(3, limit), 4)

    def _resolve_soundcloud_artwork_url(self, album_url: str) -> str:
        ydl_options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "ignoreerrors": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                info = ydl.extract_info(album_url, download=False)
        except Exception:
            return ""

        if not isinstance(info, Mapping):
            return ""

        image_url = self._extract_image_url(info.get("thumbnails"))
        if image_url:
            return image_url

        entries = info.get("entries")
        if not isinstance(entries, list) or not entries:
            return ""

        first_entry = entries[0]
        if not isinstance(first_entry, Mapping):
            return ""

        first_track_url = self._clean_text(
            first_entry.get("url") or first_entry.get("webpage_url"),
            "",
        )
        if not first_track_url:
            return ""

        try:
            with yt_dlp.YoutubeDL(
                {
                    "quiet": True,
                    "no_warnings": True,
                    "skip_download": True,
                }
            ) as ydl:
                track_info = ydl.extract_info(first_track_url, download=False)
        except Exception:
            return ""

        if not isinstance(track_info, Mapping):
            return ""

        return (
            self._extract_image_url(track_info.get("thumbnails"))
            or self._clean_text(track_info.get("thumbnail"), "")
        )

    def _resolve_youtube_artwork_url(self, album_url: str) -> str:
        try:
            with yt_dlp.YoutubeDL(
                {
                    "quiet": True,
                    "no_warnings": True,
                    "skip_download": True,
                    "extract_flat": True,
                }
            ) as ydl:
                info = ydl.extract_info(album_url, download=False)
        except Exception:
            return ""

        if not isinstance(info, Mapping):
            return ""
        return self._extract_image_url(info.get("thumbnails")) or self._clean_text(
            info.get("thumbnail"),
            "",
        )

    def _extract_soundcloud_album_urls(self, html: str) -> list[str]:
        json_urls = [
            match.replace("\\/", "/")
            for match in re.findall(
                (
                    r'"permalink_url":"'
                    r'(https:\\/\\/soundcloud\.com\\/[^"]+\\/sets\\/[^"]+)'
                    r'"'
                ),
                html,
            )
        ]
        json_urls.extend(
            re.findall(
                r'"permalink_url":"(https://soundcloud\.com/[^"]+/sets/[^"]+)"',
                html,
            )
        )
        if json_urls:
            return self._unique_values(json_urls)

        path_urls = [
            f"https://soundcloud.com{path}"
            for path in re.findall(r'href="(/[^/]+/sets/[^/"?#]+)"', html)
        ]
        return self._unique_values(path_urls)

    @staticmethod
    def _extract_item_count(value: object) -> int:
        if isinstance(value, list):
            return len(value)
        try:
            return max(0, int(float(value or 0)))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _unique_values(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    @staticmethod
    def _dedupe_results(
        results: list[DownloadSearchResult],
    ) -> list[DownloadSearchResult]:
        seen: set[tuple[str, str]] = set()
        unique_results: list[DownloadSearchResult] = []
        for item in results:
            key = (item.item_type, item.page_url.casefold())
            if key in seen:
                continue
            seen.add(key)
            unique_results.append(item)
        return unique_results

    def _remember(
        self,
        key: tuple[str, str, str, int],
        value: list[DownloadSearchResult],
    ) -> None:
        self._cache[key] = list(value)
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def _remember_soundcloud_links(
        self,
        key: str,
        value: list[DownloadSearchResult],
    ) -> None:
        self._soundcloud_link_cache[key] = list(value)
        self._soundcloud_link_cache.move_to_end(key)
        while len(self._soundcloud_link_cache) > self._cache_size:
            self._soundcloud_link_cache.popitem(last=False)
