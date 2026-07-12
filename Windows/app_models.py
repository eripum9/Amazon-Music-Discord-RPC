from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class PlaybackStatus(StrEnum):
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


def _text(value, limit=2048):
    return str(value or "").strip()[:limit]


def _seconds(value):
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _optional_seconds(value):
    if value is None or value == "":
        return None
    return _seconds(value)


def _mapping(value):
    return dict(value) if isinstance(value, Mapping) else {}


@dataclass(frozen=True, slots=True)
class TrackSnapshot:
    title: str = ""
    artist: str = ""
    album: str = ""
    status: PlaybackStatus = PlaybackStatus.UNKNOWN
    position: float | None = None
    duration: float = 0.0
    art_url: str = ""
    track_link: str = ""
    source: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None):
        source = value if isinstance(value, Mapping) else {}
        try:
            status = PlaybackStatus(_text(source.get("status")).lower())
        except ValueError:
            status = PlaybackStatus.UNKNOWN
        return cls(
            title=_text(source.get("title"), 512),
            artist=_text(source.get("artist"), 512),
            album=_text(source.get("album"), 512),
            status=status,
            position=_optional_seconds(source.get("position")),
            duration=_seconds(source.get("duration")),
            art_url=_text(source.get("art_url") or source.get("_amazon_art_url"), 4096),
            track_link=_text(source.get("track_link") or source.get("_amazon_track_link"), 4096),
            source=_text(source.get("source"), 80),
        )

    def to_dict(self):
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload

    @property
    def key(self):
        return f"{self.title}|{self.artist}"

    @property
    def has_identity(self):
        return bool(self.title and self.artist)


@dataclass(frozen=True, slots=True)
class DiagnosticsSnapshot:
    updated_at: float
    app_version: str
    rpc_status: str = "unknown"
    discord_status: str = "unknown"
    client_id: str = ""
    track: TrackSnapshot | None = None
    presence_visible: bool = False
    album_art_url: str = ""
    album_name: str = ""
    track_link: str = ""
    notification_enabled: bool = False
    notification: Mapping[str, Any] | None = None
    amazon_devtools: Mapping[str, Any] = field(default_factory=dict)
    amazify: Mapping[str, Any] = field(default_factory=dict)
    scrobbling: Mapping[str, Any] = field(default_factory=dict)
    privacy: Mapping[str, Any] = field(default_factory=dict)
    runtime: Mapping[str, Any] = field(default_factory=dict)
    last_error: str = ""

    @classmethod
    def from_state(cls, updated_at, app_version, state):
        values = dict(state or {})
        track = values.pop("track", None)
        return cls(
            updated_at=float(updated_at),
            app_version=_text(app_version, 32),
            rpc_status=_text(values.get("rpc_status"), 32),
            discord_status=_text(values.get("discord_status"), 32),
            client_id=_text(values.get("client_id"), 64),
            track=TrackSnapshot.from_mapping(track) if isinstance(track, Mapping) else None,
            presence_visible=bool(values.get("presence_visible")),
            album_art_url=_text(values.get("album_art_url"), 4096),
            album_name=_text(values.get("album_name"), 512),
            track_link=_text(values.get("track_link"), 4096),
            notification_enabled=bool(values.get("notification_enabled")),
            notification=values.get("notification") if isinstance(values.get("notification"), Mapping) else None,
            amazon_devtools=_mapping(values.get("amazon_devtools")),
            amazify=_mapping(values.get("amazify")),
            scrobbling=_mapping(values.get("scrobbling")),
            privacy=_mapping(values.get("privacy")),
            runtime=_mapping(values.get("runtime")),
            last_error=_text(values.get("last_error"), 2048),
        )

    def to_dict(self):
        payload = asdict(self)
        payload["track"] = self.track.to_dict() if self.track else None
        return payload
