# MIT License - Copyright (c) 2026 eripum9

import importlib
import socket
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

import desktop_runtime as main
import rpc_state


def poll(at, status="playing", *, native=False, connected=True, missing=False, error=False, wall=None, **fields):
    return {
        "at": at,
        "wall": at if wall is None else wall,
        "native": native,
        "connected": connected,
        "error": error,
        "track": None if missing else {
            "title": "Song",
            "artist": "Artist",
            "album": "Album",
            "status": status,
            "position": 0,
            "duration": 180,
            **fields,
        },
    }


@pytest.fixture
def isolated_environment(monkeypatch, tmp_path):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Unexpected config, Credential Manager, network, or desktop access")

    for name in ("APPDATA", "LOCALAPPDATA", "HOME", "USERPROFILE"):
        monkeypatch.setenv(name, str(tmp_path))
    monkeypatch.chdir(tmp_path)
    config = importlib.import_module("config")
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    for name in ("load_config", "update_config_fields", "mutate_config_fields", "WindowsCredentialStore"):
        monkeypatch.setattr(config, name, forbidden)
    monkeypatch.setattr(importlib.import_module("credential_store"), "WindowsCredentialStore", forbidden)
    for name in ("load_config", "update_config_fields", "mutate_config_fields",
                 "_run_picker_async", "_prompt_wrong_song_async", "get_notification_track_sync",
                 "launch_amazon_music_devtools", "restart_amazon_music_devtools", "amazon_music_is_running"):
        monkeypatch.setattr(main, name, forbidden)
    for name in ("LOG_DIR", "LOG_PATH", "EVENT_LOG_PATH", "DIAGNOSTICS_PATH", "COMMAND_PATH", "CONFIG_PATH"):
        monkeypatch.setattr(main, name, str(tmp_path / name))
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)


@pytest.fixture
def run_runtime(monkeypatch, isolated_environment):
    def run(samples, *, art_results=None, before_sample=None, **config):
        cursor = {"index": 0}
        rpc = Mock(connected=samples[0]["connected"])
        lastfm = Mock()
        listenbrainz = Mock()
        submissions = []
        updates = []
        diagnostics = []

        def current():
            return samples[cursor["index"]]

        def sleep(_seconds):
            if cursor["index"] + 1 == len(samples):
                main.rpc_running = False
            else:
                cursor["index"] += 1
                rpc.connected = current()["connected"]
                if before_sample:
                    before_sample(current(), main)

        def read_track():
            if current()["error"]:
                raise RuntimeError("mock metadata disconnect")
            track = current()["track"]
            return dict(track) if track else None

        def read_native(*_args, **_kwargs):
            if not current()["native"]:
                return {"status": "unavailable"}
            track = current()["track"]
            return {
                **track,
                "status": "found",
                "playback_status": track["status"],
                "art_url": track.get("_amazon_art_url", ""),
                "track_link": track.get("_amazon_track_link", ""),
            }

        clock = SimpleNamespace(
            time=lambda: 1000 + current()["wall"],
            monotonic=lambda: current()["at"],
            sleep=sleep,
        )
        monkeypatch.setattr(main, "time", clock)
        monkeypatch.setattr(rpc_state, "time", clock)
        monkeypatch.setattr(main, "rpc_running", True)
        monkeypatch.setattr(main, "active_rpc", None)
        monkeypatch.setattr(main, "active_scrobblers", ())
        monkeypatch.setattr(main, "_current_track_raw", None)
        monkeypatch.setattr(main, "application_state", main.ApplicationState())
        monkeypatch.setattr(main, "tasks", SimpleNamespace(stopping=False))
        monkeypatch.setattr(main, "_timing_state", rpc_state.TrackTimingState())
        store = rpc_state.ResolvedTrackStore()
        monkeypatch.setattr(main, "_resolved_store", store)
        monkeypatch.setattr(main, "_resolved_cache", store.cache)
        monkeypatch.setattr(main, "_resolved_track_info", store.track_info)
        monkeypatch.setattr(main, "_amazify_metadata_owner", lambda **_kwargs: {})
        monkeypatch.setattr(main, "_amazify_compat_snapshot", lambda: {})
        monkeypatch.setattr(main, "_should_prompt_wrong_song", lambda *_args: False)
        monkeypatch.setattr(main, "_write_diagnostics_state", lambda **state: diagnostics.append(state))
        monkeypatch.setattr(main, "DiscordRPC", Mock(return_value=rpc))
        monkeypatch.setattr(main, "get_track_sync", read_track)
        monkeypatch.setattr(main, "get_devtools_track_sync", read_native)
        art_lookup = Mock(return_value=("https://art.test/fallback", "Fallback", "https://deezer.test/song", 180))
        if art_results is not None:
            art_lookup.side_effect = art_results
        monkeypatch.setattr(main, "get_album_art", art_lookup)
        monkeypatch.setitem(sys.modules, "lastfm", SimpleNamespace(LastFMScrobbler=Mock(return_value=lastfm)))
        monkeypatch.setitem(sys.modules, "listenbrainz_scrobbler", SimpleNamespace(ListenBrainzScrobbler=Mock(return_value=listenbrainz)))
        monkeypatch.setattr(main, "current_config", {
            "lastfm_enabled": True,
            "lastfm_api_key": "key",
            "lastfm_api_secret": "secret",
            "lastfm_session_key": "session",
            "listenbrainz_enabled": True,
            "listenbrainz_token": "token",
            "song_link_enabled": True,
            **config,
        })
        rpc.update.side_effect = lambda **payload: updates.append((current()["at"], payload))
        for service, name in ((lastfm, "lastfm"), (listenbrainz, "listenbrainz")):
            service.scrobble.side_effect = lambda *args, name=name: submissions.append((current()["at"], name, args))

        main.rpc_loop()

        assert cursor["index"] == len(samples) - 1
        errors = [state["last_error"] for state in diagnostics if state.get("last_error")]
        assert errors == ["mock metadata disconnect"] * sum(sample["error"] for sample in samples)
        return SimpleNamespace(
            rpc=rpc, lastfm=lastfm, listenbrainz=listenbrainz, submissions=submissions,
            updates=updates, diagnostics=diagnostics, art_lookup=art_lookup,
        )

    return run


@pytest.mark.parametrize("status", ["stopped", "closed", "opened", " STOPPED "])
def test_stopped_metadata_never_publishes_or_scrobbles(run_runtime, status):
    result = run_runtime([poll(0, status), poll(200, status)])
    assert result.updates == []
    assert result.submissions == []
    result.art_lookup.assert_not_called()
    result.lastfm.update_now_playing.assert_not_called()
    result.listenbrainz.update_now_playing.assert_not_called()


def test_stopped_metadata_clears_existing_presence_and_suspends_listening(run_runtime):
    result = run_runtime([
        poll(0), poll(3, position=3), poll(6, "stopped"), poll(200, "stopped"),
        poll(203, position=3), poll(206, position=6),
    ])
    result.rpc.clear.assert_called_once()
    assert [at for at, _ in result.updates] == [0, 3, 203, 206]
    assert result.submissions == []
    assert sum(state.get("track") is None for state in result.diagnostics) == 4


@pytest.mark.parametrize("show_paused", [True, False])
def test_pause_resume_counts_listening_not_wall_time_and_keeps_submission_epoch(run_runtime, show_paused):
    result = run_runtime([
        poll(0), poll(3, position=3), poll(6, "paused", position=3),
        poll(200, "paused", position=3), poll(203, position=3),
        poll(289, position=89), poll(290, position=90), poll(293, position=93),
    ], show_paused=show_paused)
    assert result.submissions == [
        (290, "lastfm", ("Song", "Artist", 1000, "Fallback", 180)),
        (290, "listenbrainz", ("Song", "Artist", 1000, "Fallback", 180)),
    ]
    result.lastfm.update_now_playing.assert_called_once()
    resumed = dict(result.updates)[203]
    assert resumed["start_ts"] == 1200
    assert (6 in dict(result.updates)) is show_paused


def test_seek_does_not_add_position_jump_to_listening(run_runtime):
    result = run_runtime([
        poll(0), poll(3, position=150), poll(6, position=0),
        poll(9, position=170), poll(90, position=90),
    ])
    assert [at for at, _, _ in result.submissions] == [90, 90]
    assert all(args[2] == 1000 for _, _, args in result.submissions)


@pytest.mark.parametrize("show_paused", [True, False])
def test_pause_without_native_position_preserves_epoch_and_resume_timer(run_runtime, show_paused):
    result = run_runtime([
        poll(0, position=None), poll(3, "paused", position=None),
        poll(197, "paused", position=None), poll(200, position=None), poll(290, position=None),
    ], show_paused=show_paused)
    assert dict(result.updates)[200]["start_ts"] == 1197
    assert [(at, args[2]) for at, _, args in result.submissions] == [(290, 1000), (290, 1000)]


def test_wall_clock_jump_does_not_add_listening_time(run_runtime):
    result = run_runtime([poll(0), poll(3, wall=3000, position=3), poll(6, wall=3003, position=6)])
    assert result.submissions == []


@pytest.mark.parametrize("gap", [{"missing": True}, {"connected": False}, {"error": True}])
def test_unobserved_or_disconnected_gap_does_not_add_listening(run_runtime, gap):
    result = run_runtime([
        poll(0), poll(3, position=3), poll(6, **gap), poll(200, **gap),
        poll(203, position=3), poll(206, position=6), poll(290, position=90), poll(293, position=93),
    ])
    expected_at, expected_epoch = (293, 1203) if gap.get("missing") else (290, 1000)
    assert [(at, args[2]) for at, _, args in result.submissions] == [
        (expected_at, expected_epoch), (expected_at, expected_epoch),
    ]


def test_privacy_suppression_resets_listening_before_same_track_returns(run_runtime):
    result = run_runtime([
        poll(0), poll(3, position=3), poll(6, album="Secret"), poll(200, album="Secret"),
        poll(203), poll(290, position=87), poll(293, position=90),
    ], privacy_blocked_keywords="Secret")
    assert [at for at, _, _ in result.submissions] == [293, 293]
    assert all(args[2] == 1203 for _, _, args in result.submissions)
    assert 6 not in dict(result.updates) and 200 not in dict(result.updates)


def test_privacy_opt_in_still_allows_hidden_track_scrobbling(run_runtime):
    result = run_runtime([poll(0), poll(90, position=90)], privacy_private_session=True, privacy_disable_scrobbling=False)
    assert result.updates == []
    assert [at for at, _, _ in result.submissions] == [90, 90]


def test_track_change_after_pause_does_not_submit_previous_wall_time(run_runtime):
    result = run_runtime([
        poll(0), poll(3, position=3), poll(6, "paused", position=3),
        poll(200, "paused", title="Other"), poll(203, title="Other"),
        poll(293, title="Other", position=90),
    ])
    assert result.submissions == [
        (293, "lastfm", ("Other", "Artist", 1203, "Fallback", 180)),
        (293, "listenbrainz", ("Other", "Artist", 1203, "Fallback", 180)),
    ]


def test_song_end_resets_listening_and_submission_epoch(run_runtime):
    result = run_runtime([
        poll(0, native=True, position=None, duration=60, _amazon_art_url="https://art.test/native"),
        poll(30, native=True, position=None, duration=60, _amazon_art_url="https://art.test/native"),
        poll(60, native=True, position=None, duration=60, _amazon_art_url="https://art.test/native"),
        poll(90, native=True, position=None, duration=60, _amazon_art_url="https://art.test/native"),
    ], amazon_devtools_enabled=True)
    assert [(at, args[2]) for at, _, args in result.submissions] == [(30, 1000), (30, 1000), (90, 1060), (90, 1060)]


@pytest.mark.parametrize("custom", [False, True])
def test_same_track_late_native_enrichment_refreshes_without_lookup(run_runtime, custom):
    result = run_runtime([
        poll(0),
        poll(3, native=True, album="Canonical", position=3, duration=200,
             _amazon_art_url="https://art.test/native", _amazon_track_link="https://music.amazon.com/song"),
        poll(6, native=True, album="Canonical", position=6, duration=200,
             _amazon_art_url="https://art.test/new", _amazon_track_link="https://music.amazon.com/new"),
        poll(100, native=True, album="Canonical", position=100, duration=200,
             _amazon_art_url="https://art.test/new", _amazon_track_link="https://music.amazon.com/new"),
    ], amazon_devtools_enabled=True, custom_albums=[{
        "album": "Custom", "aliases": ["Canonical"], "art_url": "https://art.test/custom",
    }] if custom else [])
    updates = dict(result.updates)
    assert updates[0]["album_art_url"] == "https://art.test/fallback"
    assert updates[3]["album_name"] == ("Custom" if custom else "Canonical")
    assert updates[3]["album_art_url"] == ("https://art.test/custom" if custom else "https://art.test/native")
    assert updates[6]["album_art_url"] == ("https://art.test/custom" if custom else "https://art.test/new")
    assert updates[6]["buttons"] == [{"label": "Listen on Amazon Music", "url": "https://music.amazon.com/new"}]
    assert updates[3]["duration"] == 200
    assert updates[3]["start_ts"] == updates[0]["start_ts"] == 1000
    result.art_lookup.assert_called_once_with("Song", "Artist")
    result.lastfm.update_now_playing.assert_called_once()
    assert [(at, args[2:]) for at, _, args in result.submissions] == [
        (100, (1000, "Custom" if custom else "Canonical", 200)),
        (100, (1000, "Custom" if custom else "Canonical", 200)),
    ]


def test_native_album_change_or_withdrawal_does_not_retain_stale_art_and_links(run_runtime):
    result = run_runtime([
        poll(0, native=True, album="Original", _amazon_art_url="https://art.test/old", _amazon_track_link="https://music.amazon.com/old"),
        poll(3, native=True, album="Canonical"),
        poll(6, native=True, album="Canonical", _amazon_art_url="https://art.test/new", _amazon_track_link="https://music.amazon.com/new"),
        poll(9, native=True, album="Canonical"),
    ], amazon_devtools_enabled=True)
    updates = dict(result.updates)
    for at in (3, 9):
        assert updates[at]["album_name"] == "Canonical"
        assert updates[at]["album_art_url"] == ""
        assert all(button["url"] not in {"https://music.amazon.com/old", "https://music.amazon.com/new"} for button in updates[at]["buttons"])
    result.art_lookup.assert_not_called()


def test_late_native_album_without_art_clears_mismatched_deezer_art_and_link_without_lookup(run_runtime):
    result = run_runtime([
        poll(0), poll(3, native=True, album="Canonical"),
        poll(6, native=True, album="Canonical", _amazon_art_url="https://art.test/native"),
    ], amazon_devtools_enabled=True, song_link_provider="deezer")
    updates = dict(result.updates)
    assert updates[0]["buttons"] == [{"label": "Listen on Deezer", "url": "https://deezer.test/song"}]
    assert updates[3]["album_name"] == "Canonical"
    assert updates[3]["album_art_url"] == ""
    assert updates[3]["buttons"] is None
    assert updates[6]["album_art_url"] == "https://art.test/native"
    result.art_lookup.assert_called_once_with("Song", "Artist")


def test_new_track_does_not_inherit_native_album_art_or_links(run_runtime):
    result = run_runtime([
        poll(0, native=True, album="Original", _amazon_art_url="https://art.test/old", _amazon_track_link="https://music.amazon.com/old"),
        poll(3, native=True, title="Other", album=""),
    ], amazon_devtools_enabled=True, art_results=[("", "", "", 0)])
    replacement = dict(result.updates)[3]
    assert replacement["title"] == "Other"
    assert replacement["album_name"] == ""
    assert replacement["album_art_url"] == ""
    assert all(button["url"] != "https://music.amazon.com/old" for button in replacement["buttons"])
    result.art_lookup.assert_called_once_with("Other", "Artist")


@pytest.mark.parametrize("initial_native", [False, True])
@pytest.mark.parametrize("custom", [False, True])
def test_unchanged_source_hint_preserves_lookup_album_art_and_link(run_runtime, initial_native, custom):
    result = run_runtime([
        poll(0, native=initial_native, album="Player hint", duration=0),
        poll(3, native=True, album="Player hint", duration=0, position=3,
             _amazon_track_link="https://music.amazon.com/song"),
        poll(6, native=True, album="Player hint", duration=200, position=6,
             _amazon_track_link="https://music.amazon.com/new"),
        poll(100, native=True, album="Player hint", duration=200, position=100,
             _amazon_track_link="https://music.amazon.com/new"),
    ], amazon_devtools_enabled=True, song_link_provider="deezer", custom_albums=[{
        "album": "Custom", "aliases": ["Fallback"], "art_url": "https://art.test/custom",
    }] if custom else [])
    album = "Custom" if custom else "Fallback"
    for _, payload in result.updates:
        assert payload["album_name"] == album
        assert payload["album_art_url"] == ("https://art.test/custom" if custom else "https://art.test/fallback")
        assert payload["buttons"] == [{"label": "Listen on Deezer", "url": "https://deezer.test/song"}]
    assert dict(result.updates)[6]["duration"] == 200
    assert [(at, args[2:]) for at, _, args in result.submissions] == [
        (100, (1000, album, 200)), (100, (1000, album, 200)),
    ]
    result.art_lookup.assert_called_once_with("Song", "Artist")


def test_late_native_art_promotes_hint_without_retaining_lookup_album_link(run_runtime):
    result = run_runtime([
        poll(0, native=True, album="Player hint"),
        poll(3, native=True, album="Player hint", position=3, _amazon_art_url="https://art.test/native"),
        poll(6, native=True, album="Player hint", position=6, _amazon_art_url="https://art.test/new"),
    ], amazon_devtools_enabled=True, song_link_provider="deezer")
    updates = dict(result.updates)
    assert updates[0]["album_name"] == "Fallback"
    for at, art in ((3, "native"), (6, "new")):
        assert updates[at]["album_name"] == "Player hint"
        assert updates[at]["album_art_url"] == f"https://art.test/{art}"
        assert updates[at]["buttons"] is None
    result.art_lookup.assert_called_once_with("Song", "Artist")


def test_manual_correction_survives_subsequent_native_refresh(run_runtime):
    def choose_track(sample, runtime):
        if sample["at"] == 3:
            runtime._resolved_cache["Song|Artist"] = ("Chosen song", "Chosen artist")
            runtime._store_resolved_track("Song|Artist", {
                "title": "Chosen song", "artist": "Chosen artist", "album": "Chosen album",
                "art_url": "https://art.test/chosen", "track_link": "https://deezer.test/chosen",
                "duration": 210,
            })

    result = run_runtime([
        poll(0, native=True), poll(3, native=True, position=3),
        poll(6, native=True, album="Native album", position=6, duration=200,
             _amazon_art_url="https://art.test/native", _amazon_track_link="https://music.amazon.com/native"),
        poll(105, native=True, album="Native album", position=105, duration=200,
             _amazon_art_url="https://art.test/new", _amazon_track_link="https://music.amazon.com/new"),
    ], amazon_devtools_enabled=True, song_link_provider="deezer", before_sample=choose_track)
    for at in (3, 6, 105):
        payload = dict(result.updates)[at]
        assert (payload["title"], payload["artist"], payload["album_name"], payload["album_art_url"]) == (
            "Chosen song", "Chosen artist", "Chosen album", "https://art.test/chosen",
        )
        assert payload["buttons"] == [{"label": "Listen on Deezer", "url": "https://deezer.test/chosen"}]
    assert [(at, args) for at, _, args in result.submissions] == [
        (105, ("Chosen song", "Chosen artist", 1000, "Chosen album", 210)),
        (105, ("Chosen song", "Chosen artist", 1000, "Chosen album", 210)),
    ]
    result.art_lookup.assert_called_once_with("Song", "Artist")
