from __future__ import annotations

import re
from collections import Counter, OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from difflib import SequenceMatcher
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from spotiva.core.constants import DEFAULT_REQUEST_TIMEOUT
from spotiva.core.exceptions import CatalogApiError
from spotiva.infra.genius.models import GeniusSongMatch


class GeniusLyricsClient:
    _SEARCH_SECTION_TYPES = {"top_hit", "song", "lyric"}
    _NOISE_LINE_RE = re.compile(r"^(?:lyrics|contributors?|translations?)$", re.I)
    _PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
    _SPACE_RE = re.compile(r"\s+")

    def __init__(
        self,
        cache_size: int = 48,
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        self._cache_size = max(8, int(cache_size))
        self._request_timeout = max(5, int(request_timeout))
        self._session = curl_requests.Session()
        self._search_cache: OrderedDict[
            tuple[str, int],
            list[GeniusSongMatch],
        ] = OrderedDict()
        self._lyrics_cache: OrderedDict[str, list[str]] = OrderedDict()

    def search(self, query: str, limit: int = 8) -> list[GeniusSongMatch]:
        normalized_query = query.strip()
        normalized_limit = max(1, min(int(limit), 10))
        if not normalized_query:
            return []

        cache_key = (normalized_query.casefold(), normalized_limit)
        cached = self._search_cache.get(cache_key)
        if cached is not None:
            self._search_cache.move_to_end(cache_key)
            return list(cached)

        candidates = self._search_candidates(normalized_query, normalized_limit * 2)
        if not candidates:
            self._remember_search(cache_key, [])
            return []

        hydrated_candidates = self._score_candidates(normalized_query, candidates)
        minimum_score = self._minimum_score(normalized_query)
        filtered_candidates = [
            candidate
            for candidate in hydrated_candidates
            if candidate.match_score >= minimum_score
        ]

        ranked_candidates = filtered_candidates or [
            candidate
            for candidate in hydrated_candidates
            if candidate.match_score > 0.18
        ]
        ranked_candidates = sorted(
            ranked_candidates,
            key=lambda candidate: (candidate.match_score, candidate.search_score),
            reverse=True,
        )

        result = ranked_candidates[:normalized_limit]
        self._remember_search(cache_key, result)
        return list(result)

    def _search_candidates(self, query: str, limit: int) -> list[GeniusSongMatch]:
        search_url = f"https://genius.com/api/search/multi?q={quote_plus(query)}"
        try:
            response = self._session.get(
                search_url,
                timeout=self._request_timeout,
                impersonate="chrome",
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/133.0.0.0 Safari/537.36"
                    ),
                },
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            raise CatalogApiError(f"Could not search Genius: {error}") from error

        sections = payload.get("response", {}).get("sections", [])
        if not isinstance(sections, list):
            return []

        query_tokens = self._tokenize(query)
        unique_matches: list[GeniusSongMatch] = []
        seen_urls: set[str] = set()

        for section in sections:
            if not isinstance(section, dict):
                continue
            if str(section.get("type", "")).strip().lower() not in self._SEARCH_SECTION_TYPES:
                continue

            hits = section.get("hits")
            if not isinstance(hits, list):
                continue

            for hit in hits:
                if not isinstance(hit, dict):
                    continue

                result = hit.get("result")
                if not isinstance(result, dict) or result.get("_type") != "song":
                    continue

                genius_url = str(result.get("url", "")).strip()
                if not genius_url or genius_url.casefold() in seen_urls:
                    continue

                title = str(result.get("title", "")).strip()
                artist = str(
                    result.get("artist_names")
                    or result.get("primary_artist_names")
                    or ""
                ).strip()
                if not title or not artist:
                    continue

                search_score = self._build_search_score(hit, query_tokens)
                image_url = str(
                    result.get("song_art_image_thumbnail_url")
                    or result.get("song_art_image_url")
                    or ""
                ).strip()

                unique_matches.append(
                    GeniusSongMatch(
                        title=title,
                        artist=artist,
                        genius_url=genius_url,
                        image_url=image_url,
                        search_score=search_score,
                    )
                )
                seen_urls.add(genius_url.casefold())

                if len(unique_matches) >= max(6, limit):
                    return unique_matches

        return unique_matches

    def _score_candidates(
        self,
        query: str,
        candidates: list[GeniusSongMatch],
    ) -> list[GeniusSongMatch]:
        if not candidates:
            return []

        max_workers = min(4, len(candidates))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            resolved = executor.map(
                lambda candidate: self._score_candidate(query, candidate),
                candidates,
            )
            return [candidate for candidate in resolved if candidate is not None]

    def _score_candidate(
        self,
        query: str,
        candidate: GeniusSongMatch,
    ) -> GeniusSongMatch | None:
        lyric_lines = self._load_lyric_lines(candidate.genius_url)
        if not lyric_lines:
            return None

        match_score, matched_text = self._best_lyric_match(query, lyric_lines)
        if match_score <= 0:
            return None

        return replace(
            candidate,
            match_score=match_score,
            matched_text=matched_text,
        )

    def _load_lyric_lines(self, genius_url: str) -> list[str]:
        normalized_url = genius_url.strip()
        if not normalized_url:
            return []

        cached = self._lyrics_cache.get(normalized_url)
        if cached is not None:
            self._lyrics_cache.move_to_end(normalized_url)
            return list(cached)

        try:
            response = self._session.get(
                normalized_url,
                timeout=self._request_timeout,
                impersonate="chrome",
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/133.0.0.0 Safari/537.36"
                    )
                },
            )
            response.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        containers = soup.select('[data-lyrics-container="true"]')
        if not containers:
            return []

        lyric_lines: list[str] = []
        for container in containers:
            for excluded in container.select('[data-exclude-from-selection="true"]'):
                excluded.decompose()
            text = container.get_text("\n", strip=True)
            lyric_lines.extend(self._clean_lyric_lines(text.splitlines()))

        self._lyrics_cache[normalized_url] = list(lyric_lines)
        self._lyrics_cache.move_to_end(normalized_url)
        while len(self._lyrics_cache) > self._cache_size:
            self._lyrics_cache.popitem(last=False)
        return lyric_lines

    def _best_lyric_match(
        self,
        query: str,
        lyric_lines: list[str],
    ) -> tuple[float, str]:
        normalized_query = self._normalize_text(query)
        if not normalized_query:
            return (0.0, "")

        query_tokens = normalized_query.split()
        best_score = 0.0
        best_fragment = ""

        for fragment in self._candidate_fragments(lyric_lines, len(query_tokens)):
            normalized_fragment = self._normalize_text(fragment)
            if not normalized_fragment:
                continue

            sequence_score = SequenceMatcher(
                None,
                normalized_query,
                normalized_fragment,
            ).ratio()
            token_score = self._token_overlap_ratio(
                query_tokens,
                normalized_fragment.split(),
            )
            contains_bonus = 0.18 if normalized_query in normalized_fragment else 0.0
            prefix_bonus = 0.04 if normalized_fragment.startswith(normalized_query) else 0.0
            score = min(
                1.0,
                (sequence_score * 0.62) + (token_score * 0.34) + contains_bonus + prefix_bonus,
            )

            if score > best_score:
                best_score = score
                best_fragment = fragment.strip()

        return (best_score, best_fragment)

    def _candidate_fragments(
        self,
        lyric_lines: list[str],
        query_word_count: int,
    ) -> list[str]:
        cleaned_lines = [
            line.strip()
            for line in lyric_lines
            if line.strip() and not (line.startswith("[") and line.endswith("]"))
        ]
        if not cleaned_lines:
            return []

        fragments: list[str] = []
        seen: set[str] = set()

        def remember(value: str) -> None:
            normalized = value.strip()
            if not normalized:
                return
            key = normalized.casefold()
            if key in seen:
                return
            seen.add(key)
            fragments.append(normalized)

        for line in cleaned_lines:
            remember(line)

        merge_limit = 3 if query_word_count >= 6 else 2
        for size in range(2, merge_limit + 1):
            for index in range(len(cleaned_lines) - size + 1):
                remember(" ".join(cleaned_lines[index : index + size]))

        min_window = max(3, query_word_count - 2)
        max_window = max(min_window, query_word_count + 2)
        for line in cleaned_lines:
            normalized_line = self._normalize_text(line)
            tokens = normalized_line.split()
            if len(tokens) <= max_window:
                continue
            for window_size in range(min_window, min(max_window, len(tokens)) + 1):
                for index in range(len(tokens) - window_size + 1):
                    remember(" ".join(tokens[index : index + window_size]))

        return fragments

    def _clean_lyric_lines(self, lines: list[str]) -> list[str]:
        cleaned_lines: list[str] = []
        for raw_line in lines:
            normalized = self._SPACE_RE.sub(" ", raw_line.strip())
            if not normalized:
                continue
            if self._NOISE_LINE_RE.match(normalized):
                continue

            stripped = normalized.strip("() ").strip()
            if not stripped:
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                cleaned_lines.append(stripped)
                continue

            cleaned_lines.append(stripped)
        return cleaned_lines

    def _build_search_score(self, hit: dict, query_tokens: list[str]) -> float:
        if not query_tokens:
            return 0.0

        matched_words = self._safe_int(hit.get("matched_words"))
        exact_words = self._safe_int(hit.get("nb_exact_words"))
        total_words = max(1, len(query_tokens))
        return min(1.0, ((matched_words * 0.65) + (exact_words * 0.35)) / total_words)

    def _minimum_score(self, query: str) -> float:
        word_count = len(self._tokenize(query))
        if word_count >= 9:
            return 0.34
        if word_count >= 6:
            return 0.39
        if word_count >= 4:
            return 0.45
        return 0.52

    def _normalize_text(self, value: str) -> str:
        cleaned = self._PUNCT_RE.sub(" ", value.casefold())
        return self._SPACE_RE.sub(" ", cleaned).strip()

    def _tokenize(self, value: str) -> list[str]:
        return self._normalize_text(value).split()

    @staticmethod
    def _token_overlap_ratio(
        query_tokens: list[str],
        fragment_tokens: list[str],
    ) -> float:
        if not query_tokens or not fragment_tokens:
            return 0.0
        overlap = Counter(query_tokens) & Counter(fragment_tokens)
        matched_count = sum(overlap.values())
        return matched_count / max(1, len(query_tokens))

    @staticmethod
    def _safe_int(value: object) -> int:
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0

    def _remember_search(
        self,
        key: tuple[str, int],
        value: list[GeniusSongMatch],
    ) -> None:
        self._search_cache[key] = list(value)
        self._search_cache.move_to_end(key)
        while len(self._search_cache) > self._cache_size:
            self._search_cache.popitem(last=False)
