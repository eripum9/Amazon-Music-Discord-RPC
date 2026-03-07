import asyncio
from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as SessionManager
from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus


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
    artist = info.artist or ""
    album = info.album_title or ""
    status = PLAYBACK_STATUS_MAP.get(playback.playback_status, "stopped")

    timeline = session.get_timeline_properties()
    position = timeline.position.total_seconds() if timeline.position else 0
    end_time = timeline.end_time.total_seconds() if timeline.end_time else 0

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


def get_track_sync():
    return asyncio.run(get_current_track())


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
