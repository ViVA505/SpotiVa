from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import replace
from difflib import SequenceMatcher

from spotiva.core.constants import DEFAULT_TITLE_SEARCH_SOURCE
from spotiva.domain.entities.track import Track, TrackImage
from spotiva.domain.repos.catalog_repo import DownloadCatalogRepository
from spotiva.infra.downloader.track_mapper import DownloadTrackMapper
from spotiva.infra.downloader.yt_dlp_search_client import YtDlpSearchClient
from spotiva.infra.genius.lyrics_client import GeniusLyricsClient
from spotiva.infra.genius.models import GeniusSongMatch


class YtDlpCatalogRepository(DownloadCatalogRepository):
    _SPACE_RE = re.compile(r"\s+")
    _PAREN_RE = re.compile(r"\s*[\[(][^)\]]*[\])]\s*")
    _DERIVATIVE_RE = re.compile(
        r"\b(?:cover|кавер|remix|bootleg|edit|nightcore|sped up|slowed)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        search_client: YtDlpSearchClient,
        mapper: DownloadTrackMapper,
        lyrics_client: GeniusLyricsClient | None = None,
    ) -> None:
        self._search_client = search_client
        self._mapper = mapper
        self._lyrics_client = lyrics_client

    def search_tracks(
        self,
        query: str,
        limit: int,
        artist_name: str = "",
        source: str = DEFAULT_TITLE_SEARCH_SOURCE,
        lyric_search_enabled: bool = True,
    ) -> list[Track]:
        results = self._search_client.search(
            query=query,
            limit=limit,
            artist_name=artist_name,
            source=source,
        )
        tracks = self._dedupe_tracks(self._mapper.map_result(item) for item in results)
        ranked_tracks = sorted(
            tracks,
            key=lambda track: self._build_score(track, query, artist_name),
            reverse=True,
        )

        if lyric_search_enabled and self._should_try_lyric_search(
            query,
            artist_name,
            ranked_tracks,
        ):
            lyric_tracks = self._search_tracks_from_lyrics(query, limit, source)
            if lyric_tracks and self._should_prefer_lyric_tracks(
                query,
                ranked_tracks,
                lyric_tracks,
            ):
                return lyric_tracks[:limit]
            if lyric_tracks and not ranked_tracks:
                return lyric_tracks[:limit]

        return ranked_tracks[:limit]

    def _search_tracks_from_lyrics(
        self,
        query: str,
        limit: int,
        source: str,
    ) -> list[Track]:
        if not self._lyrics_client:
            return []

        try:
            lyric_matches = self._lyrics_client.search(
                query=query,
                limit=max(limit, 6),
            )
        except Exception:
            return []

        resolved_tracks: list[Track] = []
        for lyric_match in lyric_matches:
            resolved_track = self._resolve_lyric_match_track(lyric_match, source)
            if resolved_track is None:
                continue
            resolved_tracks.append(resolved_track)

        ranked_tracks = sorted(
            resolved_tracks,
            key=lambda track: (
                track.lyric_match_score,
                0 if self._is_derivative_title(track.name) else 1,
            ),
            reverse=True,
        )
        return self._dedupe_tracks(ranked_tracks)[:limit]

    def _resolve_lyric_match_track(
        self,
        lyric_match: GeniusSongMatch,
        source: str,
    ) -> Track | None:
        search_title = self._compact_text(lyric_match.title) or lyric_match.title
        search_artist = self._compact_text(lyric_match.artist) or lyric_match.artist
        search_results = self._search_client.search(
            query=search_title,
            limit=4,
            artist_name=search_artist,
            source=source,
        )
        mapped_tracks = self._dedupe_tracks(
            self._mapper.map_result(item)
            for item in search_results
        )
        if not mapped_tracks:
            return None

        single_tracks = [
            track
            for track in mapped_tracks
            if not track.is_album_result()
        ]
        candidate_tracks = single_tracks or mapped_tracks

        best_track = max(
            candidate_tracks,
            key=lambda track: self._build_score(track, search_title, search_artist),
        )
        best_track_score = self._build_score(
            best_track,
            search_title,
            search_artist,
        )
        if best_track_score < 0.45:
            return None

        if lyric_match.image_url and not best_track.best_image_url():
            best_track = replace(
                best_track,
                album=replace(
                    best_track.album,
                    images=[TrackImage(url=lyric_match.image_url)],
                ),
            )

        return replace(
            best_track,
            lyric_match_score=max(best_track.lyric_match_score, lyric_match.match_score),
            lyric_match_text=lyric_match.matched_text or best_track.lyric_match_text,
        )

    def _build_score(self, track: Track, query: str, artist_name: str) -> float:
        query_text = self._normalize_score_text(query)
        title_text = self._normalize_score_text(track.name)
        compact_query_text = self._compact_text(query)
        compact_title_text = self._compact_text(track.name)
        title_score = max(
            SequenceMatcher(None, query_text, title_text).ratio(),
            SequenceMatcher(None, compact_query_text, compact_title_text).ratio()
            if compact_query_text and compact_title_text
            else 0.0,
        )

        artist_score = 0.0
        if artist_name:
            normalized_artist_name = self._normalize_score_text(artist_name)
            normalized_track_artist = self._normalize_score_text(
                track.primary_artist_name()
            )
            compact_artist_name = self._compact_text(artist_name)
            compact_track_artist = self._compact_text(track.primary_artist_name())
            artist_score = SequenceMatcher(
                None,
                normalized_artist_name,
                normalized_track_artist,
            ).ratio()
            if compact_artist_name and compact_track_artist:
                artist_score = max(
                    artist_score,
                    SequenceMatcher(
                        None,
                        compact_artist_name,
                        compact_track_artist,
                    ).ratio(),
                )

        official_bonus = 0.04 if "official" in title_text else 0.0
        album_bonus = (
            0.05
            if track.is_album_result() and compact_title_text == compact_query_text
            else 0.0
        )
        exact_bonus = 0.18 if compact_title_text == compact_query_text else 0.0
        startswith_bonus = (
            0.06
            if compact_query_text and compact_title_text.startswith(compact_query_text)
            else 0.0
        )
        derivative_penalty = (
            0.22
            if self._is_derivative_title(track.name)
            and not self._is_derivative_title(query)
            else 0.0
        )
        score = (
            (title_score * 0.75)
            + (artist_score * 0.25)
            + official_bonus
            + album_bonus
            + exact_bonus
            + startswith_bonus
            - derivative_penalty
        )
        return max(0.0, min(score, 1.25))

    def _should_try_lyric_search(
        self,
        query: str,
        artist_name: str,
        direct_tracks: list[Track],
    ) -> bool:
        if not self._lyrics_client or artist_name.strip():
            return False

        normalized_query = query.strip()
        query_word_count = len(normalized_query.split())
        if query_word_count < 3 and len(normalized_query) < 16:
            return False

        if not direct_tracks:
            return True

        strongest_direct_score = max(
            self._build_score(track, normalized_query, artist_name)
            for track in direct_tracks[: min(3, len(direct_tracks))]
        )
        return strongest_direct_score < 0.96

    def _should_prefer_lyric_tracks(
        self,
        query: str,
        direct_tracks: list[Track],
        lyric_tracks: list[Track],
    ) -> bool:
        if not lyric_tracks:
            return False

        query_text = query.strip().casefold()
        query_word_count = len(query_text.split())
        top_lyric_track = lyric_tracks[0]
        lyric_title_similarity = SequenceMatcher(
            None,
            query_text,
            top_lyric_track.name.casefold(),
        ).ratio()

        if not direct_tracks:
            return top_lyric_track.lyric_match_score >= 0.32

        strongest_direct_title_similarity = max(
            SequenceMatcher(
                None,
                query_text,
                track.name.casefold(),
            ).ratio()
            for track in direct_tracks[: min(3, len(direct_tracks))]
        )

        strongest_direct_score = max(
            self._build_score(track, query, "")
            for track in direct_tracks[: min(3, len(direct_tracks))]
        )

        if (
            lyric_title_similarity >= 0.9
            and strongest_direct_title_similarity >= 0.94
            and strongest_direct_score >= 0.8
        ):
            return False

        if query_word_count >= 4 and lyric_title_similarity < 0.88:
            return top_lyric_track.lyric_match_score >= 0.48

        if strongest_direct_score < 0.82:
            return top_lyric_track.lyric_match_score >= 0.42

        return False

    @staticmethod
    def _dedupe_tracks(tracks: Iterable[Track]) -> list[Track]:
        seen: set[tuple[str, str]] = set()
        unique_tracks: list[Track] = []
        for track in tracks:
            if not isinstance(track, Track):
                continue
            key = (track.item_type, track.open_url().casefold())
            if key in seen:
                continue
            seen.add(key)
            unique_tracks.append(track)
        return unique_tracks

    def _normalize_score_text(self, value: str) -> str:
        return self._SPACE_RE.sub(" ", value.casefold().strip())

    def _compact_text(self, value: str) -> str:
        lowered = self._normalize_score_text(value)
        without_parenthetical = self._PAREN_RE.sub(" ", lowered)
        without_derivative = self._DERIVATIVE_RE.sub(" ", without_parenthetical)
        return self._SPACE_RE.sub(" ", without_derivative).strip()

    def _is_derivative_title(self, value: str) -> bool:
        return bool(self._DERIVATIVE_RE.search(value or ""))
