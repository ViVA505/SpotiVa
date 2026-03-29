from __future__ import annotations

from spotiva.core.constants import DEFAULT_TITLE_SEARCH_SOURCE, TITLE_SEARCH_SOURCE_LABELS


def normalize_title_search_source(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in TITLE_SEARCH_SOURCE_LABELS:
        return normalized
    return DEFAULT_TITLE_SEARCH_SOURCE


def title_search_source_label(value: str) -> str:
    normalized = normalize_title_search_source(value)
    return TITLE_SEARCH_SOURCE_LABELS[normalized]


def title_search_source_options() -> list[tuple[str, str]]:
    return list(TITLE_SEARCH_SOURCE_LABELS.items())
