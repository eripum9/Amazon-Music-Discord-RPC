# MIT License - Copyright (c) 2026 eripum9

import asyncio
import re
import time
from datetime import datetime, timezone
from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as SessionManager
from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus

_EXPLICIT_RE = re.compile(r'\s*\[Explicit\]\s*$', re.IGNORECASE)


PLAYBACK_STATUS_MAP = {
    PlaybackStatus.PLAYING: "playing",
    PlaybackStatus.PAUSED: "paused",
    PlaybackStatus.STOPPED: "stopped",
    PlaybackStatus.CLOSED: "stopped",
    PlaybackStatus.OPENED: "stopped",
    PlaybackStatus.CHANGING: "playing",
}


# Windows only gives a *snapshot* of the playback position: "position" is
# where the song was at "last_updated_time".  Amazon Music refreshes that
# snapshot rarely (mostly on play / pause / seek), so using it directly makes
# Discord jump back to an old minute.  ``live_position`` turns the snapshot
# into the real current position.
_WINDOWS_EPOCH_OFFSET = 11644473600  # seconds between 1601-01-01 and 1970-01-01
_last_snapshot = {}


def _seconds(value):
    if value is None:
        return None
    try:
        if hasattr(value, "total_seconds"):
            return max(0.0, float(value.total_seconds()))
        if hasattr(value, "duration"):  # raw TimeSpan (100 ns ticks)
            return max(0.0, float(value.duration) / 10_000_000)
        return max(0.0, float(value))
    except (TypeError, ValueError, OverflowError):
        return None


def _epoch_seconds(value):
    """Convert a WinRT DateTime (datetime or raw ticks) to Unix seconds."""
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            stamp = value.timestamp()
        elif hasattr(value, "universal_time"):
            stamp = float(value.universal_time) / 10_000_000 - _WINDOWS_EPOCH_OFFSET
        else:
            return None
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    # Ignore unset (year 1601/1970) or clearly bogus timestamps.
    if stamp < 946684800 or stamp > time.time() + 60:
        return None
    return stamp


def live_position(track_key, status, raw_position, duration=0, updated_at=None, now=None):
    """Return the current playback position in seconds, or None if unknown."""
    now = time.time() if now is None else now
    if raw_position is None:
        return None
    if not duration and not raw_position:
        # Player does not publish a timeline at all.
        return None

    if updated_at is not None:
        position = raw_position
        if status == "playing":
            position += max(0.0, now - updated_at)
        if duration:
            position = min(position, duration)
        return position

    # No usable timestamp: only trust the snapshot when it actually changes
    # (new song, seek, pause/resume).  An unchanged snapshot is stale.
    previous = _last_snapshot.get("value")
    snapshot = (track_key, round(raw_position, 1), status)
    _last_snapshot["value"] = snapshot
    if status == "playing" and previous == snapshot:
        return None
    return raw_position


async def _get_amazon_session(manager):
    sessions = manager.get_sessions()
    for session in sessions:
        source = session.source_app_user_model_id.lower()
        if "amazon" in source and "music" in source:
            return session
    for session in sessions:
        source = session.source_app_user_model_id.lower()
        if "amazon" in source:
            return session
    return None


async def _get_media_info(session):
    info = await session.try_get_media_properties_async()
    playback = session.get_playback_info()

    title = info.title or ""
    title = _EXPLICIT_RE.sub("", title)
    artist = info.artist or ""
    album = info.album_title or ""
    status = PLAYBACK_STATUS_MAP.get(playback.playback_status, "stopped")

    timeline = session.get_timeline_properties()
    raw_position = _seconds(getattr(timeline, "position", None))
    end_time = _seconds(getattr(timeline, "end_time", None)) or 0
    updated_at = _epoch_seconds(getattr(timeline, "last_updated_time", None))
    position = live_position(f"{title}|{artist}", status, raw_position, end_time, updated_at)

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "status": status,
        "position": position,
        "duration": end_time,
    }


async def get_current_track():
    manager = await SessionManager.request_async()
    session = await _get_amazon_session(manager)
    if session is None:
        return None
    return await _get_media_info(session)


def get_track_sync(timeout=2.5):
    try:
        return asyncio.run(asyncio.wait_for(get_current_track(), timeout))
    except (asyncio.TimeoutError, OSError, RuntimeError):
        return None


if __name__ == "__main__":
    track = get_track_sync()
    if track:
        print(f"Title:    {track['title']}")
        print(f"Artist:   {track['artist']}")
        print(f"Album:    {track['album']}")
        print(f"Status:   {track['status']}")
        position = track['position']
        position_text = f"{position:.1f}s" if position is not None else "unknown"
        print(f"Position: {position_text} / {track['duration']:.1f}s")
    else:
        print("Amazon Music session not found. Is it running?")
