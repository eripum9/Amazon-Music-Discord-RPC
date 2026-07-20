# MIT License - Copyright (c) 2026 eripum9

import json
import subprocess
from types import SimpleNamespace

from MacOS import media_reader


def _payload(**overrides):
    payload = {
        "status": "found",
        "bundle_identifier": "com.amazon.music",
        "display_name": "Amazon Music",
        "title": "Song",
        "artist": "Artist",
        "album": "Album",
        "duration": 240,
        "position": 30.5,
        "playback_rate": 1,
        "artwork_url": "https://images.example.test/art.jpg",
    }
    payload.update(overrides)
    return payload


def test_parse_probe_payload_returns_normalized_track():
    track = media_reader.parse_probe_payload(_payload())
    assert track == {
        "title": "Song",
        "artist": "Artist",
        "album": "Album",
        "status": "playing",
        "position": 30.5,
        "duration": 240.0,
        "art_url": "https://images.example.test/art.jpg",
        "source": "macos_now_playing",
    }


def test_parse_probe_payload_rejects_other_players_and_missing_titles():
    assert media_reader.parse_probe_payload(_payload(bundle_identifier="com.apple.Music")) is None
    assert media_reader.parse_probe_payload(_payload(title="")) is None
    assert media_reader.parse_probe_payload(_payload(status="not_amazon_music")) is None


def test_parse_probe_payload_clamps_timing_and_marks_paused():
    track = media_reader.parse_probe_payload(_payload(duration=120, position=500, playback_rate=0))
    assert track["position"] == 120
    assert track["duration"] == 120
    assert track["status"] == "paused"


def test_parse_probe_payload_rejects_non_finite_timing():
    track = media_reader.parse_probe_payload(_payload(duration=float("inf"), position=float("nan")))
    assert track["duration"] == 0
    assert track["position"] is None


def test_parse_probe_payload_accepts_only_safe_https_artwork():
    assert media_reader.parse_probe_payload(_payload(artwork_url="http://example.test/art.jpg"))["art_url"] == ""
    assert media_reader.parse_probe_payload(_payload(artwork_url="https://user:pass@example.test/art.jpg"))["art_url"] == ""
    assert media_reader.parse_probe_payload(_payload(artwork_url="https://example.test:444/art.jpg"))["art_url"] == ""


def test_get_track_sync_invokes_osascript_without_a_shell():
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps(_payload()), stderr="")

    track = media_reader.get_track_sync(timeout=1.25, runner=runner, platform="darwin")
    assert track["title"] == "Song"
    assert calls == [
        (
            ["/usr/bin/osascript", "-l", "JavaScript", str(media_reader.PROBE_PATH)],
            {"capture_output": True, "text": True, "timeout": 1.25},
        )
    ]


def test_get_track_sync_fails_closed():
    def timeout_runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    def malformed_runner(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="not json", stderr="")

    assert media_reader.get_track_sync(runner=timeout_runner, platform="darwin") is None
    assert media_reader.get_track_sync(runner=malformed_runner, platform="darwin") is None
    assert media_reader.get_track_sync(runner=malformed_runner, platform="linux") is None


def test_get_track_sync_rejects_oversized_output():
    def oversized_runner(command, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=" " * (media_reader.MAX_PROBE_OUTPUT_BYTES + 1),
            stderr="",
        )

    assert media_reader.get_track_sync(runner=oversized_runner, platform="darwin") is None


def test_jxa_probe_is_owner_scoped_and_read_only():
    source = media_reader.PROBE_PATH.read_text(encoding="utf-8")
    assert "bundleIdentifier !== 'com.amazon.music'" in source
    assert "MRNowPlayingRequest" in source
    for forbidden in ("MRNowPlayingController", "sendCommand", "pauseCommand", "playCommand"):
        assert forbidden not in source
