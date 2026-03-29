from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path

import yt_dlp

from spotiva.core.exceptions import DownloadError
from spotiva.core.state import AppState
from spotiva.domain.entities.track import Track
from spotiva.domain.repos.audio_repo import AudioAssetRepository
from spotiva.infra.downloader.audio_tagger import Mp3AudioTagger


class YtDlpAssetRepository(AudioAssetRepository):
    def __init__(self, state: AppState, tagger: Mp3AudioTagger) -> None:
        self._state = state
        self._tagger = tagger

    def download_track(self, track: Track, progress_callback: Callable[[int, int], None] | None = None) -> str:
        target_directory = Path(self._state.download_directory)
        target_directory.mkdir(parents=True, exist_ok=True)

        file_path = self._build_unique_file_path(target_directory, track)
        download_target = self._build_download_target(track)
        progress_hook = _YtDlpProgressHook(progress_callback)

        ydl_options = {
            "format": "bestaudio/best",
            "outtmpl": str(file_path.with_suffix(".%(ext)s")),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "windowsfilenames": True,
            "concurrent_fragment_downloads": 4,
            "fragment_retries": 3,
            "file_access_retries": 3,
            "retries": 3,
            "progress_hooks": [progress_hook],
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                ydl.download([download_target])
        except Exception as error:
            self._cleanup_generated_files(file_path)
            raise self._wrap_download_error(error) from error

        if not file_path.exists():
            raise DownloadError("MP3 file was not created after the download finished.")

        self._tagger.apply(file_path, track)

        if progress_callback:
            final_size = file_path.stat().st_size
            progress_callback(final_size, final_size)

        return str(file_path)

    def _build_download_target(self, track: Track) -> str:
        if track.download_url:
            return track.download_url

        search_query = " ".join(part for part in (track.artist_line(), track.name) if part).strip()
        if not search_query:
            raise DownloadError("The selected track does not contain enough metadata to search for audio.")
        return f"ytsearch1:{search_query} official audio"

    def _build_unique_file_path(self, target_directory: Path, track: Track) -> Path:
        base_name = self._sanitize_filename(f"{track.artist_line()} - {track.name}")
        candidate = target_directory / f"{base_name}.mp3"
        suffix = 1
        while candidate.exists():
            candidate = target_directory / f"{base_name} ({suffix}).mp3"
            suffix += 1
        return candidate

    def _cleanup_generated_files(self, file_path: Path) -> None:
        stem = file_path.stem
        for candidate in file_path.parent.iterdir():
            if not candidate.is_file():
                continue
            name = candidate.name
            if name == file_path.name or name.startswith(f"{stem}."):
                candidate.unlink(missing_ok=True)

    def _wrap_download_error(self, error: Exception) -> DownloadError:
        message = str(error).strip() or error.__class__.__name__
        if "ffmpeg" in message.lower():
            return DownloadError("FFmpeg is required to convert downloads to MP3. Install FFmpeg and add it to PATH.")
        return DownloadError(f"Could not download the selected track: {message}")

    @staticmethod
    def _sanitize_filename(value: str) -> str:
        normalized = re.sub(r'[<>:"/\\\\|?*]+', " ", value)
        normalized = re.sub(r"\s+", " ", normalized).strip(" .")
        return normalized or "SpotiVa Track"


class _YtDlpProgressHook:
    def __init__(self, callback: Callable[[int, int], None] | None) -> None:
        self._callback = callback

    def __call__(self, payload: Mapping[str, object]) -> None:
        if not self._callback:
            return

        status = str(payload.get("status", "")).strip().lower()
        if status not in {"downloading", "finished"}:
            return

        downloaded = self._safe_int(payload.get("downloaded_bytes"))
        total = self._safe_int(payload.get("total_bytes") or payload.get("total_bytes_estimate"))

        if status == "finished":
            resolved_total = total or downloaded
            self._callback(resolved_total, resolved_total)
            return

        self._callback(downloaded, total)

    @staticmethod
    def _safe_int(value: object) -> int:
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0
