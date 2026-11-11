# MIT License - Copyright (c) 2026 eripum9

import asyncio
import re
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
    reported_position = getattr(timeline, "position", None)
    reported_end = getattr(timeline, "end_time", None)
    position = reported_position.total_seconds() if reported_position else 0
    end_time = reported_end.total_seconds() if reported_end else 0
    # An empty SMTC timeline is not evidence that the listener sought to zero.
    if not any(getattr(timeline, field, None) for field in (
        "position", "start_time", "end_time", "min_seek_time", "max_seek_time"
    )):
        position = None

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
        print(f"Position: {track['position']:.1f}s / {track['duration']:.1f}s")
    else:
        print("Amazon Music session not found. Is it running?")
