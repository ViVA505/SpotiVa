from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from spotiva.ui.qt.asset_paths import qt_asset_path
from spotiva.ui.qt.widgets.buttons import SecondaryButton
from spotiva.ui.qt.widgets.segmented_switcher import SegmentedSwitcher


TitleSourceSwitcher = SegmentedSwitcher


class SettingsPage(QFrame):
    back_requested = pyqtSignal()
    title_source_changed = pyqtSignal(str)

    def __init__(
        self,
        title_source: str,
        title_source_options: list[tuple[str, str]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self._intro_animations: list[QPropertyAnimation] = []
        self._intro_effects: dict[QWidget, QGraphicsOpacityEffect] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(22)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._header = QWidget(self)
        self._header.setFixedWidth(292)
        header_layout = QVBoxLayout(self._header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(18)

        top_row = QWidget(self._header)
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(12)

        self._back_button = SecondaryButton("Back", top_row)
        self._back_button.clicked.connect(self.back_requested.emit)
        top_layout.addWidget(self._back_button, 0, Qt.AlignmentFlag.AlignLeft)
        top_layout.addStretch()
        header_layout.addWidget(top_row)

        title = QLabel("Settings", self._header)
        title.setObjectName("settingsPageTitle")
        header_layout.addWidget(title)
        layout.addWidget(self._header, 0, Qt.AlignmentFlag.AlignHCenter)

        self._source_card = QFrame(self)
        self._source_card.setObjectName("settingsSurface")
        self._source_card.setFixedWidth(292)

        source_layout = QVBoxLayout(self._source_card)
        source_layout.setContentsMargins(26, 24, 26, 24)
        source_layout.setSpacing(16)

        source_label = QLabel("Search Source", self._source_card)
        source_label.setObjectName("settingsSurfaceTitle")
        source_layout.addWidget(source_label)

        self._source_switcher = TitleSourceSwitcher(
            title_source_options,
            self._source_card,
            icons={
                "youtube": str(qt_asset_path("source_youtube.svg")),
                "soundcloud": str(qt_asset_path("source_soundcloud.svg")),
            },
            icon_only=True,
        )
        self._source_switcher.selected.connect(self.title_source_changed.emit)
        source_layout.addWidget(
            self._source_switcher,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

        layout.addWidget(self._source_card, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

        self._prepare_intro_effect(self._header)
        self._prepare_intro_effect(self._source_card)
        self.set_title_source(title_source)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._play_intro)

    def set_title_source(self, value: str) -> None:
        self._source_switcher.set_value(value, animated=self.isVisible())

    def _prepare_intro_effect(self, widget: QWidget) -> None:
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(1.0)
        widget.setGraphicsEffect(effect)
        self._intro_effects[widget] = effect

    def _play_intro(self) -> None:
        for animation in self._intro_animations:
            animation.stop()
        self._intro_animations.clear()

        for delay_ms, widget in (
            (0, self._header),
            (90, self._source_card),
        ):
            effect = self._intro_effects[widget]
            effect.setOpacity(0.0)

            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(280)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._intro_animations.append(animation)
            QTimer.singleShot(delay_ms, animation.start)
