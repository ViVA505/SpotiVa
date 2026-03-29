from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout


class EmptyState(QFrame):
    def __init__(self, title: str, message: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("emptyState")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(10)
        layout.addStretch()

        self._title = QLabel(title, self)
        self._title.setObjectName("headlineLabel")
        self._title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._title)

        self._message = QLabel(message, self)
        self._message.setObjectName("bodyLabel")
        self._message.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._message.setWordWrap(True)
        layout.addWidget(self._message)

        layout.addStretch()
        self.update_content(title, message)

    def update_content(self, title: str, message: str) -> None:
        self._title.setText(title)
        self._message.setText(message)
        self._title.setVisible(bool(title))
        self._message.setVisible(bool(message))
