from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from spotiva.core.state import AppState
from spotiva.logic.cases.download_track import DownloadTrackAssetUseCase
from spotiva.logic.cases.search_downloads import SearchDownloadableTracksUseCase
from spotiva.domain.services.link_parser import SpotifyLinkParser
from spotiva.infra.downloader.audio_tagger import Mp3AudioTagger
from spotiva.infra.downloader.asset_repository import YtDlpAssetRepository
from spotiva.infra.downloader.catalog_repository import YtDlpCatalogRepository
from spotiva.infra.downloader.track_mapper import DownloadTrackMapper
from spotiva.infra.downloader.yt_dlp_search_client import YtDlpSearchClient
from spotiva.infra.spotify.preview_client import SpotifyPublicPreviewClient
from spotiva.ui.ctrl.main_ctrl import MainWindowController
from spotiva.ui.qt.main_window import MainWindow
from spotiva.ui.qt.theme import configure_app


def build_controller(state: AppState | None = None) -> MainWindowController:
    app_state = state or AppState()
    link_parser = SpotifyLinkParser()
    preview_client = SpotifyPublicPreviewClient(request_timeout=app_state.request_timeout)

    download_search_client = YtDlpSearchClient()
    download_track_mapper = DownloadTrackMapper()
    download_catalog = YtDlpCatalogRepository(download_search_client, download_track_mapper)
    audio_tagger = Mp3AudioTagger(request_timeout=app_state.request_timeout)
    download_assets = YtDlpAssetRepository(app_state, audio_tagger)
    downloadable_search = SearchDownloadableTracksUseCase(download_catalog)
    download_asset = DownloadTrackAssetUseCase(download_assets)

    return MainWindowController(
        state=app_state,
        resolve_input_use_case=None,
        search_downloads_use_case=downloadable_search,
        download_track_use_case=download_asset,
        link_parser=link_parser,
        preview_client=preview_client,
    )


def run() -> int:
    state = AppState()
    app = QApplication(sys.argv)
    configure_app(app)

    controller = build_controller(state)
    window = MainWindow(controller=controller, request_timeout=state.request_timeout)
    window.show()
    return app.exec()
