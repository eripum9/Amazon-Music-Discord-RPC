# MIT License - Copyright (c) 2026 eripum9

from MacOS import config
from MacOS.runtime import MacRuntime, RuntimeDependencies


class Clock:
    def __init__(self, value=1_000.0):
        self.value = value

    def __call__(self):
        return self.value


class FakeRPC:
    def __init__(self, client_id):
        self.client_id = client_id
        self.connected = True
        self.updates = []
        self.clears = 0
        self.shutdowns = 0

    def update(self, **payload):
        self.updates.append(payload)

    def clear(self):
        self.clears += 1

    def shutdown(self):
        self.shutdowns += 1
        self.connected = False


class FakeScrobbler:
    def __init__(self, *args):
        self.args = args
        self.now_playing = []
        self.scrobbles = []
        self.closed = False

    def update_now_playing(self, *args):
        self.now_playing.append(args)

    def scrobble(self, *args):
        self.scrobbles.append(args)

    def close(self):
        self.closed = True


def settings(**overrides):
    value = {**config.DEFAULTS, config.CONFIG_REVISION_KEY: 0}
    value.update(
        {
            "amazon_devtools_enabled": True,
            "amazon_devtools_auto_launch": False,
            "deezer_lookup_enabled": False,
            "itunes_lookup_enabled": False,
        }
    )
    value.update(overrides)
    return value


def track(**overrides):
    value = {
        "status": "found",
        "title": "DevTools Song",
        "artist": "Artist",
        "album": "Album",
        "art_url": "https://m.media-amazon.com/images/I/example.jpg",
        "track_link": "https://music.amazon.com/tracks/ABCDEFGHIJ",
        "position": 20,
        "duration": 200,
        "playback_status": "playing",
        "source": "amazon_devtools",
    }
    value.update(overrides)
    return value


def build_runtime(
    current_settings,
    *,
    devtools=None,
    fallback=None,
    clock=None,
    amazon_running=False,
    art_lookup=None,
):
    rpc_instances = []
    lastfm_instances = []
    listenbrainz_instances = []
    restarts = []
    fallback_calls = []

    def rpc_factory(client_id):
        instance = FakeRPC(client_id)
        rpc_instances.append(instance)
        return instance

    def lastfm_factory(*args):
        instance = FakeScrobbler(*args)
        lastfm_instances.append(instance)
        return instance

    def listenbrainz_factory(*args):
        instance = FakeScrobbler(*args)
        listenbrainz_instances.append(instance)
        return instance

    def fallback_reader():
        fallback_calls.append(True)
        return fallback

    dependencies = RuntimeDependencies(
        discord_factory=rpc_factory,
        lastfm_factory=lastfm_factory,
        listenbrainz_factory=listenbrainz_factory,
        art_lookup=art_lookup or (lambda *args, **kwargs: ("", "", "", 0)),
        devtools_track=lambda *args: devtools,
        devtools_launch=lambda: {"ok": False, "status": "restart_required", "restart_required": True},
        devtools_restart=lambda: restarts.append(True) or {"ok": True, "status": "ready", "port": 55000},
        devtools_status=lambda: {},
        amazon_running=lambda: amazon_running,
        now_playing_track=fallback_reader,
        process_names=lambda: set(),
        network_event=lambda *args: None,
        clock=clock or Clock(),
    )
    runtime = MacRuntime(dependencies, settings_loader=lambda: current_settings)
    return runtime, rpc_instances, lastfm_instances, listenbrainz_instances, restarts, fallback_calls


def test_devtools_is_primary_and_builds_full_discord_payload():
    runtime, rpcs, _, _, _, fallback_calls = build_runtime(settings(), devtools=track())
    snapshot = runtime.tick()
    assert fallback_calls == []
    assert snapshot["source"] == "Amazon metadata"
    assert snapshot["track"]["title"] == "DevTools Song"
    payload = rpcs[0].updates[-1]
    assert payload["album_name"] == "Album"
    assert payload["album_art_url"].startswith("https://m.media-amazon.com/")
    assert payload["start_ts"] == 980
    assert payload["duration"] == 200
    assert payload["buttons"][0]["label"] == "Listen on Amazon Music"


def test_now_playing_is_used_only_when_devtools_is_unavailable():
    fallback = {
        "title": "Fallback Song",
        "artist": "Fallback Artist",
        "album": "Fallback Album",
        "status": "playing",
        "position": 5,
        "duration": 100,
        "source": "macos_now_playing",
    }
    runtime, _, _, _, _, fallback_calls = build_runtime(
        settings(),
        devtools={"status": "unavailable", "detail": "no listener"},
        fallback=fallback,
    )
    snapshot = runtime.tick()
    assert fallback_calls == [True]
    assert snapshot["track"]["title"] == "Fallback Song"
    assert snapshot["source"] == "macOS fallback"


def test_pause_state_uses_pause_asset_and_respects_show_paused():
    runtime, rpcs, _, _, _, _ = build_runtime(
        settings(show_paused=True), devtools=track(playback_status="paused")
    )
    runtime.tick()
    assert rpcs[0].updates[-1]["small_text"] == "Paused"
    assert "pause_icon.png" in rpcs[0].updates[-1]["small_image"]

    hidden_runtime, hidden_rpcs, _, _, _, _ = build_runtime(
        settings(show_paused=False), devtools=track(playback_status="paused")
    )
    snapshot = hidden_runtime.tick()
    assert hidden_rpcs[0].updates == []
    assert snapshot["presence_visible"] is False


def test_scrobblers_receive_now_playing_and_threshold_scrobble():
    current = settings(
        lastfm_enabled=True,
        lastfm_session_key="session",
        listenbrainz_enabled=True,
        listenbrainz_token="token",
    )
    runtime, _, lastfm, listenbrainz, _, _ = build_runtime(
        current, devtools=track(position=120, duration=200)
    )
    runtime.tick()
    assert lastfm[0].now_playing[0][:3] == ("DevTools Song", "Artist", "Album")
    assert listenbrainz[0].now_playing[0][:3] == ("DevTools Song", "Artist", "Album")
    assert len(lastfm[0].scrobbles) == 1
    assert len(listenbrainz[0].scrobbles) == 1


def test_private_session_blocks_presence_and_scrobbling():
    current = settings(
        privacy_private_session=True,
        privacy_disable_scrobbling=True,
        lastfm_enabled=True,
        lastfm_session_key="session",
    )
    runtime, rpcs, lastfm, _, _, _ = build_runtime(
        current, devtools=track(position=150, duration=200)
    )
    snapshot = runtime.tick()
    assert rpcs[0].updates == []
    assert lastfm[0].now_playing == []
    assert lastfm[0].scrobbles == []
    assert snapshot["track"]["title"] == "Hidden by privacy controls"
    assert snapshot["privacy"]["reason"] == "Private session enabled"
    assert snapshot["raw_track"] == {}
    assert snapshot["album_art_url"] == ""
    assert snapshot["track_link"] == ""
    assert "title" not in snapshot["amazon_devtools"]
    assert "artist" not in snapshot["amazon_devtools"]


def test_keyword_privacy_blocks_scrobbling_by_default():
    current = settings(
        privacy_blocked_keywords="devtools",
        privacy_disable_scrobbling=True,
        lastfm_enabled=True,
        lastfm_session_key="session",
    )
    runtime, rpcs, lastfm, _, _, _ = build_runtime(
        current, devtools=track(position=150, duration=200)
    )
    snapshot = runtime.tick()
    assert rpcs[0].updates == []
    assert lastfm[0].now_playing == []
    assert lastfm[0].scrobbles == []
    assert snapshot["raw_track"] == {}
    assert "title" not in snapshot["amazon_devtools"]


def test_hidden_track_never_leaks_to_artwork_when_scrobbling_is_allowed():
    artwork_calls = []
    current = settings(
        privacy_private_session=True,
        privacy_disable_scrobbling=False,
        lastfm_enabled=True,
        lastfm_session_key="session",
    )
    runtime, rpcs, lastfm, _, _, _ = build_runtime(
        current,
        devtools=track(art_url="", position=150, duration=200),
        art_lookup=lambda *args, **kwargs: artwork_calls.append((args, kwargs))
        or ("", "", "", 0),
    )

    snapshot = runtime.tick()
    assert rpcs[0].updates == []
    assert artwork_calls == []
    assert lastfm[0].args[-1] is False
    assert lastfm[0].now_playing
    assert lastfm[0].scrobbles
    assert snapshot["raw_track"] == {}


def test_private_interval_never_counts_toward_later_scrobble():
    clock = Clock(1_000)
    current = settings(
        lastfm_enabled=True,
        lastfm_session_key="session",
        privacy_disable_scrobbling=True,
    )
    current_track = {"value": track(position=20, duration=200)}
    runtime, _, lastfm, _, _, _ = build_runtime(
        current,
        devtools=current_track["value"],
        clock=clock,
    )
    runtime.dependencies.devtools_track = lambda *args: current_track["value"]

    runtime.tick()
    assert lastfm[0].now_playing

    current["privacy_private_session"] = True
    current_track["value"] = track(position=150, duration=200)
    clock.value += 130
    hidden = runtime.tick()
    assert hidden["raw_track"] == {}
    assert lastfm[0].scrobbles == []

    current["privacy_private_session"] = False
    visible_again = runtime.tick()
    assert visible_again["track"]["title"] == "DevTools Song"
    assert lastfm[0].scrobbles == []

    current_track["value"] = track(position=199, duration=200)
    clock.value += 49
    runtime.tick()
    assert lastfm[0].scrobbles == []


def test_auto_launch_never_restarts_a_running_amazon_without_explicit_consent():
    clock = Clock(1_000)
    current = settings(amazon_devtools_auto_launch=True)
    runtime, _, _, _, restarts, _ = build_runtime(
        current,
        devtools={"status": "unavailable", "detail": "no listener"},
        fallback=None,
        clock=clock,
        amazon_running=True,
    )
    runtime.tick()
    assert restarts == []
    clock.value += 30
    snapshot = runtime.tick()
    assert restarts == []
    assert snapshot["amazon_devtools"]["status"] == "restart_required"


def test_disabling_listener_requires_an_explicit_runtime_action(monkeypatch):
    current = settings()
    runtime, _, _, _, _, _ = build_runtime(current, devtools=track())
    calls = []
    runtime.dependencies.devtools_disable = (
        lambda **kwargs: calls.append(kwargs)
        or {"ok": True, "status": "disabled", "stopped": [42]}
    )
    saved = {
        **current,
        "amazon_devtools_enabled": False,
        "amazon_devtools_auto_launch": False,
    }
    monkeypatch.setattr(config, "update_config_fields", lambda updates: {**saved, **updates})
    monkeypatch.setattr(runtime, "reload_config", lambda value: setattr(runtime, "_settings", value))

    result = runtime.disable_enhanced_metadata(relaunch=True)
    assert result["status"] == "disabled"
    assert calls == [{"relaunch": True}]
    assert runtime._settings["amazon_devtools_enabled"] is False
    assert runtime._settings["amazon_devtools_auto_launch"] is False
    assert runtime.snapshot()["amazon_devtools"]["enabled"] is False


def test_no_track_clears_an_existing_presence():
    state = {"value": track()}
    current = settings()
    runtime, rpcs, _, _, _, _ = build_runtime(current, devtools=None)
    runtime.dependencies.devtools_track = lambda *args: state["value"]
    runtime.tick()
    assert rpcs[0].updates
    state["value"] = {"status": "unavailable"}
    runtime.dependencies.now_playing_track = lambda: None
    snapshot = runtime.tick()
    assert rpcs[0].clears == 1
    assert snapshot["track"] is None
    assert snapshot["raw_track"] == {}
    assert snapshot["album_art_url"] == ""
    assert snapshot["track_link"] == ""


def test_enabling_private_session_immediately_clears_diagnostic_metadata(monkeypatch):
    current = settings()
    runtime, _, _, _, _, _ = build_runtime(current, devtools=track())
    assert runtime.tick()["raw_track"]["title"] == "DevTools Song"

    private_settings = {**current, "privacy_private_session": True}
    monkeypatch.setattr(
        config,
        "update_config_fields",
        lambda updates: {**private_settings, **updates},
    )
    monkeypatch.setattr(runtime, "reload_config", lambda saved: setattr(runtime, "_settings", saved))

    runtime.set_private_session(True)
    snapshot = runtime.snapshot()
    assert snapshot["track"]["title"] == "Hidden by privacy controls"
    assert snapshot["raw_track"] == {}
    assert snapshot["album_art_url"] == ""
    assert snapshot["track_link"] == ""
    assert snapshot["correction_suggested"] is False
    assert "title" not in snapshot["amazon_devtools"]


def test_wrong_song_suggestion_matches_windows_game_mode_behavior():
    suspicious = track(title="Same", artist="Same")
    runtime, _, _, _, _, _ = build_runtime(settings(), devtools=suspicious)
    assert runtime.tick()["correction_suggested"] is True

    game_runtime, _, _, _, _, _ = build_runtime(
        settings(game_mode_enabled=True), devtools=suspicious
    )
    assert game_runtime.tick()["correction_suggested"] is False

    mapped_runtime, _, _, _, _, _ = build_runtime(
        settings(
            track_mappings={
                "same|same": {
                    "title": "Corrected",
                    "artist": "Artist",
                }
            }
        ),
        devtools=suspicious,
    )
    snapshot = mapped_runtime.tick()
    assert snapshot["correction_suggested"] is False
    assert snapshot["track"]["title"] == "Corrected"


def test_unremembered_correction_applies_for_only_the_runtime_session():
    current = settings()
    runtime, _, _, _, _, _ = build_runtime(current, devtools=track())
    assert runtime.tick()["track"]["title"] == "DevTools Song"

    runtime.apply_correction(
        "DevTools Song",
        "Artist",
        {
            "title": "Session Title",
            "artist": "Session Artist",
            "album": "Session Album",
            "art_url": "https://m.media-amazon.com/images/I/session.jpg",
            "track_link": "https://music.amazon.com/tracks/ABCDEFGHIJ",
            "duration": 201,
        },
        remember=False,
    )
    snapshot = runtime.tick()
    assert snapshot["track"]["title"] == "Session Title"
    assert snapshot["track"]["artist"] == "Session Artist"
    assert current["track_mappings"] == {}
