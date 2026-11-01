# MIT License - Copyright (c) 2026 eripum9

import pytest

from .conftest import poll


def test_paused_track_consumes_successful_deezer_lookup(run_runtime):
    result = run_runtime([poll(0, "paused"), poll(3, "paused"), poll(6, "paused")])
    assert result.updates[6]["buttons"] == [
        {"label": "Listen on Deezer", "url": "https://deezer.test/Song"},
    ]
    result.art_lookup.assert_called_once()
    assert not result.submissions


def test_missing_native_duration_backfills_scrobble_threshold(run_runtime):
    result = run_runtime([
        poll(0, native=True, duration=0), poll(3, native=True, duration=0, position=3),
        poll(99, native=True, duration=0, position=99),
        poll(100, native=True, duration=0, position=100),
        poll(103, native=True, duration=0, position=103),
    ], amazon_devtools_enabled=True, lookup_delay=3)
    assert [(at, service, args[2:]) for at, service, args in result.submissions] == [
        (100, "lastfm", (1000, "Song album", 200)),
        (100, "listenbrainz", (1000, "Song album", 200)),
    ]
    assert result.updates[99]["duration"] == 200


def test_manual_correction_wins_over_inflight_lookup(run_runtime):
    def choose_track(sample, runtime):
        if sample.at == 3:
            # This is the same store boundary used by the track picker callback.
            runtime._resolved_cache["Song|Artist"] = ("Chosen song", "Chosen artist")
            runtime._store_resolved_track("Song|Artist", {
                "title": "Chosen song", "artist": "Chosen artist", "album": "Chosen album",
                "art_url": "https://art.test/chosen", "track_link": "https://deezer.test/chosen",
                "duration": 210,
            })

    result = run_runtime([poll(0), poll(3, position=3), poll(6, position=6)],
                         lookup_delay=3, before_sample=choose_track)
    if result.has_resolver:
        assert any(event[0] == "request" for event in result.resolvers[0].events)
    for at in (3, 6):
        chosen = result.updates[at]
        assert (chosen["title"], chosen["artist"], chosen["album_name"], chosen["album_art_url"]) == (
            "Chosen song", "Chosen artist", "Chosen album", "https://art.test/chosen",
        )
        assert chosen["buttons"] == [{"label": "Listen on Deezer", "url": "https://deezer.test/chosen"}]


def test_skip_keeps_art_and_link_identity_with_current_track(run_runtime):
    result = run_runtime([
        poll(0), poll(3, position=3), poll(6, title="Next"),
        poll(9, title="Next", position=3), poll(12, title="Next", position=6),
    ], lookup_delay=3)
    for at, title in ((3, "Song"), (9, "Next"), (12, "Next")):
        payload = result.updates[at]
        assert payload["title"] == title
        assert payload["album_name"] == f"{title} album"
        assert payload["album_art_url"] == f"https://art.test/{title}"
        assert payload["buttons"] == [{"label": "Listen on Deezer", "url": f"https://deezer.test/{title}"}]
    assert not result.submissions


@pytest.mark.parametrize("status", ["playing", "paused"])
def test_initial_private_session_suppresses_external_queries(run_runtime, status):
    result = run_runtime([poll(0, status), poll(300, status)], privacy_private_session=True)
    assert not result.updates
    assert not result.submissions
    result.art_lookup.assert_not_called()
    assert all(not resolver.events for resolver in result.resolvers)
    for service in result.services.values():
        service.update_now_playing.assert_not_called()
    hidden = [data for _, data in result.diagnostics if data.get("privacy", {}).get("hidden")]
    assert len(hidden) == 2
    assert all(data["album_art_url"] == data["track_link"] == "" for data in hidden)


@pytest.mark.parametrize("show_paused", [True, False])
def test_pause_resume_refreshes_presence_timer(run_runtime, show_paused):
    result = run_runtime([
        poll(0, position=10), poll(3, position=13), poll(6, "paused", position=13),
        poll(60, "paused", position=13), poll(63, position=13), poll(66, position=16),
    ], show_paused=show_paused)
    assert result.updates[0]["start_ts"] == 990
    assert result.updates[63]["start_ts"] == result.updates[66]["start_ts"] == 1050
    assert (6 in result.updates) is show_paused
    if show_paused:
        assert result.updates[6]["small_text"] == "Paused"
    else:
        assert "discord.clear" in result.events
    # Deliberately below the threshold: pause accounting is a separate baseline bug.
    assert not result.submissions


def test_pause_resume_without_native_position_preserves_elapsed_timer(run_runtime):
    result = run_runtime([
        poll(0, position=None), poll(3, "paused", position=None),
        poll(60, "paused", position=None), poll(63, position=None),
    ])
    assert result.updates[63]["start_ts"] == 1060


def test_seeks_refresh_presence_timer_without_immediate_scrobble(run_runtime):
    result = run_runtime([
        poll(0), poll(3, position=80), poll(6, position=4), poll(9, position=7),
    ])
    assert [result.updates[at]["start_ts"] for at in (0, 3, 6, 9)] == [1000, 923, 1002, 1002]
    assert not result.submissions


@pytest.mark.parametrize("stop_via_tasks", [False, True])
def test_stop_clears_presence_closes_services_and_publishes_stopped_state(run_runtime, stop_via_tasks):
    result = run_runtime([poll(0), poll(3, position=3)], stop_via_tasks=stop_via_tasks)
    assert result.events[-3:] == ["discord.shutdown", "discord.clear", "discord.close"]
    assert not result.rpc.connected
    for service in result.services.values():
        service.close.assert_called_once_with()
    stopped = result.diagnostics[-1][1]
    assert stopped["rpc_status"] == "stopped"
    assert stopped["discord_status"] == "disconnected"
    assert stopped["track"] is None
    assert stopped["presence_visible"] is False
    assert stopped["album_art_url"] == stopped["track_link"] == ""


def test_stop_closes_background_resolver_if_present(run_runtime):
    result = run_runtime([poll(0), poll(3, position=3)], lookup_delay=30)
    if not result.has_resolver:
        pytest.skip("Baseline has synchronous artwork lookup")
    assert len(result.resolvers) == 1
    worker = result.resolvers[0]
    assert any(event[0] == "request" for event in worker.events)
    assert any(event[0] == "close" for event in worker.events), "runtime must close its artwork worker on stop"
    assert worker.closed
