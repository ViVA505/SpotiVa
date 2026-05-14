from __future__ import annotations

from collections.abc import Callable

from spotiva.core.constants import APP_NAME, SEARCH_MODE_CATALOG, SEARCH_MODE_LYRICS
from spotiva.core.state import AppState
from spotiva.core.title_sources import (
    title_search_source_label,
    title_search_source_options,
)
from spotiva.domain.entities.track import Track
from spotiva.domain.repos.artwork_repo import ArtworkRepository
from spotiva.logic.cases.download_track import DownloadTrackAssetUseCase
from spotiva.logic.cases.resolve_spotify_download import ResolveSpotifyDownloadUseCase
from spotiva.logic.cases.search_downloads import SearchDownloadableTracksUseCase


class MainWindowController:
    def __init__(
        self,
        state: AppState,
        search_downloads_use_case: SearchDownloadableTracksUseCase | None = None,
        download_track_use_case: DownloadTrackAssetUseCase | None = None,
        spotify_download_use_case: ResolveSpotifyDownloadUseCase | None = None,
        artwork_resolver: ArtworkRepository | None = None,
    ) -> None:
        self._state = state
        self._search_downloads_use_case = search_downloads_use_case
        self._download_track_use_case = download_track_use_case
        self._spotify_download_use_case = spotify_download_use_case
        self._artwork_resolver = artwork_resolver

    def is_ready(self) -> bool:
        return (
            self._search_downloads_use_case is not None
            and self._download_track_use_case is not None
        )

    def can_accept_input(self) -> bool:
        return self.is_ready()

    def title_search_source(self) -> str:
        return self._state.title_search_source

    def title_search_source_label(self) -> str:
        return title_search_source_label(self._state.title_search_source)

    def available_title_sources(self) -> list[tuple[str, str]]:
        return title_search_source_options()

    def set_title_search_source(self, value: str) -> None:
        self._state.set_title_search_source(value)

    def lyric_search_enabled(self) -> bool:
        return self._state.lyric_search_enabled

    def set_lyric_search_enabled(self, value: bool) -> None:
        self._state.set_lyric_search_enabled(value)

    def download_directory(self) -> str:
        return self._state.download_directory

    def set_download_directory(self, value: str) -> None:
        self._state.set_download_directory(value)

    def load_tracks(
        self,
        value: str,
        search_mode: str = SEARCH_MODE_CATALOG,
    ) -> list[Track]:
        normalized = value.strip()
        if not normalized:
            if search_mode == SEARCH_MODE_LYRICS:
                raise ValueError("Enter a lyric line.")
            raise ValueError(
                "Enter a track title, album title, or paste a Spotify link."
            )

        if search_mode == SEARCH_MODE_LYRICS:
            if (
                self._spotify_download_use_case
                and self._spotify_download_use_case.looks_like_spotify_link(normalized)
            ):
                raise ValueError("Enter a lyric line instead of a Spotify link.")
            if self._search_downloads_use_case:
                return self._search_downloads_use_case.execute(
                    query=normalized,
                    limit=self._state.search_limit,
                    source=self._state.title_search_source,
                    lyric_search_enabled=True,
                    lyric_search_only=True,
                )
            raise RuntimeError("Download search is not configured.")

        if (
            self._spotify_download_use_case
            and self._spotify_download_use_case.looks_like_spotify_link(normalized)
        ):
            return [self._resolve_spotify_download_item(normalized)]

        if self._search_downloads_use_case:
            return self._search_downloads_use_case.execute(
                query=normalized,
                limit=self._state.search_limit,
                source=self._state.title_search_source,
                lyric_search_enabled=False,
            )

        raise RuntimeError("Download search is not configured.")

    def download_track(
        self,
        track: Track,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> str:
        if not self._download_track_use_case:
            raise RuntimeError("Download service is not configured.")
        return self._download_track_use_case.execute(track, progress_callback)

    def resolve_track_artwork(self, track: Track) -> str:
        if track.best_image_url():
            return track.best_image_url()
        if not track.is_album_result() or not self._artwork_resolver:
            return ""
        return self._artwork_resolver.resolve_artwork_url(track.open_url())

    def request_timeout(self) -> int:
        return self._state.request_timeout

    def hero_title(self) -> str:
        return APP_NAME

    def hero_subtitle(self) -> str:
        return (
            "Paste a Spotify track or album link, type a track or album title, "
            "or switch to lyric line search to resolve snippets through Genius."
        )

    def onboarding_text(self) -> str:
        return (
            "Type a track title, album title, or paste a Spotify link to get started."
        )

    def result_summary(self, query: str, tracks: list[Track]) -> str:
        normalized = query.strip()
        total = len(tracks)
        if (
            self._spotify_download_use_case
            and self._spotify_download_use_case.looks_like_spotify_link(normalized)
        ):
            if tracks and tracks[0].is_album_result():
                return (
                    "Spotify album ready. Download will search YouTube for each "
                    "album track automatically."
                )
            return "Spotify track ready. Download will search YouTube automatically."
        if tracks and tracks[0].has_lyric_match():
            if total == 1:
                return (
                    f"1 lyric match for '{normalized}' via Genius, "
                    f"ready to download from {self.title_search_source_label()}."
                )
            return (
                f"{total} lyric matches for '{normalized}' via Genius, "
                f"ready to download from {self.title_search_source_label()}."
            )
        if total == 1:
            return f"1 result for '{normalized}'."
        return f"{total} results for '{normalized}'."

    def top_artist_summary(self, tracks: list[Track]) -> str:
        if not tracks:
            return "No artist selected"
        return tracks[0].primary_artist_name()

    def startup_status(self) -> str:
        if self.is_ready():
            return ""
        return "Download service is not configured."

    def _resolve_spotify_download_item(self, spotify_url: str) -> Track:
        if not self._spotify_download_use_case:
            raise RuntimeError("Spotify link resolving is not configured.")
        return self._spotify_download_use_case.execute(spotify_url)
