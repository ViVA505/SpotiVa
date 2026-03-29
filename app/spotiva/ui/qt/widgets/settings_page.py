from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, QTimer, Qt, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from spotiva.ui.qt.widgets.buttons import SecondaryButton


class TitleSourceSwitcher(QWidget):
    selected = pyqtSignal(str)

    def __init__(self, options: list[tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        self._options = options
        self._current_index = 0
        self._hover_index = -1
        self._indicator_x = 0.0
        self._segment_spacing = 8.0
        self._segment_padding = 8.0
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMouseTracking(True)
        self.setMinimumHeight(70)
        self.setMinimumWidth(self.minimumSizeHint().width())

        self._indicator_animation = QPropertyAnimation(self, b"indicatorX", self)
        self._indicator_animation.setDuration(260)
        self._indicator_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        QTimer.singleShot(0, self._sync_indicator_position)

    def get_indicator_x(self) -> float:
        return self._indicator_x

    def set_indicator_x(self, value: float) -> None:
        self._indicator_x = value
        self.update()

    indicatorX = pyqtProperty(float, fget=get_indicator_x, fset=set_indicator_x)

    def set_value(self, value: str, animated: bool) -> None:
        for index, (option_value, _) in enumerate(self._options):
            if option_value != value:
                continue
            self._current_index = index
            target_x = self._segment_rect(index).x()
            if animated and self.isVisible():
                self._indicator_animation.stop()
                self._indicator_animation.setStartValue(self._indicator_x)
                self._indicator_animation.setEndValue(target_x)
                self._indicator_animation.start()
            else:
                self._indicator_x = target_x
                self.update()
            return

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_indicator_position()

    def sizeHint(self) -> QSize:
        label_font = QFont("Segoe UI Semibold", 11)
        metrics = QFontMetrics(label_font)
        segment_widths = [max(144, metrics.horizontalAdvance(label) + 52) for _, label in self._options]
        total_width = int(sum(segment_widths) + (self._segment_spacing * max(0, len(self._options) - 1)) + (self._segment_padding * 2))
        return QSize(total_width, 70)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        self._hover_index = self._index_at(event.position().x(), event.position().y())
        self.update()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._hover_index = -1
        self.update()

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        index = self._index_at(event.position().x(), event.position().y())
        if index < 0 or index == self._current_index:
            return
        self.set_value(self._options[index][0], animated=True)
        self.selected.emit(self._options[index][0])

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        outer_rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(255, 255, 255, 10), 1))
        painter.setBrush(QColor(9, 11, 10, 245))
        painter.drawRoundedRect(outer_rect, 22, 22)

        active_rect = self._segment_rect(self._current_index)
        if active_rect.width() > 0:
            active_rect.moveLeft(self._indicator_x)
            gradient = QLinearGradient(active_rect.topLeft(), active_rect.bottomRight())
            gradient.setColorAt(0.0, QColor(52, 228, 124, 244))
            gradient.setColorAt(1.0, QColor(120, 247, 175, 228))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawRoundedRect(active_rect, 18, 18)

        label_font = QFont("Segoe UI Semibold", 11)
        painter.setFont(label_font)

        for index, (_, label) in enumerate(self._options):
            segment_rect = self._segment_rect(index)
            if index == self._hover_index and index != self._current_index:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255, 255, 255, 10))
                painter.drawRoundedRect(segment_rect, 18, 18)

            if index == self._current_index:
                painter.setPen(QColor(4, 17, 9))
            elif index == self._hover_index:
                painter.setPen(QColor(255, 255, 255))
            else:
                painter.setPen(QColor(244, 247, 245, 186))

            painter.drawText(segment_rect, Qt.AlignmentFlag.AlignCenter, label)

    def _index_at(self, x: float, y: float) -> int:
        point_x = float(x)
        point_y = float(y)
        for index in range(len(self._options)):
            if self._segment_rect(index).contains(point_x, point_y):
                return index
        return -1

    def _segment_rect(self, index: int) -> QRectF:
        option_count = max(1, len(self._options))
        total_spacing = self._segment_spacing * (option_count - 1)
        width = max(0.0, self.width() - (self._segment_padding * 2) - total_spacing)
        segment_width = width / option_count if option_count else 0.0
        x = self._segment_padding + index * (segment_width + self._segment_spacing)
        y = self._segment_padding
        height = max(0.0, self.height() - (self._segment_padding * 2))
        return QRectF(x, y, segment_width, height)

    def _sync_indicator_position(self) -> None:
        self._indicator_animation.stop()
        self._indicator_x = self._segment_rect(self._current_index).x()
        self.update()


class SettingsPage(QFrame):
    back_requested = pyqtSignal()
    title_source_changed = pyqtSignal(str)

    def __init__(self, title_source: str, title_source_options: list[tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self._intro_animations: list[QPropertyAnimation] = []
        self._intro_effects: dict[QWidget, QGraphicsOpacityEffect] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(22)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._header = QWidget(self)
        self._header.setMaximumWidth(780)
        self._header.setMinimumWidth(460)
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
        self._source_card.setMaximumWidth(780)
        self._source_card.setMinimumWidth(460)

        source_layout = QVBoxLayout(self._source_card)
        source_layout.setContentsMargins(28, 26, 28, 28)
        source_layout.setSpacing(18)

        source_label = QLabel("Search Source", self._source_card)
        source_label.setObjectName("settingsSurfaceTitle")
        source_layout.addWidget(source_label)

        self._source_switcher = TitleSourceSwitcher(title_source_options, self._source_card)
        self._source_switcher.selected.connect(self.title_source_changed.emit)
        source_layout.addWidget(self._source_switcher)

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

        for delay_ms, widget in ((0, self._header), (90, self._source_card)):
            effect = self._intro_effects[widget]
            effect.setOpacity(0.0)

            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(280)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._intro_animations.append(animation)
            QTimer.singleShot(delay_ms, animation.start)
