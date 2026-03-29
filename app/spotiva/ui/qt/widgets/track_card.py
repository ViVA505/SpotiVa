from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from spotiva.domain.entities.track import Track


class TrackCard(QFrame):
    clicked = pyqtSignal(object)

    def __init__(self, track: Track, parent=None) -> None:
        super().__init__(parent)
        self.track = track

        self.setObjectName("trackCard")
        self.setProperty("active", "false")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(14, 14, 18, 14)
        root_layout.setSpacing(12)

        self._accent = QFrame(self)
        self._accent.setObjectName("trackAccent")
        self._accent.setFixedWidth(4)
        self._accent.setMinimumHeight(34)
        self._accent.setVisible(False)
        root_layout.addWidget(self._accent)

        content_layout = QVBoxLayout()
        content_layout.setSpacing(4)

        title = QLabel(track.name, self)
        title.setObjectName("cardTitle")
        title.setWordWrap(True)
        content_layout.addWidget(title)

        subtitle = QLabel(f"{track.artist_line()} | {track.album.name}", self)
        subtitle.setObjectName("cardSubtitle")
        subtitle.setWordWrap(True)
        content_layout.addWidget(subtitle)

        root_layout.addLayout(content_layout, 1)

        duration = QLabel(track.duration_label(), self)
        duration.setObjectName("durationLabel")
        root_layout.addWidget(duration, alignment=Qt.AlignmentFlag.AlignTop)

    def set_active(self, is_active: bool) -> None:
        self._accent.setVisible(is_active)
        self.setProperty("active", "true" if is_active else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def fade_in(self, delay_ms: int) -> None:
        _ = delay_ms

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.clicked.emit(self.track)
