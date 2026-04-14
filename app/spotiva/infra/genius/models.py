from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeniusSongMatch:
    title: str
    artist: str
    genius_url: str
    image_url: str = ""
    match_score: float = 0.0
    matched_text: str = ""
    search_score: float = 0.0
