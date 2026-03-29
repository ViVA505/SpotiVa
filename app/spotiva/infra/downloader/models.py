from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadSearchResult:
    source: str
    source_id: str
    title: str
    artist: str
    page_url: str
    image_url: str = ""
    album: str = "Single"
    duration_ms: int = 0
