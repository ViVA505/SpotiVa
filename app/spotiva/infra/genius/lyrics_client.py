from __future__ import annotations

import re
from collections import Counter, OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from difflib import SequenceMatcher
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from spotiva.core.constants import DEFAULT_REQUEST_TIMEOUT
from spotiva.core.exceptions import CatalogApiError
from spotiva.infra.genius.models import GeniusSongMatch


class GeniusLyricsClient:
    _BASE_HEADERS = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/133.0.0.0 Safari/537.36"
        ),
    }
    _SEARCH_SECTION_TYPES = {"top_hit", "song", "lyric"}
    _NOISE_LINE_RE = re.compile(r"^(?:lyrics|contributors?|translations?)$", re.I)
    _GENIUS_LYRICS_URL_RE = re.compile(
        r"https?://(?:www\.)?genius\.com/[^\s\"'<>]+-lyrics",
        re.I,
    )
    _PAREN_CONTENT_RE = re.compile(r"[\[(][^)\]]{1,48}[\])]")
    _PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
    _SPACE_RE = re.compile(r"\s+")
    _STOP_WORDS = frozenset(
        {
            "а",
            "без",
            "бы",
            "был",
            "была",
            "были",
            "быть",
            "в",
            "во",
            "вот",
            "всегда",
            "все",
            "для",
            "до",
            "его",
            "ее",
            "если",
            "есть",
            "еще",
            "же",
            "за",
            "и",
            "из",
            "или",
            "к",
            "как",
            "ко",
            "ли",
            "меня",
            "мне",
            "мой",
            "моя",
            "мы",
            "на",
            "не",
            "ни",
            "но",
            "ну",
            "о",
            "об",
            "он",
            "она",
            "они",
            "от",
            "по",
            "под",
            "при",
            "с",
            "со",
            "та",
            "так",
            "там",
            "те",
            "тебя",
            "тем",
            "то",
            "ты",
            "у",
            "что",
            "это",
            "я",
        }
    )

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

        quick_matches = self._search_quick_web_matches(
            normalized_query,
            normalized_limit,
        )
        if quick_matches:
            self._remember_search(cache_key, quick_matches)
            return list(quick_matches)

        candidates = self._search_candidates(normalized_query, normalized_limit)
        if not candidates:
            candidates = self._search_web_genius_candidates(
                normalized_query,
                min(3, normalized_limit),
            )
            if not candidates:
                self._remember_search(cache_key, [])
                return []

        hydrated_candidates = self._score_candidates(normalized_query, candidates)
        if self._should_try_web_fallback(normalized_query, hydrated_candidates):
            web_candidates = self._search_web_genius_candidates(
                normalized_query,
                min(3, normalized_limit),
            )
            new_candidates = self._unique_new_candidates(
                hydrated_candidates,
                web_candidates,
            )
            if new_candidates:
                hydrated_candidates.extend(
                    self._score_candidates(normalized_query, new_candidates)
                )

        ranked_candidates = self._rank_candidates(
            normalized_query,
            hydrated_candidates,
        )

        result = ranked_candidates[:normalized_limit]
        self._remember_search(cache_key, result)
        return list(result)

    def _search_candidates(self, query: str, limit: int) -> list[GeniusSongMatch]:
        return self._search_candidates_for_queries(
            self._build_search_queries(query),
            limit,
        )

    def _search_candidates_for_queries(
        self,
        queries: list[str],
        limit: int,
    ) -> list[GeniusSongMatch]:
        candidates: OrderedDict[str, GeniusSongMatch] = OrderedDict()
        errors: list[CatalogApiError] = []
        search_jobs = [
            (searcher, query)
            for query in queries
            for searcher in (
                self._search_multi_candidates,
                self._search_basic_candidates,
            )
        ]

        max_workers = min(6, len(search_jobs))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(searcher, query, limit)
                for searcher, query in search_jobs
            ]
            for future in as_completed(futures):
                try:
                    found_candidates = future.result()
                except CatalogApiError as error:
                    errors.append(error)
                    continue

                for candidate in found_candidates:
                    self._remember_candidate(candidates, candidate)

        if not candidates and errors:
            raise errors[0]

        return list(candidates.values())[: max(8, limit * 2)]

    def _search_multi_candidates(
        self,
        query: str,
        limit: int,
    ) -> list[GeniusSongMatch]:
        search_url = f"https://genius.com/api/search/multi?q={quote_plus(query)}"
        payload = self._request_json(search_url)

        sections = payload.get("response", {}).get("sections", [])
        if not isinstance(sections, list):
            return []

        query_tokens = self._tokenize(query)
        unique_matches: OrderedDict[str, GeniusSongMatch] = OrderedDict()

        for section in sections:
            if not isinstance(section, dict):
                continue
            section_type = str(section.get("type", "")).strip().lower()
            if section_type not in self._SEARCH_SECTION_TYPES:
                continue

            hits = section.get("hits")
            if not isinstance(hits, list):
                continue

            for hit in hits:
                candidate = self._build_candidate_from_hit(hit, query_tokens)
                if candidate is None:
                    continue

                self._remember_candidate(unique_matches, candidate)
                if len(unique_matches) >= max(6, limit):
                    return list(unique_matches.values())

        return list(unique_matches.values())

    def _search_basic_candidates(
        self,
        query: str,
        limit: int,
    ) -> list[GeniusSongMatch]:
        search_url = f"https://genius.com/api/search?q={quote_plus(query)}"
        payload = self._request_json(search_url)

        hits = payload.get("response", {}).get("hits", [])
        if not isinstance(hits, list):
            return []

        query_tokens = self._tokenize(query)
        unique_matches: OrderedDict[str, GeniusSongMatch] = OrderedDict()
        for hit in hits:
            candidate = self._build_candidate_from_hit(hit, query_tokens)
            if candidate is None:
                continue

            self._remember_candidate(unique_matches, candidate)
            if len(unique_matches) >= max(6, limit):
                break

        return list(unique_matches.values())

    def _request_json(self, url: str) -> dict:
        try:
            response = self._session.get(
                url,
                timeout=self._request_timeout,
                impersonate="chrome",
                headers=self._BASE_HEADERS,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            raise CatalogApiError(f"Could not search Genius: {error}") from error

        if not isinstance(payload, dict):
            return {}
        return payload

    def _build_candidate_from_hit(
        self,
        hit: object,
        query_tokens: list[str],
    ) -> GeniusSongMatch | None:
        if not isinstance(hit, dict):
            return None

        result = hit.get("result")
        if not isinstance(result, dict) or result.get("_type") != "song":
            return None

        genius_url = str(result.get("url", "")).strip()
        if not genius_url:
            return None

        title = str(result.get("title", "")).strip()
        artist = str(
            result.get("artist_names")
            or result.get("primary_artist_names")
            or ""
        ).strip()
        if not title or not artist:
            return None

        image_url = str(
            result.get("song_art_image_thumbnail_url")
            or result.get("song_art_image_url")
            or ""
        ).strip()
        return GeniusSongMatch(
            title=title,
            artist=artist,
            genius_url=genius_url,
            image_url=image_url,
            search_score=self._build_search_score(hit, query_tokens),
        )

    def _search_web_genius_candidates(
        self,
        query: str,
        limit: int,
    ) -> list[GeniusSongMatch]:
        urls = self._search_web_genius_urls(
            self._build_web_search_queries(query),
            limit,
        )
        return self._candidates_from_genius_urls(urls)

    def _search_quick_web_matches(
        self,
        query: str,
        limit: int,
    ) -> list[GeniusSongMatch]:
        if len(self._tokenize(query)) < 5:
            return []

        web_queries = self._build_web_search_queries(query)
        if not web_queries:
            return []

        urls = self._search_web_genius_urls(web_queries[:1], min(3, limit))
        candidates = self._candidates_from_genius_urls(urls)
        scored_candidates = self._score_candidates(query, candidates)
        ranked_candidates = self._rank_candidates(query, scored_candidates)
        if ranked_candidates and ranked_candidates[0].match_score >= 0.98:
            return ranked_candidates[:limit]
        return []

    def _search_web_genius_urls(
        self,
        queries: list[str],
        limit: int,
    ) -> list[str]:
        urls: list[str] = []
        seen_urls: set[str] = set()

        for search_query in queries:
            search_url = f"https://yandex.ru/search/?text={quote_plus(search_query)}"
            try:
                response = self._session.get(
                    search_url,
                    timeout=self._request_timeout,
                    impersonate="chrome",
                    headers={
                        **self._BASE_HEADERS,
                        "Accept": (
                            "text/html,application/xhtml+xml,application/xml;"
                            "q=0.9,*/*;q=0.8"
                        ),
                    },
                )
                response.raise_for_status()
            except Exception:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for link in soup.select(".serp-item a[href], a[href]"):
                genius_url = self._extract_genius_lyrics_url(str(link.get("href", "")))
                if not genius_url:
                    continue
                key = genius_url.casefold()
                if key in seen_urls:
                    continue

                seen_urls.add(key)
                urls.append(genius_url)
                if len(urls) >= limit:
                    return urls

        return urls

    def _candidates_from_genius_urls(
        self,
        urls: list[str],
    ) -> list[GeniusSongMatch]:
        if not urls:
            return []

        candidates: OrderedDict[str, GeniusSongMatch] = OrderedDict()
        max_workers = min(4, len(urls))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self._candidate_from_genius_page, url)
                for url in urls
            ]
            for future in as_completed(futures):
                candidate = future.result()
                if candidate is None:
                    continue
                self._remember_candidate(candidates, candidate)

        return list(candidates.values())

    def _candidate_from_genius_page(self, genius_url: str) -> GeniusSongMatch | None:
        normalized_url = self._normalize_genius_url(genius_url)
        if not normalized_url:
            return None

        try:
            response = self._session.get(
                normalized_url,
                timeout=self._request_timeout,
                impersonate="chrome",
                headers=self._BASE_HEADERS,
            )
            response.raise_for_status()
        except Exception:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        title_value = self._meta_content(soup, "og:title") or self._meta_content(
            soup,
            "twitter:title",
        )
        if not title_value and soup.title:
            title_value = soup.title.get_text(" ", strip=True)

        title_value = self._clean_page_title(title_value)
        artist, separator, title = title_value.partition(" – ")
        if not separator:
            title, artist = title_value, ""

        title = title.strip()
        artist = artist.strip()
        if not title or not artist:
            return None

        lyric_lines = self._parse_lyric_lines(response.text)
        if lyric_lines:
            self._remember_lyrics(normalized_url, lyric_lines)

        return GeniusSongMatch(
            title=title,
            artist=artist,
            genius_url=normalized_url,
            image_url=self._meta_content(soup, "og:image")
            or self._meta_content(soup, "twitter:image")
            or "",
            search_score=1.0,
        )

    def _score_candidates(
        self,
        query: str,
        candidates: list[GeniusSongMatch],
    ) -> list[GeniusSongMatch]:
        if not candidates:
            return []

        max_workers = min(8, len(candidates))
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
                headers=self._BASE_HEADERS,
            )
            response.raise_for_status()
        except Exception:
            return []

        lyric_lines = self._parse_lyric_lines(response.text)
        if not lyric_lines:
            return []

        self._remember_lyrics(normalized_url, lyric_lines)
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
        meaningful_query_tokens = self._meaningful_tokens(query_tokens)
        best_score = 0.0
        best_fragment = ""

        for fragment in self._candidate_fragments(lyric_lines, len(query_tokens)):
            normalized_fragment = self._normalize_text(fragment)
            if not normalized_fragment:
                continue

            fragment_tokens = normalized_fragment.split()
            sequence_score = SequenceMatcher(
                None,
                normalized_query,
                normalized_fragment,
            ).ratio()
            token_score = self._token_overlap_ratio(
                query_tokens,
                fragment_tokens,
            )
            meaningful_score = self._token_overlap_ratio(
                meaningful_query_tokens,
                self._meaningful_tokens(fragment_tokens),
            )
            bigram_score = self._ngram_overlap_ratio(
                query_tokens,
                fragment_tokens,
                2,
            )
            trigram_score = self._ngram_overlap_ratio(
                query_tokens,
                fragment_tokens,
                3,
            )
            contains_bonus = 0.18 if normalized_query in normalized_fragment else 0.0
            prefix_bonus = (
                0.04 if normalized_fragment.startswith(normalized_query) else 0.0
            )
            score = min(
                1.0,
                (sequence_score * 0.42)
                + (token_score * 0.22)
                + (meaningful_score * 0.22)
                + (bigram_score * 0.09)
                + (trigram_score * 0.05)
                + contains_bonus
                + prefix_bonus,
            )
            if normalized_query == normalized_fragment:
                score = 1.0
            elif normalized_query in normalized_fragment:
                score = max(score, 0.94)

            if meaningful_query_tokens and meaningful_score == 0:
                score = min(score, 0.24)
            elif len(meaningful_query_tokens) >= 3 and meaningful_score < 0.5:
                score = min(score, 0.42)

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
            return 0.5
        if word_count >= 6:
            return 0.58
        if word_count >= 4:
            return 0.5
        return 0.52

    def _normalize_text(self, value: str) -> str:
        without_adlibs = self._PAREN_CONTENT_RE.sub(" ", value.casefold())
        cleaned = self._PUNCT_RE.sub(" ", without_adlibs.replace("ё", "е"))
        tokens = self._SPACE_RE.sub(" ", cleaned).strip().split()
        return " ".join(self._dedupe_adjacent_tokens(tokens))

    def _tokenize(self, value: str) -> list[str]:
        return self._normalize_text(value).split()

    def _rank_candidates(
        self,
        query: str,
        candidates: list[GeniusSongMatch],
    ) -> list[GeniusSongMatch]:
        minimum_score = self._minimum_score(query)
        strict_candidates = [
            candidate
            for candidate in candidates
            if candidate.match_score >= minimum_score
            and self._has_required_lyric_signal(query, candidate.matched_text)
        ]

        ranked_candidates = strict_candidates or [
            candidate
            for candidate in candidates
            if candidate.match_score >= max(0.42, minimum_score - 0.08)
            and self._has_required_lyric_signal(query, candidate.matched_text)
        ]
        ranked_candidates = sorted(
            ranked_candidates,
            key=lambda candidate: (candidate.match_score, candidate.search_score),
            reverse=True,
        )
        if ranked_candidates and ranked_candidates[0].match_score >= 0.98:
            return [
                candidate
                for candidate in ranked_candidates
                if candidate.match_score >= 0.75
            ]
        return ranked_candidates

    def _should_try_web_fallback(
        self,
        query: str,
        candidates: list[GeniusSongMatch],
    ) -> bool:
        if len(self._tokenize(query)) < 4:
            return False
        if not candidates:
            return True

        best_score = max(candidate.match_score for candidate in candidates)
        return best_score < 0.985

    def _has_required_lyric_signal(self, query: str, fragment: str) -> bool:
        query_tokens = self._meaningful_tokens(self._tokenize(query))
        if not query_tokens:
            return True

        fragment_tokens = set(self._meaningful_tokens(self._tokenize(fragment)))
        if not fragment_tokens:
            return False

        overlap = sum(1 for token in set(query_tokens) if token in fragment_tokens)
        unique_query_count = len(set(query_tokens))
        if unique_query_count >= 2:
            return overlap >= 2
        return overlap >= 1

    def _build_search_queries(self, query: str) -> list[str]:
        raw_query = query.strip()
        normalized_query = self._normalize_text(raw_query)
        meaningful_query = " ".join(self._meaningful_tokens(normalized_query.split()))

        queries: list[str] = []
        self._append_unique(queries, raw_query)
        self._append_unique(queries, normalized_query)
        self._append_unique(queries, meaningful_query)

        tokens = normalized_query.split()
        if len(tokens) < 6:
            return queries

        for window_size in range(min(7, len(tokens)), 3, -1):
            for index in range(0, len(tokens) - window_size + 1):
                self._append_unique(
                    queries,
                    " ".join(tokens[index : index + window_size]),
                )
                if len(queries) >= 7:
                    return queries

        return queries

    def _build_web_search_queries(self, query: str) -> list[str]:
        raw_query = query.strip()
        normalized_query = self._normalize_text(raw_query)
        meaningful_query = " ".join(self._meaningful_tokens(normalized_query.split()))

        queries: list[str] = []
        if raw_query:
            self._append_unique(queries, f'"{raw_query}" site:genius.com')
            self._append_unique(queries, f'"{raw_query}"')
        if normalized_query and normalized_query != raw_query.casefold():
            self._append_unique(queries, f'"{normalized_query}" site:genius.com')
        if meaningful_query:
            self._append_unique(queries, f"{meaningful_query} site:genius.com")
        return queries[:4]

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

    def _meaningful_tokens(self, tokens: list[str]) -> list[str]:
        return [
            token
            for token in tokens
            if len(token) >= 3 and token not in self._STOP_WORDS
        ]

    @staticmethod
    def _ngram_overlap_ratio(
        query_tokens: list[str],
        fragment_tokens: list[str],
        size: int,
    ) -> float:
        if len(query_tokens) < size or len(fragment_tokens) < size:
            return 0.0

        query_ngrams = Counter(
            tuple(query_tokens[index : index + size])
            for index in range(len(query_tokens) - size + 1)
        )
        fragment_ngrams = Counter(
            tuple(fragment_tokens[index : index + size])
            for index in range(len(fragment_tokens) - size + 1)
        )
        overlap = query_ngrams & fragment_ngrams
        matched_count = sum(overlap.values())
        return matched_count / max(1, sum(query_ngrams.values()))

    @staticmethod
    def _dedupe_adjacent_tokens(tokens: list[str]) -> list[str]:
        deduped_tokens: list[str] = []
        for token in tokens:
            if deduped_tokens and deduped_tokens[-1] == token:
                continue
            deduped_tokens.append(token)
        return deduped_tokens

    @staticmethod
    def _append_unique(values: list[str], value: str) -> None:
        normalized = value.strip()
        if not normalized:
            return
        if normalized.casefold() in {item.casefold() for item in values}:
            return
        values.append(normalized)

    def _parse_lyric_lines(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        containers = soup.select('[data-lyrics-container="true"]')
        if not containers:
            return []

        lyric_lines: list[str] = []
        for container in containers:
            for excluded in container.select('[data-exclude-from-selection="true"]'):
                excluded.decompose()
            text = container.get_text("\n", strip=True)
            lyric_lines.extend(self._clean_lyric_lines(text.splitlines()))

        return lyric_lines

    def _remember_lyrics(self, normalized_url: str, lyric_lines: list[str]) -> None:
        self._lyrics_cache[normalized_url] = list(lyric_lines)
        self._lyrics_cache.move_to_end(normalized_url)
        while len(self._lyrics_cache) > self._cache_size:
            self._lyrics_cache.popitem(last=False)

    def _remember_candidate(
        self,
        candidates: OrderedDict[str, GeniusSongMatch],
        candidate: GeniusSongMatch,
    ) -> None:
        key = self._normalize_genius_url(candidate.genius_url).casefold()
        current = candidates.get(key)
        if current is not None and current.search_score >= candidate.search_score:
            return
        candidates[key] = candidate

    def _unique_new_candidates(
        self,
        existing: list[GeniusSongMatch],
        candidates: list[GeniusSongMatch],
    ) -> list[GeniusSongMatch]:
        seen_urls = {
            self._normalize_genius_url(candidate.genius_url).casefold()
            for candidate in existing
        }
        new_candidates: list[GeniusSongMatch] = []
        for candidate in candidates:
            normalized_url = self._normalize_genius_url(candidate.genius_url).casefold()
            if not normalized_url or normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)
            new_candidates.append(candidate)
        return new_candidates

    def _extract_genius_lyrics_url(self, value: str) -> str:
        candidates = [value]
        parsed_url = urlparse(value)
        query_values = parse_qs(parsed_url.query)
        for key in ("url", "u", "target"):
            candidates.extend(query_values.get(key, []))

        for candidate in candidates:
            unquoted = unquote(candidate)
            match = self._GENIUS_LYRICS_URL_RE.search(unquoted)
            if match:
                return self._normalize_genius_url(match.group(0))

        return ""

    @staticmethod
    def _normalize_genius_url(value: str) -> str:
        normalized = value.strip().split("#", maxsplit=1)[0]
        normalized = normalized.split("?", maxsplit=1)[0]
        return normalized.rstrip("/.,)")

    @staticmethod
    def _meta_content(soup: BeautifulSoup, name: str) -> str:
        node = soup.select_one(f'meta[property="{name}"]') or soup.select_one(
            f'meta[name="{name}"]',
        )
        if node is None:
            return ""
        return str(node.get("content", "")).strip()

    @staticmethod
    def _clean_page_title(value: str) -> str:
        cleaned = value.strip()
        cleaned = re.sub(
            r"\s+Lyrics\s*\|\s*Genius\s+Lyrics\s*$",
            "",
            cleaned,
            flags=re.I,
        )
        cleaned = re.sub(r"\s*\|\s*Genius\s+Lyrics\s*$", "", cleaned, flags=re.I)
        return cleaned.strip()

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
