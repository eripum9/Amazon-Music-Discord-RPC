# MIT License - Copyright (c) 2026 eripum9

import threading

import pytest

from artwork_resolver import ArtworkResolver

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


def test_stop_and_private_restart_never_start_queued_track(run_runtime):
    entered, release = threading.Event(), threading.Event()
    workers, calls = [], []

    def make_resolver(lookup):
        worker = ArtworkResolver(lookup)
        workers.append(worker)
        return worker

    def lookup(title, **context):
        calls.append(title)
        entered.set()
        assert release.wait(2)
        assert context["cancel_event"].is_set()
        return ("https://art.test/obsolete", "obsolete", "", 200)

    def transition(sample, runtime):
        if sample.at == 3:
            assert entered.wait(1)
        if sample.at == 6:
            # Stop is the controller's synchronous privacy/restart boundary.
            assert workers[0]._pending is not None
            runtime.current_config = {**runtime.current_config, "privacy_private_session": True}
            runtime.clear_current_presence("private session enabled")
            runtime._set_rpc_running(False)

    try:
        result = run_runtime([poll(0), poll(3, title="Next"), poll(6)],
                             lookup=lookup, before_sample=transition, resolver_factory=make_resolver)
        assert calls == ["Song"]
        assert result.art_lookup.call_count == 1
    finally:
        release.set()
        for worker in workers:
            worker.close(timeout=1)
    assert all(not worker._thread.is_alive() for worker in workers)
    assert workers[0].result(("song", "artist", "album")) is None
    private = run_runtime([poll(0), poll(100)], privacy_private_session=True,
                          resolver_factory=make_resolver)
    private.art_lookup.assert_not_called()
    assert not private.resolvers


@pytest.mark.parametrize("status", ["playing", "paused"])
def test_hidden_track_cancels_pending_results_even_when_scrobbling_allowed(run_runtime, status):
    result = run_runtime([
        poll(0, status), poll(3, status, album="Secret"), poll(6, status, album="Secret"),
    ], privacy_blocked_keywords="Secret", privacy_disable_scrobbling=False, lookup_delay=6)
    assert any(event[0] == "cancel" for event in result.resolvers[0].events)
    assert not any(event[0] == "complete" for event in result.resolvers[0].events)
    assert result.art_lookup.call_count == 0
    hidden = [data for _, data in result.diagnostics if data.get("privacy", {}).get("hidden")]
    assert len(hidden) == 2
    assert all(data["track_link"] == data["album_art_url"] == "" for data in hidden)


@pytest.mark.parametrize("status", ["playing", "paused"])
def test_manual_correction_with_unchanged_identity_invalidates_result(run_runtime, status):
    def choose(sample, runtime):
        if sample.at == 3:
            runtime._resolved_cache["Song|Artist"] = ("Song", "Artist")
            runtime._store_resolved_track("Song|Artist", {
                "title": "Song", "artist": "Artist", "album": "Chosen album",
                "art_url": "https://art.test/chosen", "track_link": "https://deezer.test/chosen",
                "duration": 210,
            })

    result = run_runtime([poll(0, status), poll(3, status), poll(6, status)],
                         lookup_delay=6, before_sample=choose)
    for at in (3, 6):
        assert result.updates[at]["album_name"] == "Chosen album"
        assert result.updates[at]["album_art_url"] == "https://art.test/chosen"
        assert result.updates[at]["buttons"][0]["url"] == "https://deezer.test/chosen"
    result.art_lookup.assert_not_called()


def test_initial_paused_new_track_does_not_keep_previous_art_album_or_link(run_runtime):
    result = run_runtime([poll(0), poll(3, "paused", title="Next", album=""),
                          poll(6, "paused", title="Next", album="")], lookup_delay=3)
    at_skip = result.updates[3]
    assert at_skip["album_art_url"] == at_skip["album_name"] == ""
    assert at_skip["buttons"] is None
    assert result.updates[6]["album_name"] == "Next album"
    assert result.updates[6]["buttons"][0]["url"] == "https://deezer.test/Next"


def test_native_duration_remains_authoritative_after_async_resolution(run_runtime):
    result = run_runtime([poll(0, duration=300), poll(3, duration=300, position=3),
                          poll(100, duration=300, position=100),
                          poll(150, duration=300, position=150)], lookup_delay=3)
    assert [at for at, service, _ in result.submissions if service == "lastfm"] == [150]
    assert result.updates[100]["duration"] == 300
    assert result.updates[150]["start_ts"] == 1000


@pytest.mark.parametrize("status", ["playing", "paused"])
def test_custom_art_wins_after_async_result(run_runtime, status):
    result = run_runtime([poll(0, status), poll(3, status), poll(6, status)],
                         lookup_delay=3, custom_albums=[{
                             "album": "Custom", "aliases": ["Song album"],
                             "art_url": "https://art.test/custom",
                         }])
    assert result.updates[3]["album_art_url"] == result.updates[6]["album_art_url"] == "https://art.test/custom"
    result.art_lookup.assert_called_once()


def test_paused_results_are_consumed_even_when_paused_presence_is_hidden(run_runtime):
    result = run_runtime([poll(0, "paused"), poll(3, "paused"), poll(6, "paused")],
                         lookup_delay=3, show_paused=False)
    assert not result.updates
    result.art_lookup.assert_called_once()
    assert result.diagnostics[-2][1]["track_link"] == "https://deezer.test/Song"


def test_dynamic_private_gate_cancels_before_completion(run_runtime):
    def enable_private(sample, runtime):
        if sample.at == 3:
            runtime.current_config = {**runtime.current_config, "privacy_private_session": True}

    result = run_runtime([poll(0), poll(3), poll(6)], lookup_delay=6, before_sample=enable_private)
    result.art_lookup.assert_not_called()
    assert set(result.updates) == {0}
    hidden = [data for _, data in result.diagnostics if data.get("privacy", {}).get("hidden")]
    assert len(hidden) == 2


def test_late_native_metadata_cancels_inflight_lookup_while_paused(run_runtime):
    result = run_runtime([
        poll(0), poll(3, "paused", native=True, album="Canonical",
                      _amazon_art_url="https://art.test/native"),
        poll(6, "paused", native=True, album="Canonical",
             _amazon_art_url="https://art.test/native"),
    ], amazon_devtools_enabled=True, lookup_delay=6)
    result.art_lookup.assert_not_called()
    assert result.updates[6]["album_name"] == "Canonical"
    assert result.updates[6]["album_art_url"] == "https://art.test/native"
    assert result.updates[6]["buttons"] is None


def test_empty_paused_identity_clears_previous_metadata(run_runtime):
    result = run_runtime([poll(0), poll(3, "paused", title="", artist=""),
                          poll(6, "paused", title="", artist="")], lookup_delay=6)
    assert set(result.updates) == {0}
    result.art_lookup.assert_not_called()
    assert result.diagnostics[-2][1]["album_art_url"] == ""
    assert result.diagnostics[-2][1]["track_link"] == ""
