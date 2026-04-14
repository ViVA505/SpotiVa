from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import replace
from difflib import SequenceMatcher
from pathlib import Path

import yt_dlp
from mutagen.mp3 import MP3

from spotiva.core.exceptions import DownloadError
from spotiva.core.state import AppState
from spotiva.domain.entities.track import Album, Artist, Track, TrackImage
from spotiva.domain.repos.audio_repo import AudioAssetRepository
from spotiva.infra.downloader.audio_tagger import Mp3AudioTagger
from spotiva.infra.downloader.models import DownloadSearchResult
from spotiva.infra.downloader.track_mapper import DownloadTrackMapper


class YtDlpAssetRepository(AudioAssetRepository):
    _SPACE_RE = re.compile(r"\s+")
    _PAREN_RE = re.compile(r"\s*[\[(][^)\]]*[\])]\s*")
    _DERIVATIVE_RE = re.compile(
        r"\b(?:cover|РєР°РІРµСЂ|remix|bootleg|edit|nightcore|sped up|slowed)\b",
        re.IGNORECASE,
    )

    _SHORT_FORM_RE = re.compile(
        r"\b(?:snippet|preview|teaser|demo|sample|excerpt|clip)\b",
        re.IGNORECASE,
    )

    def __init__(self, state: AppState, tagger: Mp3AudioTagger) -> None:
        self._state = state
        self._tagger = tagger
        self._download_mapper = DownloadTrackMapper()

    def download_track(
        self,
        track: Track,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> str:
        target_directory = Path(self._state.download_directory)
        target_directory.mkdir(parents=True, exist_ok=True)

        if track.is_album_result():
            return self._download_album(track, target_directory, progress_callback)
        return self._download_single_track(track, target_directory, progress_callback)

    def _download_album(
        self,
        album_track: Track,
        target_directory: Path,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> str:
        album_directory = self._build_unique_directory_path(
            target_directory,
            album_track,
        )
        album_directory.mkdir(parents=True, exist_ok=True)

        tracks = list(album_track.album_tracks)
        if not tracks:
            entries = self._extract_album_entries(album_track)
            tracks = self._build_album_tracks(album_track, entries)
        if not tracks:
            raise DownloadError(
                "Could not find downloadable tracks for the selected album."
            )

        total_tracks = len(tracks)
        completed_tracks = 0
        if progress_callback:
            progress_callback(0, total_tracks)

        for track in tracks:
            try:
                self._download_single_track(track, album_directory, None)
            except DownloadError:
                continue
            completed_tracks += 1
            if progress_callback:
                progress_callback(completed_tracks, total_tracks)

        if completed_tracks == 0:
            raise DownloadError(
                "Could not download any tracks from the selected album."
            )

        if progress_callback:
            progress_callback(total_tracks, total_tracks)
        return str(album_directory)

    def _download_single_track(
        self,
        track: Track,
        target_directory: Path,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> str:
        download_track = self._resolve_download_track(track)
        resolved_track = self._enrich_track_metadata(download_track)
        file_path = self._build_unique_file_path(target_directory, resolved_track)
        download_targets = self._build_download_targets(resolved_track)
        progress_hook = _YtDlpProgressHook(progress_callback)

        ydl_options = {
            "format": "bestaudio/best",
            "outtmpl": str(file_path.with_suffix(".%(ext)s")),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
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

        last_error: Exception | None = None
        download_completed = False
        for download_target in download_targets:
            existing_files = self._snapshot_files(target_directory)
            try:
                with yt_dlp.YoutubeDL(ydl_options) as ydl:
                    ydl.download([download_target])
            except Exception as error:
                last_error = error
                self._cleanup_attempt_outputs(target_directory, existing_files)
                continue

            resolved_file_path = self._resolve_downloaded_file_path(
                file_path,
                existing_files,
            )
            if resolved_file_path is None:
                continue

            if resolved_file_path != file_path:
                resolved_file_path = self._normalize_downloaded_file_name(
                    resolved_file_path,
                    file_path,
                )

            file_path = resolved_file_path
            if not self._is_downloaded_audio_compatible(
                requested_track=track,
                resolved_track=resolved_track,
                file_path=file_path,
            ):
                last_error = DownloadError(
                    "Downloaded audio did not match the expected track."
                )
                file_path.unlink(missing_ok=True)
                continue

            download_completed = True
            break

        if not download_completed:
            if last_error is None:
                raise DownloadError("Could not resolve a downloadable source.")
            raise self._wrap_download_error(last_error) from last_error

        self._tagger.apply(file_path, resolved_track)

        if progress_callback:
            final_size = file_path.stat().st_size
            progress_callback(final_size, final_size)

        return str(file_path)

    def _resolve_download_track(self, track: Track) -> Track:
        excluded_urls: set[str] = set()
        if track.download_url and self._is_reliable_direct_download_track(track):
            return track
        if track.download_url:
            excluded_urls.add(track.open_url().casefold())

        matched_track = self._resolve_best_download_match(track, excluded_urls)
        if matched_track is None or not matched_track.download_url:
            raise DownloadError(
                "Could not find a reliable audio match for the selected track."
            )

        resolved_name = track.name
        if self._needs_title_refresh(track):
            resolved_name = matched_track.name or track.name

        resolved_artists = track.artists
        if self._needs_artist_refresh(track) and matched_track.artists:
            resolved_artists = matched_track.artists

        resolved_album = track.album
        if not track.best_image_url() and matched_track.best_image_url():
            resolved_album = replace(track.album, images=matched_track.album.images)

        resolved_duration = track.duration_ms or matched_track.duration_ms
        return replace(
            track,
            name=resolved_name,
            artists=resolved_artists,
            album=resolved_album,
            duration_ms=resolved_duration,
            download_url=matched_track.download_url or matched_track.external_url,
        )

    def _extract_album_entries(self, album_track: Track) -> list[Mapping[str, object]]:
        album_url = (
            album_track.download_url
            or album_track.external_url
            or album_track.open_url()
        )
        if not album_url:
            raise DownloadError("The selected album does not contain a playlist URL.")

        source = self._guess_source(album_url)
        ydl_options = {
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
        }
        if source == "youtube":
            ydl_options["extract_flat"] = True

        try:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                payload = ydl.extract_info(album_url, download=False)
        except Exception as error:
            raise self._wrap_download_error(error) from error

        if not isinstance(payload, Mapping):
            return []

        entries = payload.get("entries")
        if not isinstance(entries, list):
            return []

        return [entry for entry in entries if isinstance(entry, Mapping)]

    def _build_album_tracks(
        self,
        album_track: Track,
        entries: list[Mapping[str, object]],
    ) -> list[Track]:
        album_name = album_track.name or album_track.album.name or "Album"
        album_images = album_track.album.images
        fallback_artist = album_track.primary_artist_name()
        source = self._guess_source(
            album_track.download_url
            or album_track.external_url
            or album_track.open_url()
        )

        tracks: list[Track] = []
        for index, entry in enumerate(entries, start=1):
            entry_url = self._resolve_entry_url(entry, source)
            if not entry_url:
                continue

            title = self._clean_text(entry.get("title"), f"Track {index}")
            artist_name = self._clean_text(
                entry.get("uploader") or entry.get("channel") or fallback_artist,
                fallback_artist or "Unknown Artist",
            ).removesuffix(" - Topic").strip() or "Unknown Artist"
            image_url = self._extract_image_url(entry.get("thumbnails"))
            track_images = [TrackImage(url=image_url)] if image_url else album_images
            track_id = f"{album_track.track_id}:track:{index}"

            tracks.append(
                Track(
                    track_id=track_id,
                    name=title,
                    artists=[Artist(name=artist_name)],
                    album=Album(
                        name=album_name,
                        images=track_images,
                        spotify_url=album_track.album.spotify_url,
                    ),
                    duration_ms=self._extract_duration_ms(entry.get("duration")),
                    spotify_url="",
                    external_url=entry_url,
                    download_url=entry_url,
                    source_label=album_track.source_label,
                    is_downloadable=True,
                )
            )
        return tracks

    def _enrich_track_metadata(self, track: Track) -> Track:
        if not self._needs_metadata_refresh(track):
            return track

        ydl_options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        info: Mapping[str, object] | None = None
        for download_target in self._build_download_targets(track):
            try:
                with yt_dlp.YoutubeDL(ydl_options) as ydl:
                    payload = ydl.extract_info(download_target, download=False)
            except Exception:
                continue
            info = self._resolve_track_payload(payload)
            if isinstance(info, Mapping):
                break

        if not isinstance(info, Mapping):
            return track

        resolved_name = track.name
        if self._needs_title_refresh(track):
            resolved_name = self._clean_text(
                info.get("title"),
                track.name or "Unknown Title",
            )

        resolved_artists = track.artists
        if self._needs_artist_refresh(track):
            artist_name = self._clean_text(
                info.get("artist") or info.get("uploader") or info.get("channel"),
                track.primary_artist_name(),
            ).removesuffix(" - Topic").strip()
            if artist_name:
                resolved_artists = [Artist(name=artist_name)]

        resolved_album = track.album
        image_url = self._extract_image_url(info.get("thumbnails"))
        if image_url and not track.best_image_url():
            resolved_album = replace(track.album, images=[TrackImage(url=image_url)])

        return replace(
            track,
            name=resolved_name,
            artists=resolved_artists,
            album=resolved_album,
        )

    def _build_download_targets(self, track: Track) -> list[str]:
        if track.download_url:
            return [track.download_url]

        search_query = " ".join(
            part for part in (track.artist_line(), track.name) if part
        ).strip()
        if not search_query:
            raise DownloadError(
                "The selected track does not contain enough metadata "
                "to search for audio."
            )

        preferred_source = self._state.title_search_source
        if preferred_source == "soundcloud":
            candidates = [
                f"scsearch5:{search_query}",
                f"ytsearch5:{search_query}",
                f"ytsearch5:{search_query} official audio",
            ]
        else:
            candidates = [
                f"ytsearch5:{search_query} official audio",
                f"ytsearch5:{search_query}",
                f"scsearch5:{search_query}",
            ]
        return self._unique_targets(candidates)

    def _resolve_best_download_match(
        self,
        track: Track,
        excluded_urls: set[str] | None = None,
    ) -> Track | None:
        requested_artist = track.artist_line().strip()
        query_variants = self._build_query_variants(track.name)
        source_order = self._download_source_order()
        best_match: Track | None = None
        best_score = 0.0
        normalized_excluded_urls = {
            value.casefold()
            for value in (excluded_urls or set())
            if value.strip()
        }

        for source in source_order:
            for query in query_variants:
                candidates = self._search_download_candidates(
                    query=query,
                    artist_name=requested_artist,
                    source=source,
                )
                for candidate in candidates:
                    if candidate.is_album_result() or not candidate.download_url:
                        continue
                    if candidate.open_url().casefold() in normalized_excluded_urls:
                        continue
                    match_score = self._build_candidate_match_score(
                        requested_track=track,
                        candidate_track=candidate,
                        source=source,
                        preferred_source=source_order[0],
                    )
                    if not self._is_reliable_download_match(
                        requested_track=track,
                        candidate_track=candidate,
                        score=match_score,
                    ):
                        continue
                    if match_score <= best_score:
                        continue
                    best_match = candidate
                    best_score = match_score
        return best_match

    def _search_download_candidates(
        self,
        query: str,
        artist_name: str,
        source: str,
    ) -> list[Track]:
        search_targets = self._build_search_targets(
            query=query,
            artist_name=artist_name,
            source=source,
        )
        ydl_options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "extract_flat": True,
            "ignoreerrors": True,
        }

        candidates: list[Track] = []
        seen_urls: set[str] = set()
        for target in search_targets:
            try:
                with yt_dlp.YoutubeDL(ydl_options) as ydl:
                    payload = ydl.extract_info(target, download=False)
            except Exception:
                continue

            entries = payload.get("entries") if isinstance(payload, Mapping) else None
            if not isinstance(entries, list):
                continue

            for entry in entries:
                candidate = self._map_search_candidate(entry, source)
                if candidate is None:
                    continue
                url_key = candidate.open_url().casefold()
                if not url_key or url_key in seen_urls:
                    continue
                seen_urls.add(url_key)
                candidates.append(candidate)
        return candidates

    def _build_search_targets(
        self,
        query: str,
        artist_name: str,
        source: str,
    ) -> list[str]:
        search_text = " ".join(
            part for part in (artist_name.strip(), query.strip()) if part
        ).strip()
        if source == "soundcloud":
            return self._unique_targets(
                [
                    f"scsearch8:{search_text}",
                    f"scsearch8:{query.strip()}",
                ]
            )
        return self._unique_targets(
            [
                f"ytsearch8:{search_text} official audio",
                f"ytsearch8:{search_text}",
                f"ytsearch8:{query.strip()} official audio",
                f"ytsearch8:{query.strip()}",
            ]
        )

    def _map_search_candidate(
        self,
        entry: object,
        source: str,
    ) -> Track | None:
        if not isinstance(entry, Mapping):
            return None

        page_url = self._resolve_entry_url(entry, source)
        if not page_url:
            return None

        title = self._clean_text(entry.get("title"), "")
        source_id = self._clean_text(entry.get("id") or entry.get("url"), title)
        if not title or not source_id:
            return None

        item = DownloadSearchResult(
            source=source,
            source_id=source_id,
            title=title,
            artist=self._clean_text(
                entry.get("artist")
                or entry.get("uploader")
                or entry.get("channel")
                or entry.get("channel_uploader"),
                "Unknown Artist",
            ),
            page_url=page_url,
            image_url=self._extract_image_url(entry.get("thumbnails")),
            album=self._clean_text(
                entry.get("album") or entry.get("playlist_title") or entry.get("channel"),
                "Single",
            ),
            duration_ms=self._extract_duration_ms(entry.get("duration")),
        )
        return self._download_mapper.map_result(item)

    def _build_candidate_match_score(
        self,
        requested_track: Track,
        candidate_track: Track,
        source: str,
        preferred_source: str,
    ) -> float:
        requested_title = requested_track.name
        requested_artist = requested_track.primary_artist_name()
        candidate_title = candidate_track.name
        candidate_artist = candidate_track.primary_artist_name()

        title_score = max(
            self._text_similarity(
                self._normalize_match_text(requested_title),
                self._normalize_match_text(candidate_title),
            ),
            self._text_similarity(
                self._compact_match_text(requested_title),
                self._compact_match_text(candidate_title),
            ),
        )
        artist_score = self._text_similarity(
            self._compact_match_text(requested_artist),
            self._compact_match_text(candidate_artist),
        )

        exact_title_bonus = (
            0.14
            if self._compact_match_text(requested_title)
            and self._compact_match_text(requested_title)
            == self._compact_match_text(candidate_title)
            else 0.0
        )
        preferred_source_bonus = 0.03 if source == preferred_source else 0.0
        derivative_penalty = (
            0.18
            if self._is_derivative_text(candidate_title)
            and not self._is_derivative_text(requested_title)
            else 0.0
        )
        short_form_penalty = (
            0.24
            if self._is_short_form_text(candidate_title)
            and not self._is_short_form_text(requested_title)
            else 0.0
        )
        duration_bonus = 0.12 * self._duration_match_score(
            requested_track.duration_ms,
            candidate_track.duration_ms,
        )
        duration_penalty = (
            0.32
            if self._has_duration_mismatch(
                requested_track.duration_ms,
                candidate_track.duration_ms,
            )
            else 0.0
        )
        length_preference_bonus = self._length_preference_bonus(
            requested_duration_ms=requested_track.duration_ms,
            candidate_duration_ms=candidate_track.duration_ms,
            title_score=title_score,
            artist_score=artist_score,
        )
        ultra_short_penalty = self._ultra_short_candidate_penalty(
            requested_duration_ms=requested_track.duration_ms,
            candidate_duration_ms=candidate_track.duration_ms,
            title_score=title_score,
            artist_score=artist_score,
        )
        return max(
            0.0,
            min(
                1.25,
                (title_score * 0.68)
                + (artist_score * 0.32)
                + exact_title_bonus
                + preferred_source_bonus
                + duration_bonus
                + length_preference_bonus
                - derivative_penalty
                - short_form_penalty
                - duration_penalty
                - ultra_short_penalty
            ),
        )

    def _is_reliable_download_match(
        self,
        requested_track: Track,
        candidate_track: Track,
        score: float,
    ) -> bool:
        title_score = max(
            self._text_similarity(
                self._normalize_match_text(requested_track.name),
                self._normalize_match_text(candidate_track.name),
            ),
            self._text_similarity(
                self._compact_match_text(requested_track.name),
                self._compact_match_text(candidate_track.name),
            ),
        )
        artist_score = self._text_similarity(
            self._compact_match_text(requested_track.primary_artist_name()),
            self._compact_match_text(candidate_track.primary_artist_name()),
        )
        candidate_artist = self._compact_match_text(candidate_track.primary_artist_name())

        if title_score < 0.72:
            return False
        if score < 0.64:
            return False
        if self._has_duration_mismatch(
            requested_track.duration_ms,
            candidate_track.duration_ms,
        ):
            return False
        if (
            self._is_short_form_text(candidate_track.name)
            and not self._is_short_form_text(requested_track.name)
        ):
            return False
        if artist_score >= 0.52:
            return True
        if not candidate_artist and title_score >= 0.96:
            return True
        return False

    def _download_source_order(self) -> list[str]:
        preferred_source = self._state.title_search_source
        if preferred_source == "soundcloud":
            return ["soundcloud", "youtube"]
        return ["youtube", "soundcloud"]

    def _build_query_variants(self, value: str) -> list[str]:
        normalized = value.strip()
        compacted = self._compact_match_text(value)
        return self._unique_targets([normalized, compacted])

    def _normalize_match_text(self, value: str) -> str:
        return self._SPACE_RE.sub(" ", value.casefold().strip())

    def _compact_match_text(self, value: str) -> str:
        lowered = self._normalize_match_text(value)
        without_parenthetical = self._PAREN_RE.sub(" ", lowered)
        without_derivative = self._DERIVATIVE_RE.sub(" ", without_parenthetical)
        return self._SPACE_RE.sub(" ", without_derivative).strip()

    def _is_derivative_text(self, value: str) -> bool:
        return bool(self._DERIVATIVE_RE.search(value or ""))

    def _is_short_form_text(self, value: str) -> bool:
        return bool(self._SHORT_FORM_RE.search(value or ""))

    @staticmethod
    def _text_similarity(left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        return SequenceMatcher(None, left, right).ratio()

    @staticmethod
    def _duration_match_score(
        requested_duration_ms: int,
        candidate_duration_ms: int,
    ) -> float:
        if requested_duration_ms <= 0 or candidate_duration_ms <= 0:
            return 0.0

        duration_delta = abs(requested_duration_ms - candidate_duration_ms)
        soft_tolerance_ms = max(8_000, int(requested_duration_ms * 0.08))
        hard_tolerance_ms = max(30_000, int(requested_duration_ms * 0.35))
        if duration_delta <= soft_tolerance_ms:
            return 1.0
        if duration_delta >= hard_tolerance_ms:
            return 0.0
        return 1.0 - (
            (duration_delta - soft_tolerance_ms)
            / max(1, hard_tolerance_ms - soft_tolerance_ms)
        )

    @staticmethod
    def _has_duration_mismatch(
        requested_duration_ms: int,
        candidate_duration_ms: int,
    ) -> bool:
        if requested_duration_ms <= 0 or candidate_duration_ms <= 0:
            return False

        duration_delta = abs(requested_duration_ms - candidate_duration_ms)
        allowed_delta_ms = max(15_000, int(requested_duration_ms * 0.18))
        return duration_delta > allowed_delta_ms

    @staticmethod
    def _length_preference_bonus(
        requested_duration_ms: int,
        candidate_duration_ms: int,
        title_score: float,
        artist_score: float,
    ) -> float:
        if requested_duration_ms > 0:
            return 0.0
        if candidate_duration_ms <= 0:
            return 0.0
        if title_score < 0.94 or artist_score < 0.85:
            return 0.0

        capped_duration_ms = min(candidate_duration_ms, 240_000)
        return (capped_duration_ms / 240_000) * 0.10

    @staticmethod
    def _ultra_short_candidate_penalty(
        requested_duration_ms: int,
        candidate_duration_ms: int,
        title_score: float,
        artist_score: float,
    ) -> float:
        if requested_duration_ms > 0:
            return 0.0
        if candidate_duration_ms <= 0:
            return 0.0
        if title_score < 0.94 or artist_score < 0.85:
            return 0.0
        if candidate_duration_ms >= 45_000:
            return 0.0
        return 0.18

    def _is_reliable_direct_download_track(self, track: Track) -> bool:
        if not track.download_url:
            return False

        candidate_track = self._load_candidate_track(track.download_url)
        if candidate_track is None or not candidate_track.download_url:
            return False

        source = self._guess_source(track.download_url)
        match_score = self._build_candidate_match_score(
            requested_track=track,
            candidate_track=candidate_track,
            source=source,
            preferred_source=self._download_source_order()[0],
        )
        return self._is_reliable_download_match(
            requested_track=track,
            candidate_track=candidate_track,
            score=match_score,
        )

    def _load_candidate_track(self, url: str) -> Track | None:
        normalized_url = url.strip()
        if not normalized_url:
            return None

        ydl_options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "ignoreerrors": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                payload = ydl.extract_info(normalized_url, download=False)
        except Exception:
            return None

        info = self._resolve_track_payload(payload)
        if not isinstance(info, Mapping):
            return None
        return self._map_search_candidate(
            info,
            self._guess_source(normalized_url),
        )

    def _is_downloaded_audio_compatible(
        self,
        requested_track: Track,
        resolved_track: Track,
        file_path: Path,
    ) -> bool:
        expected_duration_ms = requested_track.duration_ms or resolved_track.duration_ms
        if expected_duration_ms <= 0:
            return True

        try:
            actual_duration_ms = int(MP3(file_path).info.length * 1000)
        except Exception:
            return True

        return not self._has_duration_mismatch(
            expected_duration_ms,
            actual_duration_ms,
        )

    def _build_unique_file_path(self, target_directory: Path, track: Track) -> Path:
        base_name = self._sanitize_filename(f"{track.artist_line()} - {track.name}")
        candidate = target_directory / f"{base_name}.mp3"
        suffix = 1
        while candidate.exists():
            candidate = target_directory / f"{base_name} ({suffix}).mp3"
            suffix += 1
        return candidate

    def _build_unique_directory_path(
        self,
        target_directory: Path,
        track: Track,
    ) -> Path:
        base_name = self._sanitize_filename(f"{track.artist_line()} - {track.name}")
        candidate = target_directory / base_name
        suffix = 1
        while candidate.exists():
            candidate = target_directory / f"{base_name} ({suffix})"
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

    def _cleanup_attempt_outputs(
        self,
        target_directory: Path,
        existing_files: set[Path],
    ) -> None:
        current_files = self._snapshot_files(target_directory)
        for candidate in current_files - existing_files:
            candidate.unlink(missing_ok=True)

    def _wrap_download_error(self, error: Exception) -> DownloadError:
        message = str(error).strip() or error.__class__.__name__
        if "ffmpeg" in message.lower():
            return DownloadError(
                "FFmpeg is required to convert downloads to MP3. "
                "Install FFmpeg and add it to PATH."
            )
        return DownloadError(f"Could not download the selected item: {message}")

    def _needs_metadata_refresh(self, track: Track) -> bool:
        return (
            self._needs_title_refresh(track)
            or self._needs_artist_refresh(track)
            or not track.best_image_url()
        )

    @staticmethod
    def _needs_title_refresh(track: Track) -> bool:
        title = track.name.strip()
        if not title:
            return True
        if title.lower() in {"direct download", "unknown title"}:
            return True
        return bool(re.fullmatch(r"track \d+", title, flags=re.IGNORECASE))

    @staticmethod
    def _needs_artist_refresh(track: Track) -> bool:
        artist_name = track.primary_artist_name().strip().lower()
        return artist_name in {"", "unknown", "unknown artist"}

    @staticmethod
    def _resolve_track_payload(payload: object) -> Mapping[str, object] | None:
        if isinstance(payload, Mapping):
            entries = payload.get("entries")
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, Mapping):
                        return entry
            return payload
        return None

    @staticmethod
    def _guess_source(value: str) -> str:
        normalized = value.casefold()
        if "soundcloud.com" in normalized:
            return "soundcloud"
        return "youtube"

    @staticmethod
    def _resolve_entry_url(entry: Mapping[str, object], source: str) -> str:
        for key in ("webpage_url", "original_url", "permalink_url", "url"):
            value = str(entry.get(key, "") or "").strip()
            if value.startswith("http://") or value.startswith("https://"):
                return value

        raw_id = str(entry.get("id") or entry.get("url") or "").strip()
        if not raw_id:
            return ""
        if source == "soundcloud":
            return raw_id
        return f"https://www.youtube.com/watch?v={raw_id}"

    @staticmethod
    def _extract_duration_ms(value: object) -> int:
        try:
            duration_seconds = int(float(value or 0))
        except (TypeError, ValueError):
            return 0
        return max(0, duration_seconds * 1000)

    @staticmethod
    def _extract_image_url(value: object) -> str:
        if not isinstance(value, list):
            return ""
        for item in reversed(value):
            if not isinstance(item, Mapping):
                continue
            url = str(item.get("url", "")).strip()
            if url:
                return url
        return ""

    @staticmethod
    def _clean_text(value: object, default: str) -> str:
        text = str(value or "").strip()
        return text or default

    @staticmethod
    def _sanitize_filename(value: str) -> str:
        normalized = re.sub(r'[<>:"/\\\\|?*]+', " ", value)
        normalized = re.sub(r"\s+", " ", normalized).strip(" .")
        return normalized or "SpotiVa Track"

    @staticmethod
    def _snapshot_files(target_directory: Path) -> set[Path]:
        return {
            candidate.resolve()
            for candidate in target_directory.iterdir()
            if candidate.is_file()
        }

    def _resolve_downloaded_file_path(
        self,
        expected_file_path: Path,
        existing_files: set[Path],
    ) -> Path | None:
        if expected_file_path.exists():
            return expected_file_path

        current_files = self._snapshot_files(expected_file_path.parent)
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

    @staticmethod
    def _normalize_downloaded_file_name(
        actual_file_path: Path,
        expected_file_path: Path,
    ) -> Path:
        if actual_file_path == expected_file_path:
            return expected_file_path
        if expected_file_path.exists():
            return expected_file_path
        actual_file_path.replace(expected_file_path)
        return expected_file_path

    @staticmethod
    def _unique_targets(values: list[str]) -> list[str]:
        unique_values: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique_values.append(normalized)
        return unique_values


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
        total = self._safe_int(
            payload.get("total_bytes") or payload.get("total_bytes_estimate")
        )

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
