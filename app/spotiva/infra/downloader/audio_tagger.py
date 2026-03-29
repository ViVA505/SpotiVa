from __future__ import annotations

import io
from pathlib import Path

import requests
from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, error as id3_error
from mutagen.mp3 import MP3
from PIL import Image

from spotiva.core.constants import DEFAULT_REQUEST_TIMEOUT
from spotiva.core.exceptions import DownloadError
from spotiva.domain.entities.track import Track


class Mp3AudioTagger:
    def __init__(self, request_timeout: int = DEFAULT_REQUEST_TIMEOUT) -> None:
        self._timeout = max(5, int(request_timeout))
        self._session = requests.Session()

    def apply(self, file_path: Path, track: Track) -> None:
        try:
            audio = MP3(file_path, ID3=ID3)
        except Exception as error:
            raise DownloadError(f"Could not open the downloaded MP3 for tagging: {error}") from error

        try:
            audio.add_tags()
        except id3_error:
            pass

        if audio.tags is None:
            raise DownloadError("Could not initialize ID3 tags for the downloaded MP3.")

        for frame_name in ("TPE1", "TIT2", "TALB", "APIC"):
            audio.tags.delall(frame_name)

        audio.tags.add(TPE1(encoding=3, text=track.artist_line()))
        audio.tags.add(TIT2(encoding=3, text=track.name))
        audio.tags.add(TALB(encoding=3, text=track.album.name or "Single"))

        artwork_frame = self._build_artwork_frame(track.best_image_url())
        if artwork_frame:
            audio.tags.add(artwork_frame)

        try:
            audio.save(v2_version=3)
        except Exception as error:
            raise DownloadError(f"Could not save MP3 tags: {error}") from error

    def _build_artwork_frame(self, image_url: str) -> APIC | None:
        if not image_url:
            return None

        try:
            response = self._session.get(
                image_url,
                timeout=self._timeout,
                headers={"User-Agent": "SpotiVa/1.0"},
            )
            response.raise_for_status()
        except requests.RequestException:
            return None

        mime_type = str(response.headers.get("content-type", "image/jpeg")).split(";")[0].strip().lower()
        image_bytes = response.content

        if mime_type == "image/webp" or image_url.lower().endswith(".webp"):
            try:
                image_bytes = self._convert_webp_to_jpeg(image_bytes)
                mime_type = "image/jpeg"
            except Exception:
                return None

        return APIC(
            encoding=3,
            mime=mime_type or "image/jpeg",
            type=3,
            desc="Cover",
            data=image_bytes,
        )

    @staticmethod
    def _convert_webp_to_jpeg(image_bytes: bytes) -> bytes:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        return buffer.getvalue()
