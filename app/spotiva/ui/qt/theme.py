from __future__ import annotations

from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QApplication


def configure_app(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(build_stylesheet())


def build_stylesheet() -> str:
    return """
    QWidget {
        background: transparent;
        color: #f4f7f5;
    }
    QMainWindow {
        background: #000000;
    }
    QLabel#brandLabel {
        color: #ffffff;
        font-size: 25px;
        font-weight: 700;
        font-family: "Segoe UI Semibold";
    }
    QLabel#sectionTitle {
        color: #ffffff;
        font-size: 22px;
        font-weight: 700;
        font-family: "Segoe UI Semibold";
    }
    QLabel#settingsPageTitle {
        color: #ffffff;
        font-size: 34px;
        font-weight: 800;
        font-family: "Segoe UI Semibold";
    }
    QLabel#settingsSurfaceTitle {
        color: #f8fbf9;
        font-size: 18px;
        font-weight: 700;
        font-family: "Segoe UI Semibold";
    }
    QLabel#detailTitleLabel {
        color: #ffffff;
        font-size: 24px;
        font-weight: 800;
        font-family: "Segoe UI Semibold";
    }
    QLabel#detailArtistLabel {
        color: #dce8e0;
        font-size: 15px;
        font-weight: 600;
    }
    QLabel#detailMetaLabel {
        color: #8d9a93;
        font-size: 13px;
    }
    QLabel#downloadPathLabel {
        color: #7c8982;
        font-size: 12px;
    }
    QLabel#headlineLabel {
        color: #ffffff;
        font-size: 28px;
        font-weight: 700;
        font-family: "Segoe UI Semibold";
    }
    QLabel#bodyLabel {
        color: #8e9b93;
        font-size: 13px;
    }
    QLabel#captionLabel {
        color: #6f7a73;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    QLabel#statusLabel {
        color: #9ad8af;
        font-size: 12px;
        font-weight: 600;
    }
    QLabel#cardTitle {
        font-size: 15px;
        font-weight: 700;
        color: #ffffff;
    }
    QLabel#cardSubtitle {
        color: #6f7a73;
        font-size: 12px;
    }
    QLabel#durationLabel {
        color: #73d594;
        font-size: 12px;
        font-weight: 700;
    }
    QFrame#shell {
        background: rgba(9, 11, 11, 0.82);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 24px;
    }
    QFrame#sidebar,
    QFrame#heroCard,
    QFrame#resultsCard,
    QFrame#detailCard,
    QFrame#emptyState {
        background: rgba(14, 17, 16, 0.74);
        border: 1px solid rgba(255, 255, 255, 0.04);
        border-radius: 22px;
    }
    QFrame#trackCard {
        background: rgba(18, 20, 19, 0.76);
        border: 1px solid rgba(255, 255, 255, 0.028);
        border-radius: 18px;
    }
    QFrame#trackCard:hover {
        background: rgba(22, 25, 24, 0.8);
        border: 1px solid rgba(255, 255, 255, 0.05);
    }
    QFrame#trackCard[active="true"] {
        background: rgba(24, 30, 27, 0.84);
        border: 1px solid rgba(255, 255, 255, 0.08);
    }
    QFrame#artworkFrame {
        background: transparent;
        border: none;
    }
    QLabel#artworkLabel {
        background: rgba(18, 20, 19, 0.8);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 22px;
        color: #7f8b84;
        font-size: 13px;
    }
    QFrame#actionSurface {
        background: rgba(16, 19, 18, 0.82);
        border: 1px solid rgba(255, 255, 255, 0.045);
        border-radius: 22px;
    }
    QFrame#trackAccent {
        background: rgba(45, 216, 112, 0.82);
        border: none;
        border-radius: 2px;
    }
    QFrame#accentLine {
        background: rgba(45, 216, 112, 0.82);
        border: none;
        border-radius: 2px;
    }
    QLineEdit {
        background: rgba(10, 12, 11, 0.9);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 15px;
        padding: 14px 16px;
        color: #f8fbf9;
        selection-background-color: #2dd870;
        font-size: 14px;
    }
    QLineEdit:focus {
        background: rgba(14, 18, 16, 0.92);
        border: 1px solid rgba(45, 216, 112, 0.28);
    }
    QComboBox {
        background: rgba(10, 12, 11, 0.9);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 15px;
        padding: 12px 14px;
        color: #f8fbf9;
        font-size: 13px;
        font-weight: 600;
    }
    QComboBox:focus {
        background: rgba(14, 18, 16, 0.92);
        border: 1px solid rgba(45, 216, 112, 0.28);
    }
    QComboBox::drop-down {
        border: none;
        width: 26px;
    }
    QComboBox QAbstractItemView {
        background: rgba(14, 17, 16, 0.96);
        border: 1px solid rgba(255, 255, 255, 0.06);
        color: #f4f7f5;
        selection-background-color: rgba(45, 216, 112, 0.26);
        selection-color: #ffffff;
        outline: 0;
    }
    QToolButton#menuButton {
        background: rgba(16, 18, 17, 0.82);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 14px;
        padding: 0;
        min-width: 44px;
        max-width: 44px;
        min-height: 44px;
        max-height: 44px;
    }
    QToolButton#menuButton:hover {
        background: rgba(20, 24, 22, 0.82);
        border: 1px solid rgba(255, 255, 255, 0.08);
    }
    QToolButton#menuButton:pressed {
        background: rgba(24, 28, 26, 0.88);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    QFrame#drawerScrim {
        background: rgba(4, 8, 6, 0.52);
    }
    QFrame#navigationDrawer {
        background: rgba(11, 15, 13, 0.98);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 24px;
    }
    QFrame#settingsSurface {
        background: qlineargradient(
            x1: 0,
            y1: 0,
            x2: 1,
            y2: 1,
            stop: 0 rgba(16, 21, 19, 0.96),
            stop: 1 rgba(10, 13, 12, 0.94)
        );
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 28px;
    }
    QFrame#sourceSwitcher {
        background: rgba(9, 11, 10, 0.96);
        border: 1px solid rgba(255, 255, 255, 0.04);
        border-radius: 22px;
    }
    QFrame#sourceSwitcherOption {
        background: transparent;
        border: none;
        border-radius: 18px;
        min-height: 54px;
    }
    QFrame#sourceSwitcherOption[hovered="true"] {
        background: rgba(255, 255, 255, 0.03);
    }
    QFrame#sourceSwitcherOptionFill {
        background: qlineargradient(
            x1: 0,
            y1: 0,
            x2: 1,
            y2: 1,
            stop: 0 rgba(54, 228, 125, 0.96),
            stop: 1 rgba(120, 247, 175, 0.9)
        );
        border: none;
        border-radius: 18px;
    }
    QFrame#drawerNavItem {
        background: transparent;
        border: 1px solid transparent;
        border-radius: 16px;
    }
    QFrame#drawerNavItem:hover {
        background: rgba(19, 23, 21, 0.56);
        border: 1px solid rgba(255, 255, 255, 0.025);
    }
    QFrame#drawerNavItem[active="true"] {
        background: rgba(21, 27, 24, 0.72);
        border: 1px solid rgba(45, 216, 112, 0.12);
    }
    QFrame#drawerNavAccent {
        background: rgba(45, 216, 112, 0.86);
        border: none;
        border-radius: 2px;
    }
    QPushButton {
        border: none;
        border-radius: 15px;
        padding: 12px 18px;
        font-size: 13px;
        font-weight: 700;
        font-family: "Segoe UI Semibold";
    }
    QPushButton#primaryButton {
        background: #2dd870;
        color: #041109;
    }
    QPushButton#primaryButton:hover {
        background: #46de82;
    }
    QPushButton#primaryButton:pressed {
        background: #28c666;
    }
    QPushButton#secondaryButton {
        background: rgba(16, 18, 17, 0.78);
        color: #eff7f2;
        border: 1px solid rgba(255, 255, 255, 0.05);
    }
    QPushButton#secondaryButton:hover {
        background: rgba(20, 24, 22, 0.82);
        border: 1px solid rgba(255, 255, 255, 0.08);
    }
    QPushButton#secondaryButton:pressed {
        background: rgba(24, 28, 26, 0.88);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    QLabel#sourceSwitcherLabel {
        color: rgba(244, 247, 245, 0.74);
        font-size: 15px;
        font-weight: 700;
        font-family: "Segoe UI Semibold";
    }
    QFrame#sourceSwitcherOption[hovered="true"] QLabel#sourceSwitcherLabel {
        color: #ffffff;
    }
    QFrame#sourceSwitcherOption[active="true"] QLabel#sourceSwitcherLabel {
        color: #041109;
    }
    QToolButton#iconButton {
        background: rgba(16, 18, 17, 0.78);
        color: #eff7f2;
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 15px;
        padding: 10px;
        min-width: 44px;
        min-height: 44px;
    }
    QToolButton#iconButton:hover {
        background: rgba(20, 24, 22, 0.82);
        border: 1px solid rgba(255, 255, 255, 0.08);
    }
    QToolButton#iconButton:pressed {
        background: rgba(24, 28, 26, 0.88);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    QPushButton:disabled {
        background: rgba(17, 17, 17, 0.99);
        color: #55615a;
    }
    QToolButton#iconButton:disabled {
        background: rgba(17, 17, 17, 0.99);
        color: #55615a;
        border: 1px solid rgba(255, 255, 255, 0.04);
    }
    QScrollArea {
        border: none;
        background: transparent;
    }
    QScrollBar:vertical {
        width: 9px;
        margin: 8px 0;
        background: transparent;
    }
    QScrollBar::handle:vertical {
        border-radius: 4px;
        background: rgba(45, 216, 112, 0.24);
        min-height: 30px;
    }
    QSplitter::handle {
        background: transparent;
    }
    """


def background_colors() -> tuple[QColor, QColor, QColor]:
    return QColor("#09100d"), QColor("#121816"), QColor("#1d2320")
