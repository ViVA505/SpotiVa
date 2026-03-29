from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QFrame


class ResultsLoadingState(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("resultsLoadingState")
        self._phase = -0.35
        self._animation = QPropertyAnimation(self, b"phase", self)
        self._animation.setDuration(1080)
        self._animation.setLoopCount(-1)
        self._animation.setStartValue(-0.35)
        self._animation.setEndValue(1.15)
        self._animation.setEasingCurve(QEasingCurve.Type.Linear)

    def start(self) -> None:
        if self._animation.state() != QPropertyAnimation.State.Running:
            self._animation.start()

    def stop(self) -> None:
        self._animation.stop()
        self._phase = -0.35
        self.update()

    def get_phase(self) -> float:
        return self._phase

    def set_phase(self, value: float) -> None:
        self._phase = value
        self.update()

    phase = pyqtProperty(float, fget=get_phase, fset=set_phase)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        card_count = 4
        spacing = 12.0
        card_height = 70.0
        top = 6.0
        width = max(220.0, self.width() - 2.0)

        for index in range(card_count):
            y = top + index * (card_height + spacing)
            card_rect = QRectF(0.5, y, width - 1.0, card_height)
            self._draw_card(painter, card_rect)

    def _draw_card(self, painter: QPainter, card_rect: QRectF) -> None:
        border_color = QColor(255, 255, 255, 8)
        base_fill = QColor(18, 20, 19, 194)
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(base_fill)
        painter.drawRoundedRect(card_rect, 18, 18)

        accent_rect = QRectF(card_rect.left() + 14, card_rect.top() + 14, 4, card_rect.height() - 28)
        badge_rect = QRectF(card_rect.left() + 30, card_rect.top() + 14, 44, 44)
        title_rect = QRectF(card_rect.left() + 90, card_rect.top() + 16, card_rect.width() * 0.36, 14)
        subtitle_rect = QRectF(card_rect.left() + 90, card_rect.top() + 38, card_rect.width() * 0.24, 10)
        duration_rect = QRectF(card_rect.right() - 68, card_rect.top() + 18, 38, 12)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(45, 216, 112, 46))
        painter.drawRoundedRect(accent_rect, 2, 2)

        skeleton_fill = QColor(255, 255, 255, 12)
        painter.setBrush(skeleton_fill)
        painter.drawRoundedRect(badge_rect, 14, 14)
        painter.drawRoundedRect(title_rect, 7, 7)
        painter.drawRoundedRect(subtitle_rect, 5, 5)
        painter.drawRoundedRect(duration_rect, 6, 6)

        shimmer_width = card_rect.width() * 0.34
        shimmer_left = card_rect.left() + (card_rect.width() * self._phase)
        shimmer_rect = QRectF(shimmer_left, card_rect.top(), shimmer_width, card_rect.height())

        gradient = QLinearGradient(shimmer_rect.left(), shimmer_rect.top(), shimmer_rect.right(), shimmer_rect.top())
        gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
        gradient.setColorAt(0.5, QColor(255, 255, 255, 26))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 0))

        clip_path = QPainterPath()
        clip_path.addRoundedRect(card_rect, 18, 18)
        painter.save()
        painter.setClipPath(clip_path)
        painter.fillRect(shimmer_rect, gradient)
        painter.restore()
