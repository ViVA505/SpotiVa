from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
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
from spotiva.infra.genius.lyrics_client import GeniusLyricsClient
from spotiva.infra.spotify.preview_client import SpotifyPublicPreviewClient
from spotiva.ui.ctrl.main_ctrl import MainWindowController
from spotiva.ui.qt.main_window import MainWindow
from spotiva.ui.qt.theme import configure_app


_WINDOWS_APP_ID = "SpotiVa.Desktop"
_APP_ICON_PATH = Path(__file__).resolve().parent / "ui" / "qt" / "assets" / "app_icon.ico"


def build_controller(state: AppState | None = None) -> MainWindowController:
    app_state = state or AppState()
    link_parser = SpotifyLinkParser()
    preview_client = SpotifyPublicPreviewClient(
        request_timeout=app_state.request_timeout
    )

    download_search_client = YtDlpSearchClient(
        request_timeout=app_state.request_timeout
    )
    genius_client = GeniusLyricsClient(request_timeout=app_state.request_timeout)
    download_track_mapper = DownloadTrackMapper()
    download_catalog = YtDlpCatalogRepository(
        download_search_client,
        download_track_mapper,
        genius_client,
    )
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
        artwork_resolver=download_search_client,
    )


def _configure_windows_identity() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            _WINDOWS_APP_ID
        )
    except (AttributeError, OSError):
        return


def _configure_app_icon(app: QApplication) -> None:
    if not _APP_ICON_PATH.exists():
        return
    app.setWindowIcon(QIcon(str(_APP_ICON_PATH)))


def run() -> int:
    state = AppState()
    _configure_windows_identity()
    app = QApplication(sys.argv)
    _configure_app_icon(app)
    configure_app(app)

    controller = build_controller(state)
    window = MainWindow(controller=controller, request_timeout=state.request_timeout)
    window.setWindowIcon(app.windowIcon())
    window.show()
    return app.exec()
