from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel


class InfoChip(QFrame):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("infoChip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(0)

        self._label = QLabel(text, self)
        self._label.setObjectName("chipText")
        layout.addWidget(self._label)

    def set_text(self, text: str) -> None:
        self._label.setText(text)
