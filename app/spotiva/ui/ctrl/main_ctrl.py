from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from spotiva.core.state import AppState
from spotiva.logic.cases.download_track import DownloadTrackAssetUseCase
from spotiva.logic.cases.resolve_input import ResolveTrackInputUseCase
from spotiva.logic.cases.search_downloads import SearchDownloadableTracksUseCase
from spotiva.core.constants import APP_NAME
from spotiva.core.exceptions import SpotifyApiError
from spotiva.core.title_sources import (
    title_search_source_label,
    title_search_source_options,
)
from spotiva.domain.entities.track import Track
from spotiva.domain.services.link_parser import SpotifyLinkParser
from spotiva.infra.downloader.yt_dlp_search_client import YtDlpSearchClient
from spotiva.infra.spotify.preview_client import SpotifyPublicPreviewClient


class MainWindowController:
    def __init__(
        self,
        state: AppState,
        resolve_input_use_case: ResolveTrackInputUseCase | None,
        search_downloads_use_case: SearchDownloadableTracksUseCase | None = None,
        download_track_use_case: DownloadTrackAssetUseCase | None = None,
        link_parser: SpotifyLinkParser | None = None,
        preview_client: SpotifyPublicPreviewClient | None = None,
        artwork_resolver: YtDlpSearchClient | None = None,
    ) -> None:
        self._state = state
        self._resolve_input_use_case = resolve_input_use_case
        self._search_downloads_use_case = search_downloads_use_case
        self._download_track_use_case = download_track_use_case
        self._link_parser = link_parser
        self._preview_client = preview_client
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

    def load_tracks(self, value: str) -> list[Track]:
        normalized = value.strip()
        if not normalized:
            raise ValueError(
                "Enter a track title, album title, lyric line, or paste a Spotify link."
            )

        if self._link_parser and self._link_parser.looks_like_spotify_link(normalized):
            return [self._resolve_spotify_download_item(normalized)]

        if self._search_downloads_use_case:
            return self._search_downloads_use_case.execute(
                query=normalized,
                limit=self._state.search_limit,
                source=self._state.title_search_source,
                lyric_search_enabled=self._state.lyric_search_enabled,
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
            "or paste a lyric line. "
            "The app can resolve lyric snippets through Genius and then pull a clean "
            "downloadable match from YouTube or SoundCloud."
        )

    def onboarding_text(self) -> str:
        return (
            "Type a track title, album title, lyric line, or paste a Spotify link "
            "to get started."
        )

    def result_summary(self, query: str, tracks: list[Track]) -> str:
        normalized = query.strip()
        total = len(tracks)
        if self._link_parser and self._link_parser.looks_like_spotify_link(normalized):
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
        if not self._link_parser:
            raise RuntimeError("Spotify link parsing is not configured.")

        resource = self._link_parser.parse(spotify_url)
        resolved_track: Track | None = None
        api_error: SpotifyApiError | None = None

        if self._resolve_input_use_case:
            try:
                tracks = self._resolve_input_use_case.execute(spotify_url, limit=1)
            except SpotifyApiError as error:
                api_error = error
            else:
                if tracks:
                    resolved_track = tracks[0]

        if resolved_track is None and self._preview_client:
            if resource.resource_type == "album":
                resolved_track = self._preview_client.resolve_album(
                    spotify_url,
                    resource.resource_id,
                )
            else:
                resolved_track = self._preview_client.resolve_track(
                    spotify_url,
                    resource.resource_id,
                )

        if resolved_track is None:
            if api_error is not None:
                raise api_error
            raise RuntimeError("Spotify link metadata is not available.")

        return replace(
            resolved_track,
            external_url=(
                resolved_track.external_url
                or resolved_track.spotify_url
                or spotify_url
            ),
            source_label="Spotify Link",
            is_downloadable=True,
        )
