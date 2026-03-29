from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

from spotiva.ui.qt.widgets.buttons import PrimaryButton


class SearchBar(QWidget):
    search_requested = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._is_busy = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._input = QLineEdit(self)
        self._input.setPlaceholderText("Paste a Spotify track link or enter a song title")
        self._input.returnPressed.connect(self._emit_search)
        layout.addWidget(self._input, 1)

        self._button = PrimaryButton("Search", self)
        self._button.clicked.connect(self._emit_search)
        layout.addWidget(self._button)

    def text(self) -> str:
        return self._input.text()

    def clear(self) -> None:
        self._input.clear()

    def set_busy(self, is_busy: bool) -> None:
        self._is_busy = is_busy
        self._input.setReadOnly(is_busy)
        self._button.setText("Search")

    def _emit_search(self) -> None:
        if self._is_busy:
            return
        self.search_requested.emit(self.text())
