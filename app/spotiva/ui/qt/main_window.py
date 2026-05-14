from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QSettings, QTimer, Qt
from PyQt6.QtGui import (
    QColor,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from spotiva.core.constants import APP_NAME, SEARCH_MODE_CATALOG, SEARCH_MODE_LYRICS
from spotiva.domain.entities.track import Track
from spotiva.ui.ctrl.main_ctrl import MainWindowController
from spotiva.ui.qt.artwork_cache import ArtworkCache
from spotiva.ui.qt.theme import background_colors
from spotiva.ui.qt.widgets.detail_panel import DetailPanel
from spotiva.ui.qt.widgets.empty_state import EmptyState
from spotiva.ui.qt.widgets.nav_drawer import NavigationDrawer
from spotiva.ui.qt.widgets.loading_state import ResultsLoadingState
from spotiva.ui.qt.widgets.search_bar import SearchBar
from spotiva.ui.qt.widgets.settings_page import SettingsPage
from spotiva.ui.qt.widgets.sidebar import Sidebar
from spotiva.ui.qt.widgets.track_card import TrackCard
from spotiva.ui.qt.workers import (
    ArtworkResolveWorker,
    TrackDownloadWorker,
    TrackSearchWorker,
)


_RESULT_THUMBNAIL_WARMUP_LIMIT = 4
_RESULT_REVEAL_MAX_WAIT_MS = 520


@dataclass
class _SearchModeState:
    query: str = ""
    summary: str = ""
    tracks: list[Track] = field(default_factory=list)
    selected_track_id: str = ""
    resolved_artwork_urls: dict[str, str] = field(default_factory=dict)
    scroll_position: int = 0
    empty_title: str = ""
    empty_message: str = ""
    has_searched: bool = False


class MainWindow(QMainWindow):
    def __init__(
        self,
        controller: MainWindowController,
        request_timeout: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._request_timeout = request_timeout
        self._ui_settings = QSettings(APP_NAME, APP_NAME)
        self._restore_title_search_source()
        self._search_worker = None
        self._download_worker = None
        self._artwork_workers: list[ArtworkResolveWorker] = []
        self._artwork_requests_in_flight: set[str] = set()
        self._resolved_artwork_urls: dict[str, str] = {}
        self._selected_track_id = ""
        self._track_cards = []
        self._pending_thumbnail_track_ids: set[str] = set()
        self._pending_auto_select_track: Track | None = None
        self._artwork_cache = ArtworkCache(self)
        self._artwork_cache.loaded.connect(self._handle_artwork_payload_loaded)
        self._artwork_cache.failed.connect(self._handle_artwork_payload_failed)
        self._intro_started = False
        self._intro_animations = []
        self._pages: dict[str, QWidget] = {}
        self._detail_panel_visible = True
        self._detail_panel_sizes = [760, 420]
        self._active_search_mode = SEARCH_MODE_CATALOG
        self._search_mode_states = {
            SEARCH_MODE_CATALOG: _SearchModeState(),
            SEARCH_MODE_LYRICS: _SearchModeState(),
        }

        self.setWindowTitle(APP_NAME)
        self.resize(1360, 860)
        self.setMinimumSize(980, 680)

        self._results_reveal_timer = QTimer(self)
        self._results_reveal_timer.setSingleShot(True)
        self._results_reveal_timer.timeout.connect(self._reveal_pending_results)

        shell = QFrame(self)
        shell.setObjectName("shell")
        self.setCentralWidget(shell)
        self._shell = shell

        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(18, 18, 18, 18)
        shell_layout.setSpacing(18)

        self._sidebar = Sidebar(
            title_source_label=self._controller.title_search_source_label(),
            parent=shell,
        )
        self._sidebar.menu_requested.connect(self._toggle_nav_drawer)
        shell_layout.addWidget(self._sidebar)

        content = QWidget(shell)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(18)

        self._content_stack = QStackedWidget(content)
        self._content_stack.addWidget(self._build_search_page())
        self._content_stack.addWidget(self._build_settings_page())
        content_layout.addWidget(self._content_stack, 1)
        shell_layout.addWidget(content, 1)

        self._nav_drawer = NavigationDrawer(shell)
        self._nav_drawer.page_requested.connect(self._open_page)
        self._nav_drawer.set_current_page("search")
        self._nav_drawer.setGeometry(shell.rect())

        self._restore_download_directory()
        self._apply_initial_state()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._intro_started:
            return
        self._intro_started = True
        self._start_intro_animation()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_nav_drawer()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        first, second, third = background_colors()
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, first)
        gradient.setColorAt(0.45, second)
        gradient.setColorAt(1.0, third)
        painter.fillRect(self.rect(), gradient)

        glow_top = QRadialGradient(
            self.width() * 0.22,
            self.height() * 0.1,
            self.width() * 0.42,
        )
        glow_top.setColorAt(0.0, QColor(46, 123, 86, 90))
        glow_top.setColorAt(0.45, QColor(46, 123, 86, 28))
        glow_top.setColorAt(1.0, QColor(46, 123, 86, 0))
        painter.fillRect(self.rect(), glow_top)

        glow_right = QRadialGradient(
            self.width() * 0.88,
            self.height() * 0.18,
            self.width() * 0.36,
        )
        glow_right.setColorAt(0.0, QColor(96, 118, 103, 44))
        glow_right.setColorAt(0.55, QColor(96, 118, 103, 14))
        glow_right.setColorAt(1.0, QColor(96, 118, 103, 0))
        painter.fillRect(self.rect(), glow_right)

        glow_bottom = QRadialGradient(
            self.width() * 0.72,
            self.height() * 0.95,
            self.width() * 0.46,
        )
        glow_bottom.setColorAt(0.0, QColor(34, 82, 60, 44))
        glow_bottom.setColorAt(0.5, QColor(34, 82, 60, 15))
        glow_bottom.setColorAt(1.0, QColor(34, 82, 60, 0))
        painter.fillRect(self.rect(), glow_bottom)

    def _build_search_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        self._hero_card = self._build_search_card(page)
        layout.addWidget(self._hero_card)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, page)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(10)
        self._splitter.setOpaqueResize(False)

        self._results_panel = self._build_results_panel(self._splitter)
        self._results_panel.setMinimumWidth(420)
        self._splitter.addWidget(self._results_panel)

        self._detail_panel = DetailPanel(
            request_timeout=self._request_timeout,
            parent=self._splitter,
        )
        self._detail_panel.copy_requested.connect(self._copy_link_to_clipboard)
        self._detail_panel.download_requested.connect(self._start_download)
        self._detail_panel.download_directory_requested.connect(
            self._choose_download_directory
        )
        self._splitter.addWidget(self._detail_panel)

        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)
        self._splitter.setSizes([760, 420])

        layout.addWidget(self._splitter, 1)
        self._pages["search"] = page
        return page

    def _build_settings_page(self) -> QWidget:
        self._settings_page = SettingsPage(
            title_source=self._controller.title_search_source(),
            title_source_options=self._controller.available_title_sources(),
            parent=self,
        )
        self._settings_page.back_requested.connect(lambda: self._open_page("search"))
        self._settings_page.title_source_changed.connect(
            self._apply_title_source_change
        )
        self._pages["settings"] = self._settings_page
        return self._settings_page

    def _build_search_card(self, parent) -> QFrame:
        card = QFrame(parent)
        card.setObjectName("heroCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(12)

        self._search_bar = SearchBar(card)
        self._search_bar.search_requested.connect(self._start_search)
        self._search_bar.mode_changed.connect(self._handle_search_mode_changed)
        layout.addWidget(self._search_bar)

        self._status_label = QLabel("", card)
        self._status_label.setObjectName("statusLabel")
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)
        return card

    def _build_results_panel(self, parent) -> QFrame:
        panel = QFrame(parent)
        panel.setObjectName("resultsCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Results", panel)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self._results_summary = QLabel("", panel)
        self._results_summary.setObjectName("bodyLabel")
        self._results_summary.setWordWrap(True)
        self._results_summary.setVisible(False)
        layout.addWidget(self._results_summary)

        self._results_scroll = QScrollArea(panel)
        self._results_scroll.setWidgetResizable(True)
        self._results_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._results_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self._results_host = QWidget(self._results_scroll)
        self._results_layout = QVBoxLayout(self._results_host)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.setSpacing(12)
        self._results_layout.addStretch()
        self._results_scroll.setWidget(self._results_host)

        self._empty_state = EmptyState("", "", panel)
        self._loading_state = ResultsLoadingState(panel)
        self._results_stack = QStackedWidget(panel)
        self._results_stack.addWidget(self._results_scroll)
        self._results_stack.addWidget(self._empty_state)
        self._results_stack.addWidget(self._loading_state)
        self._results_stack.setCurrentWidget(self._results_scroll)
        layout.addWidget(self._results_stack, 1)
        return panel

    def _apply_initial_state(self) -> None:
        if self._controller.can_accept_input():
            self._detail_panel.show_placeholder()
            self._set_detail_panel_visible(False)
            self._show_results_state()
            if not self._controller.is_ready():
                self._set_status(self._controller.startup_status())
                self._show_empty_state(
                    "Search unavailable",
                    self._controller.onboarding_text(),
                )
                return
            self._set_status("")
            return

        self._search_bar.setDisabled(True)
        self._set_status(self._controller.startup_status())
        self._show_empty_state("Search unavailable", self._controller.onboarding_text())
        self._detail_panel.show_message(
            "Search unavailable",
            self._controller.onboarding_text(),
        )
        self._set_detail_panel_visible(False)

    def _start_search(self, query: str, search_mode: str) -> None:
        normalized = query.strip()
        if search_mode not in {SEARCH_MODE_CATALOG, SEARCH_MODE_LYRICS}:
            search_mode = SEARCH_MODE_CATALOG
        self._active_search_mode = search_mode

        if not normalized:
            self._show_error(self._empty_query_message(search_mode))
            return

        self._search_bar.set_busy(True)
        self._set_status("Searching...")
        self._set_results_summary("")
        self._cancel_pending_results_reveal()
        self._clear_results()
        self._show_loading_state()
        self._detail_panel.show_placeholder()
        self._set_detail_panel_visible(False)
        self._resolved_artwork_urls.clear()
        self._selected_track_id = ""

        self._search_worker = TrackSearchWorker(
            self._controller,
            normalized,
            search_mode,
            self,
        )
        self._search_worker.completed.connect(
            lambda tracks, artwork_payloads: self._handle_search_success(
                normalized,
                search_mode,
                tracks,
                artwork_payloads,
            )
        )
        self._search_worker.failed.connect(
            lambda message: self._handle_search_error(
                normalized,
                search_mode,
                message,
            )
        )
        self._search_worker.finished.connect(lambda: self._search_bar.set_busy(False))
        self._search_worker.start()

    def _handle_search_success(
        self,
        query: str,
        search_mode: str,
        tracks: list[Track],
        artwork_payloads: dict[str, bytes],
    ) -> None:
        if not tracks:
            message = self._nothing_found_message(search_mode)
            self._search_mode_states[search_mode] = _SearchModeState(
                query=query,
                empty_message=message,
                has_searched=True,
            )
            if search_mode != self._active_search_mode:
                return

            self._set_status("")
            self._set_results_summary("")
            self._show_empty_state(
                "",
                message,
            )
            self._clear_results()
            self._detail_panel.show_placeholder()
            self._set_detail_panel_visible(False)
            return

        summary = self._controller.result_summary(query, tracks)
        self._search_mode_states[search_mode] = _SearchModeState(
            query=query,
            summary=summary,
            tracks=list(tracks),
            selected_track_id=tracks[0].track_id,
            has_searched=True,
        )
        if search_mode != self._active_search_mode:
            return

        self._set_status("")
        self._set_results_summary(summary)
        self._detail_panel.prime_artwork_payloads(artwork_payloads)
        self._populate_results(tracks)
        self._prime_album_artwork(tracks)
        self._schedule_results_reveal(tracks[0])

    def _handle_search_error(
        self,
        query: str,
        search_mode: str,
        message: str,
    ) -> None:
        self._search_mode_states[search_mode] = _SearchModeState(
            query=query,
            empty_message=message,
            has_searched=True,
        )
        if search_mode != self._active_search_mode:
            return

        self._set_status("")
        self._set_results_summary("")
        self._cancel_pending_results_reveal()
        self._show_empty_state("", message)
        self._clear_results()
        self._detail_panel.show_message("", message)
        self._set_detail_panel_visible(False)
        self._show_error(message)

    def _handle_search_mode_changed(self, search_mode: str) -> None:
        self._save_visible_search_state(self._active_search_mode)
        self._active_search_mode = search_mode
        self._restore_search_mode_state(search_mode)

    def _save_visible_search_state(self, search_mode: str) -> None:
        state = self._search_mode_states.get(search_mode)
        if state is None:
            return

        state.query = self._search_bar.text()
        state.selected_track_id = self._selected_track_id
        state.resolved_artwork_urls = dict(self._resolved_artwork_urls)
        state.scroll_position = self._results_scroll.verticalScrollBar().value()

    def _restore_search_mode_state(self, search_mode: str) -> None:
        state = self._search_mode_states.get(search_mode, _SearchModeState())
        self._cancel_pending_results_reveal()
        self._search_bar.set_text(state.query)
        self._set_status("")
        self._set_results_summary(state.summary)
        self._clear_results()
        self._resolved_artwork_urls = dict(state.resolved_artwork_urls)
        self._selected_track_id = ""

        if state.tracks:
            self._populate_results(state.tracks, animate=False)
            self._show_results_state()
            for card in self._track_cards:
                self._restore_cached_result_thumbnail(card)
            selected_track = (
                self._track_by_id(state.tracks, state.selected_track_id)
                or state.tracks[0]
            )
            self._select_track(
                selected_track,
                load_artwork_network=False,
                resolve_missing_artwork=False,
            )
            QTimer.singleShot(
                0,
                lambda value=state.scroll_position: (
                    self._results_scroll.verticalScrollBar().setValue(value)
                ),
            )
            return

        if state.has_searched:
            self._show_empty_state(state.empty_title, state.empty_message)
            self._detail_panel.show_placeholder()
            self._set_detail_panel_visible(False)
            return

        self._show_results_state()
        self._detail_panel.show_placeholder()
        self._set_detail_panel_visible(False)

    def _empty_query_message(self, search_mode: str) -> str:
        if search_mode == SEARCH_MODE_LYRICS:
            return "Enter a lyric line."
        return "Enter a track title, album title, or paste a Spotify link."

    def _nothing_found_message(self, search_mode: str) -> str:
        if search_mode == SEARCH_MODE_LYRICS:
            return "No lyric matches found via Genius. Try a longer or more exact line."
        return (
            f"Nothing found on {self._controller.title_search_source_label()}. "
            "Try a more precise track title or album title."
        )

    def _populate_results(self, tracks: list[Track], animate: bool = True) -> None:
        self._clear_results()
        for index, track in enumerate(tracks):
            card = TrackCard(track, self._results_host)
            card.clicked.connect(self._select_track)
            card.thumbnail_ready.connect(self._handle_result_thumbnail_ready)
            self._results_layout.insertWidget(index, card)
            if animate:
                card.fade_in(min(index * 18, 90))
            self._track_cards.append(card)

    def _schedule_results_reveal(self, first_track: Track) -> None:
        self._pending_auto_select_track = first_track
        self._pending_thumbnail_track_ids = {
            card.track.track_id
            for card in self._track_cards[:_RESULT_THUMBNAIL_WARMUP_LIMIT]
        }

        for card in self._track_cards:
            self._warm_result_thumbnail(card)

        if not self._pending_thumbnail_track_ids:
            self._reveal_pending_results()
            return

        self._results_reveal_timer.start(_RESULT_REVEAL_MAX_WAIT_MS)

    def _handle_result_thumbnail_ready(self, track_id: str) -> None:
        if track_id not in self._pending_thumbnail_track_ids:
            return

        self._pending_thumbnail_track_ids.discard(track_id)
        if not self._pending_thumbnail_track_ids:
            self._reveal_pending_results()

    def _reveal_pending_results(self) -> None:
        if self._results_reveal_timer.isActive():
            self._results_reveal_timer.stop()

        track = self._pending_auto_select_track
        self._pending_auto_select_track = None
        self._pending_thumbnail_track_ids.clear()
        self._show_results_state()
        if track is not None:
            self._select_track(track)

    def _warm_result_thumbnail(self, card: TrackCard) -> None:
        artwork_url = card.track.best_image_url()
        if not artwork_url:
            card.thumbnail_ready.emit(card.track.track_id)
            return

        cached_payload = self._artwork_cache.payload(artwork_url)
        if cached_payload:
            card.show_thumbnail_payload(cached_payload)
            return

        self._artwork_cache.request(artwork_url)

    def _restore_cached_result_thumbnail(self, card: TrackCard) -> None:
        artwork_url = card.track.best_image_url()
        if not artwork_url:
            return

        cached_payload = self._artwork_cache.payload(artwork_url)
        if cached_payload:
            card.show_thumbnail_payload(cached_payload)

    def _handle_artwork_payload_loaded(self, artwork_url: str, payload: bytes) -> None:
        self._detail_panel.prime_artwork_payloads({artwork_url: payload})
        for card in self._track_cards:
            if card.track.best_image_url() == artwork_url:
                card.show_thumbnail_payload(payload)

    def _handle_artwork_payload_failed(self, artwork_url: str) -> None:
        for card in self._track_cards:
            if card.track.best_image_url() == artwork_url:
                card.thumbnail_ready.emit(card.track.track_id)

    def _cancel_pending_results_reveal(self) -> None:
        if self._results_reveal_timer.isActive():
            self._results_reveal_timer.stop()
        self._pending_auto_select_track = None
        self._pending_thumbnail_track_ids.clear()

    def _select_track(
        self,
        track: Track,
        load_artwork_network: bool = True,
        resolve_missing_artwork: bool = True,
    ) -> None:
        self._selected_track_id = track.track_id
        state = self._search_mode_states.get(self._active_search_mode)
        if state is not None:
            state.selected_track_id = track.track_id
        for card in self._track_cards:
            card.set_active(card.track.track_id == track.track_id)
        self._set_detail_panel_visible(True)
        self._detail_panel.show_track(
            track,
            load_artwork_network=load_artwork_network,
        )
        prefetched_url = self._resolved_artwork_urls.get(track.track_id, "")
        if prefetched_url and not track.best_image_url():
            self._detail_panel.show_resolved_artwork(track.track_id, prefetched_url)
        if resolve_missing_artwork:
            self._maybe_resolve_selected_artwork(track)

    @staticmethod
    def _track_by_id(tracks: list[Track], track_id: str) -> Track | None:
        if not track_id:
            return None
        for track in tracks:
            if track.track_id == track_id:
                return track
        return None

    def _clear_results(self) -> None:
        self._track_cards.clear()
        while self._results_layout.count():
            item = self._results_layout.takeAt(0)
            widget = item.widget()
            if widget is None:
                continue
            widget.setParent(None)
            widget.deleteLater()
        self._results_layout.addStretch()

    def _copy_link_to_clipboard(self, value: str) -> None:
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(value, mode=clipboard.Mode.Clipboard)

    def _start_download(self, track: Track) -> None:
        if self._download_worker and self._download_worker.isRunning():
            self._show_error("A download is already running.")
            return

        self._detail_panel.set_download_busy(True)
        self._set_status("Downloading...")

        self._download_worker = TrackDownloadWorker(self._controller, track, self)
        self._download_worker.progressed.connect(self._handle_download_progress)
        self._download_worker.completed.connect(self._handle_download_success)
        self._download_worker.failed.connect(self._handle_download_error)
        self._download_worker.finished.connect(
            lambda: self._detail_panel.set_download_busy(False)
        )
        self._download_worker.start()

    def _handle_download_progress(self, bytes_written: int, total_bytes: int) -> None:
        if total_bytes > 0:
            progress = int((bytes_written / total_bytes) * 100)
            self._set_status(f"Downloading... {progress}%")
            return
        downloaded_mb = bytes_written / (1024 * 1024)
        self._set_status(f"Downloading... {downloaded_mb:.1f} MB")

    def _handle_download_success(self, track: Track, file_path: str) -> None:
        _ = Path(file_path).name
        self._set_status("")
        QMessageBox.information(
            self,
            APP_NAME,
            f"{track.saved_item_label()} saved to:\n{file_path}",
        )

    def _maybe_resolve_selected_artwork(self, track: Track) -> None:
        if track.best_image_url() or not track.is_album_result():
            return
        if track.track_id in self._artwork_requests_in_flight:
            return

        worker = ArtworkResolveWorker(self._controller, track, self)
        self._artwork_workers.append(worker)
        self._artwork_requests_in_flight.add(track.track_id)
        worker.completed.connect(self._handle_artwork_resolved)
        worker.failed.connect(self._handle_artwork_resolution_failed)
        worker.finished.connect(
            lambda track_id=track.track_id, current_worker=worker: (
                self._cleanup_artwork_worker(track_id, current_worker)
            )
        )
        worker.start()

    def _handle_artwork_resolved(self, track_id: str, artwork_url: str) -> None:
        self._resolved_artwork_urls[track_id] = artwork_url
        self._detail_panel.prefetch_artwork_url(artwork_url)
        if track_id == self._selected_track_id:
            self._detail_panel.show_resolved_artwork(track_id, artwork_url)

    def _handle_artwork_resolution_failed(self, track_id: str, message: str) -> None:
        _ = track_id
        _ = message

    def _cleanup_artwork_worker(
        self,
        track_id: str,
        worker: ArtworkResolveWorker,
    ) -> None:
        self._artwork_requests_in_flight.discard(track_id)
        if worker in self._artwork_workers:
            self._artwork_workers.remove(worker)
        worker.deleteLater()

    def _prime_album_artwork(self, tracks: list[Track], limit: int = 6) -> None:
        primed = 0
        for track in tracks:
            if primed >= max(1, limit):
                break
            if track.best_image_url() or not track.is_album_result():
                continue
            if track.track_id in self._resolved_artwork_urls:
                self._detail_panel.prefetch_artwork_url(
                    self._resolved_artwork_urls[track.track_id]
                )
                primed += 1
                continue
            self._maybe_resolve_selected_artwork(track)
            primed += 1

    def _handle_download_error(self, message: str) -> None:
        self._set_status("")
        self._show_error(message)

    def _set_status(self, text: str) -> None:
        self._status_label.setText(text)
        self._status_label.setVisible(bool(text))

    def _set_results_summary(self, text: str) -> None:
        self._results_summary.setText(text)
        self._results_summary.setVisible(bool(text))

    def _show_results_state(self) -> None:
        self._loading_state.stop()
        self._results_stack.setCurrentWidget(self._results_scroll)

    def _show_empty_state(self, title: str, message: str) -> None:
        self._loading_state.stop()
        self._empty_state.update_content(title, message)
        self._results_stack.setCurrentWidget(self._empty_state)

    def _show_loading_state(self) -> None:
        self._loading_state.start()
        self._results_stack.setCurrentWidget(self._loading_state)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, APP_NAME, message)

    def _open_page(self, page_name: str) -> None:
        page = self._pages.get(page_name)
        if page is None:
            return
        self._content_stack.setCurrentWidget(page)
        self._nav_drawer.set_current_page(page_name)
        if page_name == "settings":
            self._settings_page.set_title_source(self._controller.title_search_source())

    def _apply_title_source_change(self, value: str) -> None:
        self._controller.set_title_search_source(value)
        self._ui_settings.setValue(
            "title_search_source",
            self._controller.title_search_source(),
        )
        self._sidebar.set_title_source_label(
            self._controller.title_search_source_label()
        )
        self._settings_page.set_title_source(self._controller.title_search_source())
        self._set_status("")

    def _choose_download_directory(self) -> None:
        initial_directory = self._controller.download_directory() or str(Path.home())
        selected_directory = QFileDialog.getExistingDirectory(
            self,
            "Choose download folder",
            initial_directory,
        )
        if not selected_directory:
            return
        self._controller.set_download_directory(selected_directory)
        self._ui_settings.setValue("download_directory", selected_directory)
        self._detail_panel.set_download_directory(self._controller.download_directory())
        self._set_status("")

    def _restore_download_directory(self) -> None:
        saved_directory = str(
            self._ui_settings.value("download_directory", "", type=str) or ""
        ).strip()
        if saved_directory:
            self._controller.set_download_directory(saved_directory)
        self._detail_panel.set_download_directory(self._controller.download_directory())

    def _restore_title_search_source(self) -> None:
        saved_source = str(
            self._ui_settings.value("title_search_source", "", type=str) or ""
        ).strip()
        if saved_source:
            self._controller.set_title_search_source(saved_source)

    def _toggle_nav_drawer(self) -> None:
        self._sync_nav_drawer()
        self._nav_drawer.toggle()

    def _sync_nav_drawer(self) -> None:
        if hasattr(self, "_nav_drawer"):
            self._nav_drawer.setGeometry(self._shell.rect())

    def _start_intro_animation(self) -> None:
        self._fade_in_widget(self._sidebar, delay_ms=0, duration_ms=340)
        self._fade_in_widget(self._hero_card, delay_ms=80, duration_ms=340)
        self._fade_in_widget(self._results_panel, delay_ms=160, duration_ms=360)
        if self._detail_panel.isVisible():
            self._fade_in_widget(self._detail_panel, delay_ms=240, duration_ms=360)

    def _set_detail_panel_visible(self, is_visible: bool) -> None:
        if is_visible == self._detail_panel_visible:
            return

        if is_visible:
            self._detail_panel.show()
            self._splitter.setHandleWidth(10)
            self._splitter.setSizes(self._detail_panel_sizes)
            self._detail_panel_visible = True
            return

        current_sizes = self._splitter.sizes()
        if len(current_sizes) == 2 and current_sizes[1] > 0:
            self._detail_panel_sizes = current_sizes
        self._detail_panel.hide()
        self._splitter.setHandleWidth(0)
        self._splitter.setSizes([1, 0])
        self._detail_panel_visible = False

    def _fade_in_widget(self, widget: QWidget, delay_ms: int, duration_ms: int) -> None:
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)

        animation = QPropertyAnimation(effect, b"opacity", widget)
        animation.setDuration(duration_ms)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        self._intro_animations.append(animation)
        QTimer.singleShot(delay_ms, animation.start)
