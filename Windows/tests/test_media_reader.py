# MIT License - Copyright (c) 2026 eripum9

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest

import media_reader
import rpc_state


def test_smtc_device_not_ready_is_treated_as_no_track(monkeypatch):
    async def unavailable():
        raise OSError(-2147024875, "The device is not ready")

    monkeypatch.setattr(media_reader, "get_current_track", unavailable)
    assert media_reader.get_track_sync(timeout=0.1) is None


def _session(timeline):
    async def properties():
        return SimpleNamespace(title="Song", artist="Artist", album_title="Album")

    return SimpleNamespace(
        try_get_media_properties_async=properties,
        get_playback_info=lambda: SimpleNamespace(playback_status=media_reader.PlaybackStatus.PLAYING),
        get_timeline_properties=lambda: timeline,
    )


def _timeline(**seconds):
    return SimpleNamespace(**{
        name: timedelta(seconds=seconds.get(name, 0))
        for name in ("position", "start_time", "end_time", "min_seek_time", "max_seek_time")
    })


@pytest.mark.parametrize("timeline", [None, _timeline()])
def test_missing_smtc_timeline_has_unknown_position(timeline):
    track = asyncio.run(media_reader._get_media_info(_session(timeline)))
    assert track["position"] is None
    assert track["duration"] == 0
    assert track["status"] == "playing"


@pytest.mark.parametrize("seconds", [
    {"end_time": 180},
    {"max_seek_time": 180},
    {"position": 24},
    {"start_time": 10},
])
def test_meaningful_smtc_timeline_preserves_reported_position(seconds):
    track = asyncio.run(media_reader._get_media_info(_session(_timeline(**seconds))))
    assert track["position"] == seconds.get("position", 0)
    assert track["duration"] == seconds.get("end_time", 0)


def test_empty_smtc_timeline_does_not_repeatedly_reset_discord_timer(monkeypatch):
    timing = rpc_state.TrackTimingState()
    track = asyncio.run(media_reader._get_media_info(_session(_timeline())))
    monkeypatch.setattr(rpc_state.time, "time", lambda: 1000)
    start = timing.track_start_ts(track, "Song|Artist")
    for now in (1004, 1008, 1012):
        monkeypatch.setattr(rpc_state.time, "time", lambda: now)
        updated, _, refreshed = timing.playing_start_ts(track, "Song|Artist", start, None, False)
        assert updated == start
        assert refreshed is False


def test_valid_smtc_seek_to_zero_still_resynchronizes(monkeypatch):
    track = asyncio.run(media_reader._get_media_info(_session(_timeline(end_time=180))))
    monkeypatch.setattr(rpc_state.time, "time", lambda: 1000)
    start, _, refreshed = rpc_state.TrackTimingState().playing_start_ts(
        track, "Song|Artist", 980, None, False
    )
    assert start == 1000
    assert refreshed is True
