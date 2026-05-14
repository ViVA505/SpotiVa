from __future__ import annotations

import re
from pathlib import Path

from spotiva.domain.entities.track import Track


def build_unique_file_path(target_directory: Path, track: Track) -> Path:
    base_name = _sanitize_filename(f"{track.artist_line()} - {track.name}")
    candidate = target_directory / f"{base_name}.mp3"
    suffix = 1
    while candidate.exists():
        candidate = target_directory / f"{base_name} ({suffix}).mp3"
        suffix += 1
    return candidate


def build_unique_directory_path(target_directory: Path, track: Track) -> Path:
    base_name = _sanitize_filename(f"{track.artist_line()} - {track.name}")
    candidate = target_directory / base_name
    suffix = 1
    while candidate.exists():
        candidate = target_directory / f"{base_name} ({suffix})"
        suffix += 1
    return candidate


def cleanup_attempt_outputs(
    target_directory: Path,
    existing_files: set[Path],
) -> None:
    current_files = snapshot_files(target_directory)
    for candidate in current_files - existing_files:
        candidate.unlink(missing_ok=True)


def snapshot_files(target_directory: Path) -> set[Path]:
    return {
        candidate.resolve()
        for candidate in target_directory.iterdir()
        if candidate.is_file()
    }


def resolve_downloaded_file_path(
    expected_file_path: Path,
    existing_files: set[Path],
) -> Path | None:
    if expected_file_path.exists():
        return expected_file_path

    current_files = snapshot_files(expected_file_path.parent)
    new_files = current_files - existing_files
    new_mp3_files = [
        candidate
        for candidate in new_files
        if candidate.suffix.casefold() == ".mp3"
    ]
    if len(new_mp3_files) == 1:
        return new_mp3_files[0]
    if new_mp3_files:
        return max(new_mp3_files, key=lambda candidate: candidate.stat().st_mtime)
    return None


def normalize_downloaded_file_name(
    actual_file_path: Path,
    expected_file_path: Path,
) -> Path:
    if actual_file_path == expected_file_path:
        return expected_file_path
    if expected_file_path.exists():
        return expected_file_path
    actual_file_path.replace(expected_file_path)
    return expected_file_path


def _sanitize_filename(value: str) -> str:
    normalized = re.sub(r'[<>:"/\\\\|?*]+', " ", value)
    normalized = re.sub(r"\s+", " ", normalized).strip(" .")
    return normalized or "SpotiVa Track"
