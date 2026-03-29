from __future__ import annotations

from PyQt6.QtGui import QCursor
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton


class AnimatedButton(QPushButton):
    def __init__(self, text: str, object_name: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName(object_name)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))


class PrimaryButton(AnimatedButton):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, "primaryButton", parent)
        self.setMinimumHeight(46)


class SecondaryButton(AnimatedButton):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, "secondaryButton", parent)
        self.setMinimumHeight(44)
