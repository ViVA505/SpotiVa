from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QSettings, QTimer, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter, QRadialGradient
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

from spotiva.core.constants import APP_NAME
from spotiva.domain.entities.track import Track
from spotiva.ui.ctrl.main_ctrl import MainWindowController
from spotiva.ui.qt.theme import background_colors
from spotiva.ui.qt.widgets.detail_panel import DetailPanel
from spotiva.ui.qt.widgets.empty_state import EmptyState
from spotiva.ui.qt.widgets.nav_drawer import NavigationDrawer
from spotiva.ui.qt.widgets.loading_state import ResultsLoadingState
from spotiva.ui.qt.widgets.search_bar import SearchBar
from spotiva.ui.qt.widgets.settings_page import SettingsPage
from spotiva.ui.qt.widgets.sidebar import Sidebar
from spotiva.ui.qt.widgets.track_card import TrackCard
from spotiva.ui.qt.workers import TrackDownloadWorker, TrackSearchWorker


class MainWindow(QMainWindow):
    def __init__(self, controller: MainWindowController, request_timeout: int, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._request_timeout = request_timeout
        self._ui_settings = QSettings(APP_NAME, APP_NAME)
        self._restore_title_search_source()
        self._search_worker = None
        self._download_worker = None
        self._track_cards = []
        self._intro_started = False
        self._intro_animations = []
        self._pages: dict[str, QWidget] = {}
        self._detail_panel_visible = True
        self._detail_panel_sizes = [760, 420]

        self.setWindowTitle(APP_NAME)
        self.resize(1360, 860)
        self.setMinimumSize(980, 680)

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

        glow_top = QRadialGradient(self.width() * 0.22, self.height() * 0.1, self.width() * 0.42)
        glow_top.setColorAt(0.0, QColor(46, 123, 86, 90))
        glow_top.setColorAt(0.45, QColor(46, 123, 86, 28))
        glow_top.setColorAt(1.0, QColor(46, 123, 86, 0))
        painter.fillRect(self.rect(), glow_top)

        glow_right = QRadialGradient(self.width() * 0.88, self.height() * 0.18, self.width() * 0.36)
        glow_right.setColorAt(0.0, QColor(96, 118, 103, 44))
        glow_right.setColorAt(0.55, QColor(96, 118, 103, 14))
        glow_right.setColorAt(1.0, QColor(96, 118, 103, 0))
        painter.fillRect(self.rect(), glow_right)

        glow_bottom = QRadialGradient(self.width() * 0.72, self.height() * 0.95, self.width() * 0.46)
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

        self._detail_panel = DetailPanel(request_timeout=self._request_timeout, parent=self._splitter)
        self._detail_panel.copy_requested.connect(self._copy_link_to_clipboard)
        self._detail_panel.download_requested.connect(self._start_download)
        self._detail_panel.download_directory_requested.connect(self._choose_download_directory)
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
        self._settings_page.title_source_changed.connect(self._apply_title_source_change)
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
        self._results_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._results_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

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
                self._show_empty_state("Search unavailable", self._controller.onboarding_text())
                return
            self._set_status("")
            return

        self._search_bar.setDisabled(True)
        self._set_status(self._controller.startup_status())
        self._show_empty_state("Search unavailable", self._controller.onboarding_text())
        self._detail_panel.show_message("Search unavailable", self._controller.onboarding_text())
        self._set_detail_panel_visible(False)

    def _start_search(self, query: str) -> None:
        normalized = query.strip()
        if not normalized:
            self._show_error("Enter a song title or paste a Spotify track link.")
            return

        self._search_bar.set_busy(True)
        self._set_status("Searching...")
        self._set_results_summary("")
        self._clear_results()
        self._show_loading_state()
        self._detail_panel.show_placeholder()
        self._set_detail_panel_visible(False)

        self._search_worker = TrackSearchWorker(self._controller, normalized, self)
        self._search_worker.completed.connect(lambda tracks: self._handle_search_success(normalized, tracks))
        self._search_worker.failed.connect(self._handle_search_error)
        self._search_worker.finished.connect(lambda: self._search_bar.set_busy(False))
        self._search_worker.start()

    def _handle_search_success(self, query: str, tracks: list[Track]) -> None:
        if not tracks:
            self._set_status("")
            self._set_results_summary("")
            self._show_empty_state(
                "",
                f"Nothing found on {self._controller.title_search_source_label()}. Try a more precise title.",
            )
            self._clear_results()
            self._detail_panel.show_placeholder()
            self._set_detail_panel_visible(False)
            return

        self._set_status("")
        self._set_results_summary("")
        self._populate_results(tracks)
        self._show_results_state()
        self._select_track(tracks[0])

    def _handle_search_error(self, message: str) -> None:
        self._set_status("")
        self._set_results_summary("")
        self._show_empty_state("", message)
        self._clear_results()
        self._detail_panel.show_message("", message)
        self._set_detail_panel_visible(False)
        self._show_error(message)

    def _populate_results(self, tracks: list[Track]) -> None:
        self._clear_results()
        for index, track in enumerate(tracks):
            card = TrackCard(track, self._results_host)
            card.clicked.connect(self._select_track)
            self._results_layout.insertWidget(index, card)
            card.fade_in(min(index * 18, 90))
            self._track_cards.append(card)
        self._results_layout.addStretch()

    def _select_track(self, track: Track) -> None:
        for card in self._track_cards:
            card.set_active(card.track.track_id == track.track_id)
        self._set_detail_panel_visible(True)
        self._detail_panel.show_track(track)

    def _clear_results(self) -> None:
        self._track_cards.clear()
        while self._results_layout.count():
            item = self._results_layout.takeAt(0)
            widget = item.widget()
            if widget is None:
                continue
            widget.setParent(None)
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
        self._download_worker.finished.connect(lambda: self._detail_panel.set_download_busy(False))
        self._download_worker.start()

    def _handle_download_progress(self, bytes_written: int, total_bytes: int) -> None:
        if total_bytes > 0:
            progress = int((bytes_written / total_bytes) * 100)
            self._set_status(f"Downloading... {progress}%")
            return
        downloaded_mb = bytes_written / (1024 * 1024)
        self._set_status(f"Downloading... {downloaded_mb:.1f} MB")

    def _handle_download_success(self, file_path: str) -> None:
        _ = Path(file_path).name
        self._set_status("")
        QMessageBox.information(self, APP_NAME, f"Track saved to:\n{file_path}")

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
        self._ui_settings.setValue("title_search_source", self._controller.title_search_source())
        self._sidebar.set_title_source_label(self._controller.title_search_source_label())
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
        saved_directory = str(self._ui_settings.value("download_directory", "", type=str) or "").strip()
        if saved_directory:
            self._controller.set_download_directory(saved_directory)
        self._detail_panel.set_download_directory(self._controller.download_directory())

    def _restore_title_search_source(self) -> None:
        saved_source = str(self._ui_settings.value("title_search_source", "", type=str) or "").strip()
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
