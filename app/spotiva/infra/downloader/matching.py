from __future__ import annotations

import re
from difflib import SequenceMatcher

from spotiva.domain.entities.track import Track


class DownloadCandidateMatcher:
    _SPACE_RE = re.compile(r"\s+")
    _PAREN_RE = re.compile(r"\s*[\[(][^)\]]*[\])]\s*")
    _DERIVATIVE_RE = re.compile(
        "\\b(?:cover|\\u043a\\u0430\\u0432\\u0435\\u0440|remix|bootleg|"
        "edit|nightcore|sped up|slowed)\\b",
        re.IGNORECASE,
    )
    _SHORT_FORM_RE = re.compile(
        r"\b(?:snippet|preview|teaser|demo|sample|excerpt|clip)\b",
        re.IGNORECASE,
    )

    def build_query_variants(self, value: str) -> list[str]:
        normalized = value.strip()
        compacted = self._compact_match_text(value)
        return self._unique_values([normalized, compacted])

    def score(
        self,
        requested_track: Track,
        candidate_track: Track,
        source: str,
        preferred_source: str,
    ) -> float:
        requested_title = requested_track.name
        requested_artist = requested_track.primary_artist_name()
        candidate_title = candidate_track.name
        candidate_artist = candidate_track.primary_artist_name()

        title_score = max(
            self._text_similarity(
                self._normalize_match_text(requested_title),
                self._normalize_match_text(candidate_title),
            ),
            self._text_similarity(
                self._compact_match_text(requested_title),
                self._compact_match_text(candidate_title),
            ),
        )
        artist_score = self._text_similarity(
            self._compact_match_text(requested_artist),
            self._compact_match_text(candidate_artist),
        )

        exact_title_bonus = (
            0.14
            if self._compact_match_text(requested_title)
            and self._compact_match_text(requested_title)
            == self._compact_match_text(candidate_title)
            else 0.0
        )
        preferred_source_bonus = 0.03 if source == preferred_source else 0.0
        derivative_penalty = (
            0.18
            if self._is_derivative_text(candidate_title)
            and not self._is_derivative_text(requested_title)
            else 0.0
        )
        short_form_penalty = (
            0.24
            if self._is_short_form_text(candidate_title)
            and not self._is_short_form_text(requested_title)
            else 0.0
        )
        duration_bonus = 0.12 * self._duration_match_score(
            requested_track.duration_ms,
            candidate_track.duration_ms,
        )
        duration_penalty = (
            0.32
            if self.has_duration_mismatch(
                requested_track.duration_ms,
                candidate_track.duration_ms,
            )
            else 0.0
        )
        length_preference_bonus = self._length_preference_bonus(
            requested_duration_ms=requested_track.duration_ms,
            candidate_duration_ms=candidate_track.duration_ms,
            title_score=title_score,
            artist_score=artist_score,
        )
        ultra_short_penalty = self._ultra_short_candidate_penalty(
            requested_duration_ms=requested_track.duration_ms,
            candidate_duration_ms=candidate_track.duration_ms,
            title_score=title_score,
            artist_score=artist_score,
        )
        return max(
            0.0,
            min(
                1.25,
                (title_score * 0.68)
                + (artist_score * 0.32)
                + exact_title_bonus
                + preferred_source_bonus
                + duration_bonus
                + length_preference_bonus
                - derivative_penalty
                - short_form_penalty
                - duration_penalty
                - ultra_short_penalty
            ),
        )

    def is_reliable_match(
        self,
        requested_track: Track,
        candidate_track: Track,
        score: float,
    ) -> bool:
        title_score = max(
            self._text_similarity(
                self._normalize_match_text(requested_track.name),
                self._normalize_match_text(candidate_track.name),
            ),
            self._text_similarity(
                self._compact_match_text(requested_track.name),
                self._compact_match_text(candidate_track.name),
            ),
        )
        artist_score = self._text_similarity(
            self._compact_match_text(requested_track.primary_artist_name()),
            self._compact_match_text(candidate_track.primary_artist_name()),
        )
        candidate_artist = self._compact_match_text(
            candidate_track.primary_artist_name()
        )

        if title_score < 0.72:
            return False
        if score < 0.64:
            return False
        if self.has_duration_mismatch(
            requested_track.duration_ms,
            candidate_track.duration_ms,
        ):
            return False
        if (
            self._is_short_form_text(candidate_track.name)
            and not self._is_short_form_text(requested_track.name)
        ):
            return False
        if artist_score >= 0.52:
            return True
        if not candidate_artist and title_score >= 0.96:
            return True
        return False

    def has_duration_mismatch(
        self,
        requested_duration_ms: int,
        candidate_duration_ms: int,
    ) -> bool:
        if requested_duration_ms <= 0 or candidate_duration_ms <= 0:
            return False

        duration_delta = abs(requested_duration_ms - candidate_duration_ms)
        allowed_delta_ms = max(15_000, int(requested_duration_ms * 0.18))
        return duration_delta > allowed_delta_ms

    def _normalize_match_text(self, value: str) -> str:
        return self._SPACE_RE.sub(" ", value.casefold().strip())

    def _compact_match_text(self, value: str) -> str:
        lowered = self._normalize_match_text(value)
        without_parenthetical = self._PAREN_RE.sub(" ", lowered)
        without_derivative = self._DERIVATIVE_RE.sub(" ", without_parenthetical)
        return self._SPACE_RE.sub(" ", without_derivative).strip()

    def _is_derivative_text(self, value: str) -> bool:
        return bool(self._DERIVATIVE_RE.search(value or ""))

    def _is_short_form_text(self, value: str) -> bool:
        return bool(self._SHORT_FORM_RE.search(value or ""))

    @staticmethod
    def _text_similarity(left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        return SequenceMatcher(None, left, right).ratio()

    @staticmethod
    def _duration_match_score(
        requested_duration_ms: int,
        candidate_duration_ms: int,
    ) -> float:
        if requested_duration_ms <= 0 or candidate_duration_ms <= 0:
            return 0.0

        duration_delta = abs(requested_duration_ms - candidate_duration_ms)
        soft_tolerance_ms = max(8_000, int(requested_duration_ms * 0.08))
        hard_tolerance_ms = max(30_000, int(requested_duration_ms * 0.35))
        if duration_delta <= soft_tolerance_ms:
            return 1.0
        if duration_delta >= hard_tolerance_ms:
            return 0.0
        return 1.0 - (
            (duration_delta - soft_tolerance_ms)
            / max(1, hard_tolerance_ms - soft_tolerance_ms)
        )

    @staticmethod
    def _length_preference_bonus(
        requested_duration_ms: int,
        candidate_duration_ms: int,
        title_score: float,
        artist_score: float,
    ) -> float:
        if requested_duration_ms > 0:
            return 0.0
        if candidate_duration_ms <= 0:
            return 0.0
        if title_score < 0.94 or artist_score < 0.85:
            return 0.0

        capped_duration_ms = min(candidate_duration_ms, 240_000)
        return (capped_duration_ms / 240_000) * 0.10

    @staticmethod
    def _ultra_short_candidate_penalty(
        requested_duration_ms: int,
        candidate_duration_ms: int,
        title_score: float,
        artist_score: float,
    ) -> float:
        if requested_duration_ms > 0:
            return 0.0
        if candidate_duration_ms <= 0:
            return 0.0
        if title_score < 0.94 or artist_score < 0.85:
            return 0.0
        if candidate_duration_ms >= 45_000:
            return 0.0
        return 0.18

    @staticmethod
    def _unique_values(values: list[str]) -> list[str]:
        unique_values: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique_values.append(normalized)
        return unique_values
