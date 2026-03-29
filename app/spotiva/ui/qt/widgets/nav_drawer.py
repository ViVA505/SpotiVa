from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QFrame, QGraphicsOpacityEffect, QLabel, QHBoxLayout, QVBoxLayout, QWidget


class DrawerScrim(QFrame):
    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.clicked.emit()


class DrawerNavItem(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, value: str, title: str, parent=None) -> None:
        super().__init__(parent)
        self._value = value
        self.setObjectName("drawerNavItem")
        self.setProperty("active", "false")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        self._accent = QFrame(self)
        self._accent.setObjectName("drawerNavAccent")
        self._accent.setFixedWidth(3)
        self._accent.setMinimumHeight(26)
        self._accent.setVisible(False)
        layout.addWidget(self._accent)

        self._title = QLabel(title, self)
        self._title.setObjectName("cardTitle")
        layout.addWidget(self._title, 1)

    def set_active(self, is_active: bool) -> None:
        self._accent.setVisible(is_active)
        self.setProperty("active", "true" if is_active else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.clicked.emit(self._value)


class NavigationDrawer(QWidget):
    page_requested = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("drawerOverlay")
        self.hide()

        self._is_open = False
        self._sheet_width = 264
        self._sheet_margin = 18

        self._scrim = DrawerScrim(self)
        self._scrim.setObjectName("drawerScrim")
        self._scrim.clicked.connect(self.close_animated)

        self._scrim_opacity = QGraphicsOpacityEffect(self._scrim)
        self._scrim.setGraphicsEffect(self._scrim_opacity)
        self._scrim_opacity.setOpacity(0.0)

        self._sheet = QFrame(self)
        self._sheet.setObjectName("navigationDrawer")

        sheet_layout = QVBoxLayout(self._sheet)
        sheet_layout.setContentsMargins(18, 22, 18, 22)
        sheet_layout.setSpacing(8)

        self._search_button = self._build_item(
            value="search",
            title="Search",
        )
        self._search_button.clicked.connect(self._emit_page)
        sheet_layout.addWidget(self._search_button)

        self._settings_button = self._build_item(
            value="settings",
            title="Settings",
        )
        self._settings_button.clicked.connect(self._emit_page)
        sheet_layout.addWidget(self._settings_button)
        sheet_layout.addStretch()

        self._sheet_animation = QPropertyAnimation(self._sheet, b"geometry", self)
        self._sheet_animation.setDuration(220)
        self._sheet_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._scrim_animation = QPropertyAnimation(self._scrim_opacity, b"opacity", self)
        self._scrim_animation.setDuration(220)
        self._scrim_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._scrim_animation.finished.connect(self._handle_animation_finished)

    def set_current_page(self, value: str) -> None:
        self._search_button.set_active(value == "search")
        self._settings_button.set_active(value == "settings")

    def toggle(self) -> None:
        if self._is_open:
            self.close_animated()
            return
        self.open_animated()

    def open_animated(self) -> None:
        if self.parentWidget():
            self.setGeometry(self.parentWidget().rect())
        self._sync_child_geometry()

        self._is_open = True
        self.show()
        self.raise_()

        self._sheet_animation.stop()
        self._sheet_animation.setStartValue(self._closed_sheet_rect())
        self._sheet_animation.setEndValue(self._open_sheet_rect())

        self._scrim_animation.stop()
        self._scrim_animation.setStartValue(self._scrim_opacity.opacity())
        self._scrim_animation.setEndValue(1.0)

        self._sheet_animation.start()
        self._scrim_animation.start()

    def close_animated(self) -> None:
        if not self.isVisible():
            return

        self._is_open = False
        self._sheet_animation.stop()
        self._sheet_animation.setStartValue(self._sheet.geometry())
        self._sheet_animation.setEndValue(self._closed_sheet_rect())

        self._scrim_animation.stop()
        self._scrim_animation.setStartValue(self._scrim_opacity.opacity())
        self._scrim_animation.setEndValue(0.0)

        self._sheet_animation.start()
        self._scrim_animation.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_child_geometry()
        if self.isVisible():
            target_rect = self._open_sheet_rect() if self._is_open else self._closed_sheet_rect()
            self._sheet.setGeometry(target_rect)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_animated()
            event.accept()
            return
        super().keyPressEvent(event)

    def _build_item(self, value: str, title: str) -> DrawerNavItem:
        return DrawerNavItem(value=value, title=title, parent=self._sheet)

    def _emit_page(self, value: str) -> None:
        self.page_requested.emit(value)
        self.close_animated()

    def _sync_child_geometry(self) -> None:
        self._scrim.setGeometry(self.rect())

    def _open_sheet_rect(self) -> QRect:
        available_height = max(280, self.height() - (self._sheet_margin * 2))
        return QRect(self._sheet_margin, self._sheet_margin, self._sheet_width, available_height)

    def _closed_sheet_rect(self) -> QRect:
        open_rect = self._open_sheet_rect()
        return QRect(-open_rect.width(), open_rect.y(), open_rect.width(), open_rect.height())

    def _handle_animation_finished(self) -> None:
        if not self._is_open and self._scrim_opacity.opacity() <= 0.01:
            self.hide()
