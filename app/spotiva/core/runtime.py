from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


_FFMPEG_ENV_VAR = "SPOTIVA_FFMPEG_DIR"


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def resolve_ffmpeg_location() -> str | None:
    for candidate in _iter_ffmpeg_directories():
        if _contains_ffmpeg_binary(candidate):
            return str(candidate)
    return None


def ensure_ffmpeg_on_path() -> str | None:
    ffmpeg_location = resolve_ffmpeg_location()
    if not ffmpeg_location:
        return None

    current_path = os.environ.get("PATH", "")
    path_entries = {
        entry.casefold()
        for entry in current_path.split(os.pathsep)
        if entry.strip()
    }
    if ffmpeg_location.casefold() not in path_entries:
        if current_path:
            os.environ["PATH"] = f"{ffmpeg_location}{os.pathsep}{current_path}"
        else:
            os.environ["PATH"] = ffmpeg_location
    return ffmpeg_location


def _iter_ffmpeg_directories() -> list[Path]:
    candidates: list[Path] = []
    env_path = os.environ.get(_FFMPEG_ENV_VAR, "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())

    _append_embedded_ffmpeg_candidates(candidates, application_root() / "ffmpeg")

    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        _append_embedded_ffmpeg_candidates(candidates, Path(bundle_root) / "ffmpeg")

    ffmpeg_binary = shutil.which("ffmpeg")
    if ffmpeg_binary:
        candidates.append(Path(ffmpeg_binary).resolve().parent)

    unique_candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate.resolve(strict=False)).casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_candidates.append(candidate)
    return unique_candidates


def _append_embedded_ffmpeg_candidates(candidates: list[Path], ffmpeg_root: Path) -> None:
    candidates.extend([
        ffmpeg_root / "bin",
        ffmpeg_root,
    ])
    if not ffmpeg_root.is_dir():
        return

    ffmpeg_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    for binary_path in ffmpeg_root.rglob(ffmpeg_name):
        candidates.append(binary_path.parent)


def _contains_ffmpeg_binary(directory: Path) -> bool:
    ffmpeg_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    return directory.is_dir() and (directory / ffmpeg_name).exists()
