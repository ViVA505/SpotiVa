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
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QWidget

from spotiva.core.constants import SEARCH_MODE_CATALOG, SEARCH_MODE_LYRICS
from spotiva.ui.qt.asset_paths import qt_asset_path


class SearchModeTabs(QWidget):
    selected = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._options = [
            (SEARCH_MODE_CATALOG, "Music"),
            (SEARCH_MODE_LYRICS, "Lyrics"),
        ]
        self._icons = self._load_icons()
        self._current_index = 0
        self._hover_index = -1
        self._indicator_x = 0.0
        self._indicator_width = 0.0
        self._gap = 8.0
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMouseTracking(True)
        self.setFixedSize(self.sizeHint())

        self._indicator_x_animation = QPropertyAnimation(self, b"indicatorX", self)
        self._indicator_x_animation.setDuration(220)
        self._indicator_x_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._indicator_width_animation = QPropertyAnimation(
            self,
            b"indicatorWidth",
            self,
        )
        self._indicator_width_animation.setDuration(220)
        self._indicator_width_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        QTimer.singleShot(0, self._sync_indicator)

    def get_indicator_x(self) -> float:
        return self._indicator_x

    def set_indicator_x(self, value: float) -> None:
        self._indicator_x = value
        self.update()

    indicatorX = pyqtProperty(float, fget=get_indicator_x, fset=set_indicator_x)

    def get_indicator_width(self) -> float:
        return self._indicator_width

    def set_indicator_width(self, value: float) -> None:
        self._indicator_width = value
        self.update()

    indicatorWidth = pyqtProperty(
        float,
        fget=get_indicator_width,
        fset=set_indicator_width,
    )

    def value(self) -> str:
        return self._options[self._current_index][0]

    def set_value(self, value: str, animated: bool) -> None:
        for index, (option_value, _) in enumerate(self._options):
            if option_value != value:
                continue
            self._current_index = index
            target_rect = self._tab_rect(index)
            if animated and self.isVisible():
                self._animate_indicator(target_rect)
            else:
                self._indicator_x = target_rect.x()
                self._indicator_width = target_rect.width()
                self.update()
            return

    def sizeHint(self) -> QSize:
        widths = self._preferred_tab_widths()
        return QSize(int(sum(widths) + self._gap), 54)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_indicator()

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
        value = self._options[index][0]
        self.set_value(value, animated=True)
        self.selected.emit(value)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.62)

        baseline_y = self.height() - 2.0
        painter.setPen(QPen(QColor(255, 255, 255, 16), 1))
        painter.drawLine(0, int(baseline_y), self.width(), int(baseline_y))

        active_rect = QRectF(
            self._indicator_x,
            0.0,
            self._indicator_width,
            self.height() - 6.0,
        )
        if active_rect.width() > 0:
            painter.setPen(QPen(QColor(45, 216, 112, 58), 1))
            painter.setBrush(QColor(20, 28, 24, 232))
            painter.drawRoundedRect(active_rect, 15, 15)

            accent_rect = QRectF(
                active_rect.left() + 13.0,
                self.height() - 4.0,
                max(0.0, active_rect.width() - 26.0),
                3.0,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(45, 216, 112, 225))
            painter.drawRoundedRect(accent_rect, 1.5, 1.5)

        for index, (_, label) in enumerate(self._options):
            rect = self._tab_rect(index)
            is_active = index == self._current_index
            is_hovered = index == self._hover_index and not is_active
            if is_hovered:
                painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
                painter.setBrush(QColor(255, 255, 255, 11))
                painter.drawRoundedRect(rect, 15, 15)

            self._draw_tab_content(painter, rect, index, label, is_active)

    def _draw_tab_content(
        self,
        painter: QPainter,
        rect: QRectF,
        index: int,
        label: str,
        is_active: bool,
    ) -> None:
        icon_rect = QRectF(rect.left() + 13.0, rect.top() + 11.0, 28.0, 28.0)
        icon_background = (
            QColor(45, 216, 112, 235)
            if is_active
            else QColor(255, 255, 255, 14)
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(icon_background)
        painter.drawRoundedRect(icon_rect, 9, 9)

        icon_key = self._options[index][0]
        icon_state = "active" if is_active else "inactive"
        icon = self._icons.get((icon_key, icon_state), QPixmap())
        if not icon.isNull():
            painter.drawPixmap(icon_rect.toRect(), icon)

        label_font = QFont("Segoe UI Semibold", 10)
        painter.setFont(label_font)
        painter.setPen(QColor(247, 251, 248) if is_active else QColor(157, 169, 162))

        text_rect = QRectF(
            icon_rect.right() + 10.0,
            rect.top(),
            max(0.0, rect.right() - icon_rect.right() - 20.0),
            rect.height(),
        )
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, label)

    def _animate_indicator(self, target_rect: QRectF) -> None:
        self._indicator_x_animation.stop()
        self._indicator_width_animation.stop()

        self._indicator_x_animation.setStartValue(self._indicator_x)
        self._indicator_x_animation.setEndValue(target_rect.x())
        self._indicator_width_animation.setStartValue(self._indicator_width)
        self._indicator_width_animation.setEndValue(target_rect.width())

        self._indicator_x_animation.start()
        self._indicator_width_animation.start()

    def _tab_rect(self, index: int) -> QRectF:
        widths = self._tab_widths()
        x = sum(widths[:index]) + (self._gap * index)
        return QRectF(x, 0.0, widths[index], self.height() - 6.0)

    def _tab_widths(self) -> list[float]:
        preferred_widths = self._preferred_tab_widths()
        available_width = max(sum(preferred_widths) + self._gap, float(self.width()))
        remaining_width = max(0.0, available_width - self._gap)
        preferred_total = max(1.0, sum(preferred_widths))
        first_width = remaining_width * (preferred_widths[0] / preferred_total)
        second_width = remaining_width - first_width
        return [first_width, second_width]

    def _preferred_tab_widths(self) -> list[float]:
        label_font = QFont("Segoe UI Semibold", 10)
        metrics = QFontMetrics(label_font)
        return [
            max(112.0, float(metrics.horizontalAdvance(label) + 58))
            for _, label in self._options
        ]

    def _index_at(self, x: float, y: float) -> int:
        for index in range(len(self._options)):
            if self._tab_rect(index).contains(float(x), float(y)):
                return index
        return -1

    def _sync_indicator(self) -> None:
        self._indicator_x_animation.stop()
        self._indicator_width_animation.stop()
        current_rect = self._tab_rect(self._current_index)
        self._indicator_x = current_rect.x()
        self._indicator_width = current_rect.width()
        self.update()

    def _load_icons(self) -> dict[tuple[str, str], QPixmap]:
        return {
            (SEARCH_MODE_CATALOG, "active"): QPixmap(
                str(qt_asset_path("tab_music_active.png"))
            ),
            (SEARCH_MODE_CATALOG, "inactive"): QPixmap(
                str(qt_asset_path("tab_music_inactive.png"))
            ),
            (SEARCH_MODE_LYRICS, "active"): QPixmap(
                str(qt_asset_path("tab_lyrics_active.png"))
            ),
            (SEARCH_MODE_LYRICS, "inactive"): QPixmap(
                str(qt_asset_path("tab_lyrics_inactive.png"))
            ),
        }
