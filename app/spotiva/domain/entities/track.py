from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TrackImage:
    url: str
    width: int = 0
    height: int = 0


@dataclass(frozen=True)
class Artist:
    name: str
    spotify_url: str = ""


@dataclass(frozen=True)
class Album:
    name: str
    release_date: str = ""
    images: list[TrackImage] = field(default_factory=list)
    spotify_url: str = ""


@dataclass(frozen=True)
class Track:
    track_id: str
    name: str
    artists: list[Artist]
    album: Album
    duration_ms: int
    spotify_url: str
    external_url: str = ""
    download_url: str | None = None
    source_label: str = "Spotify"
    is_downloadable: bool = False
    preview_url: str | None = None
    is_explicit: bool = False
    popularity: int = 0
    item_type: str = "track"
    item_count: int = 0
    album_tracks: list["Track"] = field(default_factory=list)
    lyric_match_score: float = 0.0
    lyric_match_text: str = ""

    def primary_artist_name(self) -> str:
        if not self.artists:
            return "Unknown Artist"
        return self.artists[0].name

    def artist_line(self) -> str:
        if not self.artists:
            return "Unknown Artist"
        return ", ".join(artist.name for artist in self.artists)

    def duration_label(self) -> str:
        total_seconds = max(0, self.duration_ms // 1000)
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes}:{seconds:02d}"

    def popularity_label(self) -> str:
        return f"{max(0, self.popularity)} / 100"

    def best_image_url(self) -> str:
        if not self.album.images:
            return ""
        return self.album.images[0].url

    def open_url(self) -> str:
        return self.external_url or self.spotify_url

    def copy_url(self) -> str:
        return self.open_url()

    def is_album_result(self) -> bool:
        return self.item_type == "album"

    def item_type_label(self) -> str:
        return "Album" if self.is_album_result() else "Track"

    def item_count_label(self) -> str:
        if self.item_count <= 0:
            return ""
        suffix = "track" if self.item_count == 1 else "tracks"
        return f"{self.item_count} {suffix}"

    def has_lyric_match(self) -> bool:
        return self.lyric_match_score > 0

    def lyric_match_percent(self) -> int:
        bounded = max(0.0, min(float(self.lyric_match_score), 1.0))
        return int(round(bounded * 100))

    def lyric_match_badge_label(self) -> str:
        if not self.has_lyric_match():
            return ""
        return f"{self.lyric_match_percent()}% match"

    def card_badge_label(self) -> str:
        if self.has_lyric_match():
            return self.lyric_match_badge_label()
        if self.is_album_result():
            return self.item_count_label() or self.item_type_label()
        if self.duration_ms > 0:
            return self.duration_label()
        return self.item_type_label()

    def download_action_label(self) -> str:
        return "Download"

    def saved_item_label(self) -> str:
        return "Album" if self.is_album_result() else "Track"
