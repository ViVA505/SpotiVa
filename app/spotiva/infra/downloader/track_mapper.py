from __future__ import annotations

import re

from spotiva.core.title_sources import title_search_source_label
from spotiva.domain.entities.track import Album, Artist, Track, TrackImage
from spotiva.infra.downloader.models import DownloadSearchResult


class DownloadTrackMapper:
    _TITLE_SEPARATORS = (" - ", " – ", " — ")
    _FEATURE_SPLIT_RE = re.compile(r"(?:\bfeat(?:uring)?\.?|\bft\.?|\bwith\b)", re.IGNORECASE)
    _ARTIST_SPLIT_RE = re.compile(r"\s*(?:,|&| and | x | / )\s*", re.IGNORECASE)
    _NOISE_BLOCK_RE = re.compile(
        r"\s*[\[(](?:official\b[^)\]]*|lyrics\b[^)\]]*|audio\b[^)\]]*|video\b[^)\]]*|visualizer\b[^)\]]*)[\])]\s*",
        re.IGNORECASE,
    )
    _MULTISPACE_RE = re.compile(r"\s+")

    def map_result(self, item: DownloadSearchResult) -> Track:
        track_name, artist_names = self._parse_metadata(item.title, item.artist)
        images = [TrackImage(url=item.image_url)] if item.image_url else []
        track_id = f"{item.source}:{item.source_id or item.title}"
        return Track(
            track_id=track_id,
            name=track_name,
            artists=[Artist(name=name) for name in artist_names],
            album=Album(name=item.album or "Single", images=images),
            duration_ms=max(0, item.duration_ms),
            spotify_url="",
            external_url=item.page_url,
            download_url=item.page_url or None,
            source_label=title_search_source_label(item.source),
            is_downloadable=bool(item.page_url),
        )

    def _parse_metadata(self, title: str, fallback_artist: str) -> tuple[str, list[str]]:
        normalized_title = self._normalize_text(title) or "Unknown Title"
        normalized_artist = self._normalize_text(fallback_artist)
        title_artist, title_name = self._split_title(normalized_title)

        artist_names = self._extract_artist_names(title_artist or normalized_artist)
        cleaned_title, featured_names = self._extract_featured_artists(title_name)
        artist_names.extend(featured_names)

        if not artist_names:
            artist_names = self._extract_artist_names(normalized_artist)
        if not artist_names:
            artist_names = ["Unknown Artist"]

        cleaned_title = self._cleanup_title(cleaned_title)
        if not cleaned_title:
            cleaned_title = self._cleanup_title(normalized_title) or normalized_title

        return cleaned_title, self._dedupe_names(artist_names)

    def _split_title(self, title: str) -> tuple[str, str]:
        for separator in self._TITLE_SEPARATORS:
            if separator not in title:
                continue
            left, right = title.split(separator, 1)
            left = self._normalize_text(left)
            right = self._normalize_text(right)
            if left and right:
                return left, right
        return "", title

    def _extract_featured_artists(self, title: str) -> tuple[str, list[str]]:
        match = self._FEATURE_SPLIT_RE.search(title)
        if not match:
            return title, []

        clean_title = self._normalize_text(title[: match.start()])
        featured_block = self._normalize_text(title[match.end() :])
        featured_block = re.split(r"\s[-–—]\s|[\[(]", featured_block, maxsplit=1)[0]
        return clean_title, self._split_artist_names(featured_block)

    def _extract_artist_names(self, raw_value: str) -> list[str]:
        normalized = self._normalize_text(raw_value)
        if not normalized:
            return []

        parts = self._FEATURE_SPLIT_RE.split(normalized)
        artist_names: list[str] = []
        for part in parts:
            artist_names.extend(self._split_artist_names(part))
        return self._dedupe_names(artist_names)

    def _split_artist_names(self, raw_value: str) -> list[str]:
        normalized = self._normalize_text(raw_value)
        if not normalized:
            return []

        return [
            name
            for name in (self._cleanup_artist_name(part) for part in self._ARTIST_SPLIT_RE.split(normalized))
            if name
        ]

    def _cleanup_title(self, value: str) -> str:
        cleaned = self._normalize_text(value)
        cleaned = self._NOISE_BLOCK_RE.sub(" ", cleaned)
        return self._normalize_text(cleaned)

    def _cleanup_artist_name(self, value: str) -> str:
        cleaned = re.split(r"[\[(]", value, maxsplit=1)[0]
        return self._normalize_text(cleaned)

    def _dedupe_names(self, names: list[str]) -> list[str]:
        unique_names: list[str] = []
        seen: set[str] = set()
        for name in names:
            normalized = name.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            unique_names.append(name)
        return unique_names

    def _normalize_text(self, value: str) -> str:
        return self._MULTISPACE_RE.sub(" ", value.strip())
