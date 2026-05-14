from __future__ import annotations

from dataclasses import dataclass

from spotiva.domain.repos.artwork_repo import ArtworkRepository
from spotiva.logic.cases.download_track import DownloadTrackAssetUseCase
from spotiva.logic.cases.resolve_spotify_download import ResolveSpotifyDownloadUseCase
from spotiva.logic.cases.search_downloads import SearchDownloadableTracksUseCase


@dataclass(frozen=True)
class ApplicationServices:
    search_downloads: SearchDownloadableTracksUseCase
    download_track: DownloadTrackAssetUseCase
    resolve_spotify_download: ResolveSpotifyDownloadUseCase
    artwork: ArtworkRepository
