from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from spotiva.core.constants import SEARCH_MODE_CATALOG, SEARCH_MODE_LYRICS
from spotiva.ui.qt.asset_paths import qt_asset_path
from spotiva.ui.qt.widgets.buttons import PrimaryButton
from spotiva.ui.qt.widgets.search_mode_tabs import SearchModeTabs


_SEARCH_ICON_PATH = qt_asset_path("search_action.png")


class SearchBar(QWidget):
    search_requested = pyqtSignal(str, str)
    mode_changed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._is_busy = False
        self._mode = SEARCH_MODE_CATALOG

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._mode_tabs = SearchModeTabs(self)
        self._mode_tabs.selected.connect(self._set_mode)
        layout.addWidget(self._mode_tabs, 0, Qt.AlignmentFlag.AlignLeft)

        input_row = QWidget(self)
        input_layout = QHBoxLayout(input_row)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(12)

        self._input = QLineEdit(self)
        self._input.returnPressed.connect(self._emit_search)
        input_layout.addWidget(self._input, 1)

        self._button = PrimaryButton("", self)
        self._configure_search_button()
        self._button.clicked.connect(self._emit_search)
        input_layout.addWidget(self._button)

        layout.addWidget(input_row)
        self._refresh_placeholder()

    def text(self) -> str:
        return self._input.text()

    def search_mode(self) -> str:
        return self._mode

    def clear(self) -> None:
        self._input.clear()

    def set_text(self, value: str) -> None:
        self._input.setText(value)

    def set_busy(self, is_busy: bool) -> None:
        self._is_busy = is_busy
        self._input.setReadOnly(is_busy)
        self._mode_tabs.setDisabled(is_busy)
        self._button.setDisabled(is_busy)

    def _set_mode(self, value: str) -> None:
        if value == self._mode:
            return
        self._mode = value
        self._refresh_placeholder()
        self.mode_changed.emit(value)

    def _refresh_placeholder(self) -> None:
        if self._mode == SEARCH_MODE_LYRICS:
            self._input.setPlaceholderText("Paste a lyric line")
            return
        self._input.setPlaceholderText(
            "Paste a Spotify link, track title, or album title"
        )

    def _configure_search_button(self) -> None:
        self._button.setFixedWidth(58)
        self._button.setToolTip("Search")
        self._button.setAccessibleName("Search")
        self._button.setIcon(QIcon(str(_SEARCH_ICON_PATH)))
        self._button.setIconSize(QSize(20, 20))

    def _emit_search(self) -> None:
        if self._is_busy:
            return
        self.search_requested.emit(self.text(), self.search_mode())
