from __future__ import annotations

from pathlib import Path


_ASSET_DIR = Path(__file__).resolve().parent / "assets"


def qt_asset_path(file_name: str) -> Path:
    return _ASSET_DIR / file_name
