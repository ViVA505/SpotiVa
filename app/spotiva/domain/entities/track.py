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
