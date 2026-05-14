from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from spotiva.app.bootstrap import build_controller
from spotiva.core.runtime import ensure_ffmpeg_on_path
from spotiva.core.state import AppState
from spotiva.ui.qt.main_window import MainWindow
from spotiva.ui.qt.theme import configure_app


_WINDOWS_APP_ID = "SpotiVa.Desktop"
_APP_ICON_PATH = Path(__file__).resolve().parent / "ui" / "qt" / "assets" / "app_icon.ico"


def _configure_windows_identity() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            _WINDOWS_APP_ID
        )
    except (AttributeError, OSError):
        return


def _configure_app_icon(app: QApplication) -> None:
    if not _APP_ICON_PATH.exists():
        return
    app.setWindowIcon(QIcon(str(_APP_ICON_PATH)))


def run() -> int:
    state = AppState()
    ensure_ffmpeg_on_path()
    _configure_windows_identity()
    app = QApplication(sys.argv)
    _configure_app_icon(app)
    configure_app(app)

    controller = build_controller(state)
    window = MainWindow(controller=controller, request_timeout=state.request_timeout)
    window.setWindowIcon(app.windowIcon())
    window.show()
    return app.exec()
