from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QIcon, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from spotiva.domain.entities.track import Track
from spotiva.ui.qt.widgets.buttons import PrimaryButton, SecondaryButton


_FOLDER_ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "folder_download.svg"


class ArtworkLoader(QThread):
    completed = pyqtSignal(str, bytes)
    failed = pyqtSignal(str)

    def __init__(self, url: str, timeout: int, parent=None) -> None:
        super().__init__(parent)
        self._url = url
        self._timeout = timeout

    def run(self) -> None:
        try:
            with urlopen(self._url, timeout=self._timeout) as response:
                self.completed.emit(self._url, response.read())
        except Exception:
            self.failed.emit(self._url)


def _build_folder_icon() -> QIcon:
    return QIcon(str(_FOLDER_ICON_PATH))


class DetailPanel(QFrame):
    _BASE_WIDTH = 420
    _MIN_SCALE = 0.92
    _MAX_SCALE = 1.45

    copy_requested = pyqtSignal(str)
    download_requested = pyqtSignal(object)
    download_directory_requested = pyqtSignal()

    def __init__(self, request_timeout: int, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("detailCard")
        self.setMinimumWidth(320)
        self._request_timeout = request_timeout
        self._track = None
        self._artwork_loader = None
        self._artwork_cache: dict[str, QPixmap] = {}
        self._pending_artwork_url = ""
        self._is_download_busy = False

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(24, 24, 24, 24)
        self._layout.setSpacing(14)

        self._cover_frame = QFrame(self)
        self._cover_frame.setObjectName("artworkFrame")
        self._cover_layout = QVBoxLayout(self._cover_frame)
        self._cover_layout.setContentsMargins(0, 0, 0, 0)
        self._cover_layout.setSpacing(0)

        self._cover_label = QLabel(self._cover_frame)
        self._cover_label.setObjectName("artworkLabel")
        self._cover_label.setFixedSize(240, 240)
        self._cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_label.setText("No artwork")
        self._cover_layout.addWidget(self._cover_label)
        self._layout.addWidget(self._cover_frame, alignment=Qt.AlignmentFlag.AlignLeft)

        self._title = QLabel("", self)
        self._title.setObjectName("detailTitleLabel")
        self._title.setWordWrap(True)
        self._layout.addWidget(self._title)

        self._artist_label = QLabel("", self)
        self._artist_label.setObjectName("detailArtistLabel")
        self._artist_label.setWordWrap(True)
        self._layout.addWidget(self._artist_label)

        self._meta_label = QLabel("", self)
        self._meta_label.setObjectName("detailMetaLabel")
        self._meta_label.setWordWrap(True)
        self._meta_label.setVisible(False)
        self._layout.addWidget(self._meta_label)

        self._action_surface = QFrame(self)
        self._action_surface.setObjectName("actionSurface")
        self._action_surface.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        self._action_layout = QVBoxLayout(self._action_surface)
        self._action_layout.setContentsMargins(12, 18, 18, 18)
        self._action_layout.setSpacing(14)

        self._download_actions = QWidget(self._action_surface)
        self._buttons_row = QHBoxLayout(self._download_actions)
        self._buttons_row.setContentsMargins(0, 0, 0, 0)
        self._buttons_row.setSpacing(10)
        self._download_button = PrimaryButton("Download", self._action_surface)
        self._download_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._download_button.clicked.connect(self._download_track)
        self._buttons_row.addWidget(self._download_button)
        self._buttons_row.addStretch(1)

        self._folder_button = QToolButton(self._action_surface)
        self._folder_button.setObjectName("iconButton")
        self._folder_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._folder_button.setIcon(_build_folder_icon())
        self._folder_button.setIconSize(QSize(22, 22))
        self._folder_button.setToolTip("Choose download folder")
        self._folder_button.clicked.connect(self.download_directory_requested.emit)
        self._buttons_row.addWidget(self._folder_button)
        self._action_layout.addWidget(self._download_actions)

        self._download_path_label = QLabel("", self._action_surface)
        self._download_path_label.setObjectName("downloadPathLabel")
        self._download_path_label.setWordWrap(True)
        self._action_layout.addWidget(self._download_path_label)

        self._actions_container = QWidget(self._action_surface)
        self._secondary_buttons_row = QHBoxLayout(self._actions_container)
        self._secondary_buttons_row.setContentsMargins(0, 0, 0, 0)
        self._secondary_buttons_row.setSpacing(10)

        self._open_button = SecondaryButton("Open", self._action_surface)
        self._open_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._open_button.clicked.connect(self._open_track)
        self._secondary_buttons_row.addWidget(self._open_button)

        self._copy_button = SecondaryButton("Copy Link", self._action_surface)
        self._copy_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._copy_button.clicked.connect(self._copy_link)
        self._secondary_buttons_row.addWidget(self._copy_button)
        self._action_layout.addWidget(self._actions_container)
        self._layout.addWidget(self._action_surface, alignment=Qt.AlignmentFlag.AlignLeft)
        self._layout.addStretch()

        self._reveal = QPropertyAnimation(self, b"windowOpacity", self)
        self._reveal.setDuration(220)
        self._reveal.setStartValue(0.85)
        self._reveal.setEndValue(1.0)
        self._reveal.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._apply_responsive_metrics()
        self.show_placeholder()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_metrics()

    def show_track(self, track: Track) -> None:
        self._track = track
        self._title.setText(track.name)
        self._artist_label.setText(track.artist_line())
        meta_parts = []
        if track.album.name:
            meta_parts.append(track.album.name)
        if track.duration_ms > 0:
            meta_parts.append(track.duration_label())
        self._meta_label.setText(" / ".join(meta_parts))
        self._title.setVisible(True)
        self._artist_label.setVisible(bool(track.artist_line()))
        self._meta_label.setVisible(bool(meta_parts))
        self._action_surface.setVisible(True)
        has_open_url = bool(track.open_url())
        has_copy_url = bool(track.copy_url())
        self._open_button.setEnabled(has_open_url)
        self._copy_button.setEnabled(has_copy_url)
        self._open_button.setVisible(has_open_url)
        self._copy_button.setVisible(has_copy_url)
        self._actions_container.setVisible(has_open_url or has_copy_url)
        self._update_download_controls()
        self._reveal.start()

        image_url = track.best_image_url()
        if image_url:
            self._load_artwork(image_url)
        else:
            self._pending_artwork_url = ""
            self._cover_label.setPixmap(QPixmap())
            self._cover_label.setText("No artwork")

    def show_message(self, title: str, message: str) -> None:
        self._track = None
        self._title.setText(title)
        self._artist_label.setText(message)
        self._meta_label.clear()
        self._title.setVisible(bool(title))
        self._artist_label.setVisible(bool(message))
        self._meta_label.setVisible(False)
        self._action_surface.setVisible(True)
        self._actions_container.setVisible(False)
        self._update_download_controls()
        self._pending_artwork_url = ""
        self._cover_label.setPixmap(QPixmap())
        self._cover_label.setText("No artwork")

    def show_placeholder(self) -> None:
        self._track = None
        self._title.clear()
        self._artist_label.clear()
        self._meta_label.clear()
        self._title.setVisible(False)
        self._artist_label.setVisible(False)
        self._meta_label.setVisible(False)
        self._action_surface.setVisible(True)
        self._actions_container.setVisible(False)
        self._update_download_controls()
        self._pending_artwork_url = ""
        self._cover_label.setPixmap(QPixmap())
        self._cover_label.setText("No artwork")

    def set_download_busy(self, is_busy: bool) -> None:
        self._is_download_busy = is_busy
        self._update_download_controls()

    def set_download_directory(self, directory: str) -> None:
        normalized = directory.strip()
        if normalized:
            self._download_path_label.setText(normalized)
            return
        self._download_path_label.setText("Choose a download folder")

    def _apply_responsive_metrics(self) -> None:
        scale = self._responsive_scale()

        outer_margin = self._scaled(24, scale)
        outer_spacing = self._scaled(14, scale)
        self._layout.setContentsMargins(outer_margin, outer_margin, outer_margin, outer_margin)
        self._layout.setSpacing(outer_spacing)

        cover_size = self._scaled(240, scale)
        self._cover_label.setFixedSize(cover_size, cover_size)

        action_left = self._scaled(12, scale)
        action_top = self._scaled(18, scale)
        action_right = self._scaled(18, scale)
        action_bottom = self._scaled(18, scale)
        action_spacing = self._scaled(14, scale)
        self._action_layout.setContentsMargins(action_left, action_top, action_right, action_bottom)
        self._action_layout.setSpacing(action_spacing)

        row_spacing = self._scaled(10, scale)
        self._buttons_row.setSpacing(row_spacing)
        self._secondary_buttons_row.setSpacing(row_spacing)

        download_width = self._scaled(208, scale)
        primary_height = self._scaled(46, scale)
        secondary_height = self._scaled(44, scale)
        secondary_width = self._scaled(160, scale)
        folder_size = self._scaled(44, scale)
        icon_size = self._scaled(22, scale)

        self._download_button.setFixedSize(download_width, primary_height)
        self._open_button.setFixedSize(secondary_width, secondary_height)
        self._copy_button.setFixedSize(secondary_width, secondary_height)
        self._folder_button.setFixedSize(folder_size, folder_size)
        self._folder_button.setIconSize(QSize(icon_size, icon_size))

        action_content_width = max(
            download_width + row_spacing + folder_size,
            (secondary_width * 2) + row_spacing,
        )
        action_width = action_content_width + action_left + action_right
        self._action_surface.setFixedWidth(action_width)
        self._download_path_label.setMaximumWidth(action_content_width)

        self._title.setStyleSheet(f"font-size: {self._scaled(24, scale)}px;")
        self._artist_label.setStyleSheet(f"font-size: {self._scaled(15, scale)}px;")
        self._meta_label.setStyleSheet(f"font-size: {self._scaled(13, scale)}px;")
        self._download_path_label.setStyleSheet(f"font-size: {self._scaled(12, scale)}px;")
        self._cover_label.setStyleSheet(f"font-size: {self._scaled(13, scale)}px;")
        button_font_size = self._scaled(13, scale)
        self._download_button.setStyleSheet(f"font-size: {button_font_size}px;")
        self._open_button.setStyleSheet(f"font-size: {button_font_size}px;")
        self._copy_button.setStyleSheet(f"font-size: {button_font_size}px;")

        cached_artwork = self._artwork_cache.get(self._pending_artwork_url)
        if cached_artwork is not None:
            self._cover_label.setPixmap(self._scaled_artwork_pixmap(cached_artwork))

    def _responsive_scale(self) -> float:
        if self.width() <= 0:
            return 1.0
        normalized = self.width() / self._BASE_WIDTH
        return max(self._MIN_SCALE, min(normalized, self._MAX_SCALE))

    @staticmethod
    def _scaled(value: int, scale: float) -> int:
        return max(1, int(round(value * scale)))

    def _load_artwork(self, url: str) -> None:
        cached_pixmap = self._artwork_cache.get(url)
        if cached_pixmap is not None:
            self._pending_artwork_url = url
            self._cover_label.setPixmap(self._scaled_artwork_pixmap(cached_pixmap))
            self._cover_label.setText("")
            return

        self._pending_artwork_url = url
        self._cover_label.setText("Loading artwork...")
        self._cover_label.setPixmap(QPixmap())

        self._artwork_loader = ArtworkLoader(url, self._request_timeout, self)
        self._artwork_loader.completed.connect(self._apply_artwork)
        self._artwork_loader.failed.connect(self._apply_artwork_fallback)
        self._artwork_loader.start()

    def _apply_artwork(self, url: str, data: bytes) -> None:
        if url != self._pending_artwork_url:
            return

        pixmap = QPixmap()
        pixmap.loadFromData(data)
        if pixmap.isNull():
            self._apply_artwork_fallback(url)
            return

        self._artwork_cache[url] = pixmap
        self._cover_label.setPixmap(self._scaled_artwork_pixmap(pixmap))
        self._cover_label.setText("")

    def _apply_artwork_fallback(self, url: str) -> None:
        if url != self._pending_artwork_url:
            return
        self._cover_label.setPixmap(QPixmap())
        self._cover_label.setText("Artwork unavailable")

    def _open_track(self) -> None:
        if self._track and self._track.open_url():
            QDesktopServices.openUrl(QUrl(self._track.open_url()))

    def _copy_link(self) -> None:
        if self._track and self._track.copy_url():
            self.copy_requested.emit(self._track.copy_url())

    def _download_track(self) -> None:
        if self._track and self._track.is_downloadable:
            self.download_requested.emit(self._track)

    def _scaled_artwork_pixmap(self, pixmap: QPixmap) -> QPixmap:
        return pixmap.scaled(
            self._cover_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _update_download_controls(self) -> None:
        can_download = bool(self._track and self._track.is_downloadable and not self._is_download_busy)
        self._download_button.setEnabled(can_download)
        self._download_button.setText("Downloading..." if self._is_download_busy else "Download")
        self._folder_button.setEnabled(not self._is_download_busy)
