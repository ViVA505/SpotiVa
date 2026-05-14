from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    QTimer,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QWidget


class SegmentedSwitcher(QWidget):
    selected = pyqtSignal(str)

    def __init__(
        self,
        options: list[tuple[str, str]],
        parent=None,
        icons: dict[str, str] | None = None,
        icon_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self._options = options
        self._icons = {
            key: QPixmap(path)
            for key, path in (icons or {}).items()
        }
        self._icon_only = icon_only
        self._current_index = 0
        self._hover_index = -1
        self._indicator_x = 0.0
        self._segment_spacing = 8.0
        self._segment_padding = 8.0
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMouseTracking(True)
        self.setMinimumHeight(70)
        self.setMinimumWidth(self.minimumSizeHint().width())
        if self._icon_only:
            self.setFixedSize(self.sizeHint())

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

    def value(self) -> str:
        if not self._options:
            return ""
        return self._options[self._current_index][0]

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_indicator_position()

    def sizeHint(self) -> QSize:
        if self._icon_only:
            segment_widths = [76 for _ in self._options]
            total_width = int(
                sum(segment_widths)
                + (self._segment_spacing * max(0, len(self._options) - 1))
                + (self._segment_padding * 2)
            )
            return QSize(total_width, 64)

        label_font = QFont("Segoe UI Semibold", 11)
        metrics = QFontMetrics(label_font)
        segment_widths = [
            max(144, metrics.horizontalAdvance(label) + 52)
            for _, label in self._options
        ]
        total_width = int(
            sum(segment_widths)
            + (self._segment_spacing * max(0, len(self._options) - 1))
            + (self._segment_padding * 2)
        )
        return QSize(total_width, 70)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        self._hover_index = self._index_at(event.position().x(), event.position().y())
        self._refresh_tooltip()
        self.update()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._hover_index = -1
        self.setToolTip("")
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

        if not self._icon_only:
            label_font = QFont("Segoe UI Semibold", 11)
            painter.setFont(label_font)

        for index, (value, label) in enumerate(self._options):
            segment_rect = self._segment_rect(index)
            if index == self._hover_index and index != self._current_index:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255, 255, 255, 10))
                painter.drawRoundedRect(segment_rect, 18, 18)

            if index == self._current_index:
                color = QColor(4, 17, 9)
            elif index == self._hover_index:
                color = QColor(255, 255, 255)
            else:
                color = QColor(244, 247, 245, 186)

            icon = self._icons.get(value)
            if self._icon_only and icon is not None and not icon.isNull():
                self._draw_icon(painter, segment_rect, icon, color)
                continue

            painter.setPen(color)
            painter.drawText(segment_rect, Qt.AlignmentFlag.AlignCenter, label)

    def _draw_icon(
        self,
        painter: QPainter,
        segment_rect: QRectF,
        icon: QPixmap,
        color: QColor,
    ) -> None:
        icon_size = min(34, int(segment_rect.height() - 18))
        target_rect = QRectF(
            segment_rect.center().x() - (icon_size / 2),
            segment_rect.center().y() - (icon_size / 2),
            icon_size,
            icon_size,
        )
        painter.drawPixmap(
            target_rect.toRect(),
            self._tinted_icon(icon, color, icon_size),
        )

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

    def _refresh_tooltip(self) -> None:
        if self._hover_index < 0:
            self.setToolTip("")
            return
        self.setToolTip(self._options[self._hover_index][1])

    @staticmethod
    def _tinted_icon(icon: QPixmap, color: QColor, size: int) -> QPixmap:
        scaled_icon = icon.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        tinted_icon = QPixmap(scaled_icon.size())
        tinted_icon.fill(Qt.GlobalColor.transparent)

        painter = QPainter(tinted_icon)
        painter.drawPixmap(0, 0, scaled_icon)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(tinted_icon.rect(), color)
        painter.end()
        return tinted_icon
