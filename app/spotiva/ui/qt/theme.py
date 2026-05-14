from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QApplication


_STYLE_DIR = Path(__file__).resolve().parent / "styles"
_STYLE_FILES = (
    "base.qss",
    "labels.qss",
    "surfaces.qss",
    "inputs.qss",
    "navigation.qss",
    "settings.qss",
    "buttons.qss",
    "scrolling.qss",
)


def configure_app(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(build_stylesheet())


@lru_cache(maxsize=1)
def build_stylesheet() -> str:
    return "\n\n".join(_read_style_file(file_name) for file_name in _STYLE_FILES)


def background_colors() -> tuple[QColor, QColor, QColor]:
    return QColor("#09100d"), QColor("#121816"), QColor("#1d2320")


def _read_style_file(file_name: str) -> str:
    path = _STYLE_DIR / file_name
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"Unable to load Qt stylesheet file: {path}") from exc
