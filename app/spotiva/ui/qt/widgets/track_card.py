from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QTimer,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QCursor, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

from spotiva.domain.entities.track import Track
from spotiva.ui.qt.asset_paths import qt_asset_path


_THUMBNAIL_SIZE = 46
_PLACEHOLDER_ICON = qt_asset_path("tab_music_inactive.png")


class TrackCard(QFrame):
    clicked = pyqtSignal(object)
    thumbnail_ready = pyqtSignal(str)

    def __init__(self, track: Track, parent=None) -> None:
        super().__init__(parent)
        self.track = track
        self._fade_animation: QPropertyAnimation | None = None

        self.setObjectName("trackCard")
        self.setProperty("active", "false")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(14, 11, 14, 11)
        root_layout.setSpacing(12)

        self._accent = QFrame(self)
        self._accent.setObjectName("trackAccent")
        self._accent.setFixedWidth(3)
        self._accent.setMinimumHeight(42)
        self._accent.setVisible(False)
        root_layout.addWidget(self._accent)

        self._thumbnail_frame = QFrame(self)
        self._thumbnail_frame.setObjectName("trackThumbnail")
        self._thumbnail_frame.setFixedSize(_THUMBNAIL_SIZE, _THUMBNAIL_SIZE)
        thumbnail_layout = QHBoxLayout(self._thumbnail_frame)
        thumbnail_layout.setContentsMargins(0, 0, 0, 0)
        thumbnail_layout.setSpacing(0)

        self._thumbnail = QLabel(self._thumbnail_frame)
        self._thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumbnail.setFixedSize(_THUMBNAIL_SIZE, _THUMBNAIL_SIZE)
        thumbnail_layout.addWidget(self._thumbnail)
        root_layout.addWidget(self._thumbnail_frame)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(5)

        title = QLabel(track.name, self)
        title.setObjectName("trackTitle")
        title.setWordWrap(False)
        title.setToolTip(track.name)
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        content_layout.addWidget(title)

        meta_text = self._meta_text(track)
        meta_label = QLabel(meta_text, self)
        meta_label.setObjectName("trackMeta")
        meta_label.setWordWrap(False)
        meta_label.setToolTip(meta_text)
        meta_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        content_layout.addWidget(meta_label)

        if track.lyric_match_text:
            lyric_line = QLabel(track.lyric_match_text, self)
            lyric_line.setObjectName("trackLyricLine")
            lyric_line.setWordWrap(False)
            lyric_line.setToolTip(track.lyric_match_text)
            lyric_line.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Fixed,
            )
            content_layout.addWidget(lyric_line)

        root_layout.addLayout(content_layout, 1)

        badge = QLabel(track.card_badge_label(), self)
        badge.setObjectName("trackBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setMinimumWidth(54)
        root_layout.addWidget(badge)

        self.show_thumbnail_placeholder()

    def set_active(self, is_active: bool) -> None:
        self._accent.setVisible(is_active)
        self.setProperty("active", "true" if is_active else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def fade_in(self, delay_ms: int) -> None:
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.0)
        self.setGraphicsEffect(effect)

        self._fade_animation = QPropertyAnimation(effect, b"opacity", self)
        self._fade_animation.setDuration(140)
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        QTimer.singleShot(delay_ms, self._fade_animation.start)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.clicked.emit(self.track)

    def show_thumbnail_placeholder(self) -> None:
        pixmap = QPixmap(str(_PLACEHOLDER_ICON))
        if not pixmap.isNull():
            self._thumbnail.setPixmap(self._scaled_thumbnail(pixmap))

    def show_thumbnail_payload(self, payload: bytes) -> None:
        pixmap = QPixmap()
        pixmap.loadFromData(payload)
        if pixmap.isNull():
            self.thumbnail_ready.emit(self.track.track_id)
            return
        self._thumbnail.setPixmap(self._scaled_thumbnail(pixmap))
        self.thumbnail_ready.emit(self.track.track_id)

    def _scaled_thumbnail(self, pixmap: QPixmap) -> QPixmap:
        return pixmap.scaled(
            _THUMBNAIL_SIZE,
            _THUMBNAIL_SIZE,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _meta_text(self, track: Track) -> str:
        parts = [track.artist_line()]

        if track.is_album_result():
            parts.append(track.item_type_label())
            if track.item_count_label():
                parts.append(track.item_count_label())
            return " / ".join(part for part in parts if part)

        if track.album.name:
            parts.append(track.album.name)

        if track.has_lyric_match():
            parts.append("Genius lyric match")

        return " / ".join(part for part in parts if part)
