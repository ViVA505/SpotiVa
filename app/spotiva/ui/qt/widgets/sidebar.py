from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QToolButton, QVBoxLayout

from spotiva.core.constants import APP_NAME


class Sidebar(QFrame):
    menu_requested = pyqtSignal()

    def __init__(self, title_source_label: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setMinimumWidth(184)
        self.setMaximumWidth(228)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(18)

        title = QLabel(APP_NAME, self)
        title.setObjectName("brandLabel")

        self._menu_button = QToolButton(self)
        self._menu_button.setObjectName("menuButton")
        self._menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_button.setToolTip("Open navigation")
        self._menu_button.setIcon(_build_hamburger_icon())
        self._menu_button.clicked.connect(self.menu_requested.emit)

        layout.addWidget(title)

        accent = QFrame(self)
        accent.setObjectName("accentLine")
        accent.setFixedHeight(3)
        accent.setFixedWidth(54)
        layout.addWidget(accent)

        layout.addWidget(self._menu_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()

    def set_title_source_label(self, value: str) -> None:
        _ = value


def _build_hamburger_icon() -> QIcon:
    pixmap = QPixmap(22, 22)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(Qt.GlobalColor.white)
    pen.setWidth(2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)

    for y in (6, 11, 16):
        painter.drawLine(4, y, 18, y)
    painter.end()
    return QIcon(pixmap)
