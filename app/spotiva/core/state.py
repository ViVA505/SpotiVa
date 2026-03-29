from __future__ import annotations

from pathlib import Path

from spotiva.core.constants import (
    DEFAULT_DOWNLOAD_DIR_NAME,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_TITLE_SEARCH_SOURCE,
)
from spotiva.core.title_sources import normalize_title_search_source


class AppState:
    def __init__(
        self,
        download_directory: str = "",
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
        search_limit: int = DEFAULT_SEARCH_LIMIT,
        title_search_source: str = DEFAULT_TITLE_SEARCH_SOURCE,
    ) -> None:
        self.request_timeout = max(5, int(request_timeout))
        self.search_limit = max(1, min(int(search_limit), 20))
        self.title_search_source = normalize_title_search_source(title_search_source)
        self.download_directory = ""
        self.set_download_directory(download_directory)

    def set_download_directory(self, value: str) -> None:
        self.download_directory = self._resolve_download_directory(value)

    def set_title_search_source(self, value: str) -> None:
        self.title_search_source = normalize_title_search_source(value)

    @staticmethod
    def _resolve_download_directory(value: str) -> str:
        normalized = value.strip()
        if normalized:
            return str(Path(normalized).expanduser())
        return str(Path.home() / "Downloads" / DEFAULT_DOWNLOAD_DIR_NAME)
