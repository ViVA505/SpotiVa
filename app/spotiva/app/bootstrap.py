from __future__ import annotations

from spotiva.app.services import ApplicationServices
from spotiva.core.state import AppState
from spotiva.domain.services.link_parser import SpotifyLinkParser
from spotiva.infra.downloader.audio_tagger import Mp3AudioTagger
from spotiva.infra.downloader.asset_repository import YtDlpAssetRepository
from spotiva.infra.downloader.catalog_repository import YtDlpCatalogRepository
from spotiva.infra.downloader.track_mapper import DownloadTrackMapper
from spotiva.infra.downloader.yt_dlp_search_client import YtDlpSearchClient
from spotiva.infra.genius.lyrics_client import GeniusLyricsClient
from spotiva.infra.spotify.preview_client import SpotifyPublicPreviewClient
from spotiva.logic.cases.download_track import DownloadTrackAssetUseCase
from spotiva.logic.cases.resolve_spotify_download import ResolveSpotifyDownloadUseCase
from spotiva.logic.cases.search_downloads import SearchDownloadableTracksUseCase
from spotiva.ui.ctrl.main_ctrl import MainWindowController


def build_services(state: AppState) -> ApplicationServices:
    link_parser = SpotifyLinkParser()
    preview_client = SpotifyPublicPreviewClient(request_timeout=state.request_timeout)
    download_search_client = YtDlpSearchClient(request_timeout=state.request_timeout)
    genius_client = GeniusLyricsClient(request_timeout=state.request_timeout)
    download_catalog = YtDlpCatalogRepository(
        download_search_client,
        DownloadTrackMapper(),
        genius_client,
    )
    audio_tagger = Mp3AudioTagger(request_timeout=state.request_timeout)
    download_assets = YtDlpAssetRepository(state, audio_tagger)

    return ApplicationServices(
        search_downloads=SearchDownloadableTracksUseCase(download_catalog),
        download_track=DownloadTrackAssetUseCase(download_assets),
        resolve_spotify_download=ResolveSpotifyDownloadUseCase(
            link_parser=link_parser,
            preview_repository=preview_client,
        ),
        artwork=download_search_client,
    )


def build_controller(state: AppState | None = None) -> MainWindowController:
    app_state = state or AppState()
    services = build_services(app_state)
    return MainWindowController(
        state=app_state,
        search_downloads_use_case=services.search_downloads,
        download_track_use_case=services.download_track,
        spotify_download_use_case=services.resolve_spotify_download,
        artwork_resolver=services.artwork,
    )
