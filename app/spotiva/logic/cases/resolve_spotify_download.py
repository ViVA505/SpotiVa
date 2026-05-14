from __future__ import annotations

from dataclasses import replace

from spotiva.core.exceptions import SpotifyApiError
from spotiva.domain.entities.track import Track
from spotiva.domain.repos.preview_repo import SpotifyPreviewRepository
from spotiva.domain.services.link_parser import SpotifyLinkParser
from spotiva.logic.cases.resolve_input import ResolveTrackInputUseCase


class ResolveSpotifyDownloadUseCase:
    def __init__(
        self,
        link_parser: SpotifyLinkParser,
        resolve_input_use_case: ResolveTrackInputUseCase | None = None,
        preview_repository: SpotifyPreviewRepository | None = None,
    ) -> None:
        self._link_parser = link_parser
        self._resolve_input_use_case = resolve_input_use_case
        self._preview_repository = preview_repository

    def looks_like_spotify_link(self, value: str) -> bool:
        return self._link_parser.looks_like_spotify_link(value)

    def execute(self, spotify_url: str) -> Track:
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

        if resolved_track is None and self._preview_repository:
            if resource.resource_type == "album":
                resolved_track = self._preview_repository.resolve_album(
                    spotify_url,
                    resource.resource_id,
                )
            else:
                resolved_track = self._preview_repository.resolve_track(
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
