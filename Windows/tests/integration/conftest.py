# MIT License - Copyright (c) 2026 eripum9

"""Exercise the real playback loop without desktop apps or persistent state."""

import importlib
import socket
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests


def poll(at, status="playing", *, native=False, missing=False, **fields):
    return SimpleNamespace(at=at, native=native, track=None if missing else {
        "title": "Song", "artist": "Artist", "album": "Album",
        "status": status, "position": 0, "duration": 200, **fields,
    })


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Unexpected persistent-state, network, process, or desktop access")

    for name in ("APPDATA", "LOCALAPPDATA", "HOME", "USERPROFILE"):
        monkeypatch.setenv(name, str(tmp_path))
    monkeypatch.chdir(tmp_path)
    config = importlib.import_module("config")
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    for name in ("load_config", "update_config_fields", "mutate_config_fields", "WindowsCredentialStore"):
        monkeypatch.setattr(config, name, forbidden)
    credentials = importlib.import_module("credential_store")
    monkeypatch.setattr(credentials, "WindowsCredentialStore", forbidden)
    audit = importlib.import_module("network_audit")
    monkeypatch.setattr(audit, "record_network_event", Mock())
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)

    # Only the optional HTTP deadline test may use a socket, on loopback.
    connect = socket.socket.connect
    def loopback_only(sock, address):
        if not isinstance(address, tuple) or address[0] != "127.0.0.1":
            forbidden()
        return connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", loopback_only)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    request = requests.sessions.Session.request
    def local_request(session, method, url, **kwargs):
        if not url.startswith("http://127.0.0.1:"):
            forbidden()
        session.trust_env = False
        return request(session, method, url, **kwargs)

    monkeypatch.setattr(requests.sessions.Session, "request", local_request)
    return forbidden


@pytest.fixture
def run_runtime(monkeypatch, tmp_path, isolated_environment):
    main = importlib.import_module("desktop_runtime")
    state = importlib.import_module("rpc_state")
    real_discord = main.DiscordRPC

    def run(samples, *, lookup=None, lookup_delay=0, before_sample=None,
            stop_via_tasks=False, **overrides):
        cursor = 0
        updates, diagnostics, submissions, events, resolvers = [], [], [], [], []

        def current():
            return samples[cursor]

        class FakeDiscord(real_discord):
            def __init__(self, _client_id):
                self.connected = True
                self._closed = False
                self.rpc = SimpleNamespace(
                    clear=lambda: events.append("discord.clear"),
                    close=lambda: events.append("discord.close"),
                )

            def update(self, **payload):
                updates.append((current().at, payload))

            def clear(self):
                self.rpc.clear()

            def shutdown(self):
                events.append("discord.shutdown")
                # Keep the real adapter's clear/close ordering at the boundary.
                super().shutdown()

        rpc = FakeDiscord("")
        art_lookup = Mock(side_effect=lookup or (lambda title, artist, **_kw: (
            f"https://art.test/{title}", f"{title} album",
            f"https://deezer.test/{title}", 200,
        )))

        class ScheduledResolver:
            """Request/result contract; completion follows fake time, not threads."""

            def __init__(self, lookup):
                self.lookup = lookup
                self.wanted = None
                self.pending = None
                self.outcome = None
                self.closed = False
                self.events = []
                resolvers.append(self)

            def request(self, key, **context):
                self.events.append(("request", key))
                if key == self.wanted:
                    return False
                self.wanted = key
                self.pending = (current().at + lookup_delay, context)
                self.outcome = None
                self.complete()
                return True

            def complete(self):
                if self.pending and current().at >= self.pending[0] and not self.closed:
                    _, context = self.pending
                    self.pending = None
                    self.outcome = self.lookup(**context)
                    self.events.append(("complete", self.wanted))

            def result(self, key):
                self.events.append(("result", key))
                self.complete()
                return self.outcome if key == self.wanted else None

            def cancel(self):
                self.events.append(("cancel", self.wanted))
                self.wanted = self.pending = self.outcome = None

            def close(self, *_args, **_kwargs):
                self.events.append(("close", self.wanted))
                self.closed = True
                self.cancel()

        def sleep(_seconds):
            nonlocal cursor
            if cursor == len(samples) - 1:
                if stop_via_tasks:
                    main.tasks.stopping = True
                else:
                    main.rpc_running = False
                return
            cursor += 1
            if before_sample:
                before_sample(current(), main)
            for resolver in resolvers:
                resolver.complete()

        def read_track():
            return dict(current().track) if current().track else None

        def read_native(*_args, **_kwargs):
            track = current().track
            if not current().native or not track:
                return {"status": "unavailable"}
            return {**track, "status": "found", "playback_status": track["status"],
                    "art_url": track.get("_amazon_art_url", ""),
                    "track_link": track.get("_amazon_track_link", "")}

        clock = SimpleNamespace(time=lambda: 1000 + current().at,
                                monotonic=lambda: current().at, sleep=sleep)
        monkeypatch.setattr(main, "time", clock)
        monkeypatch.setattr(state, "time", clock)
        monkeypatch.setattr(main, "rpc_running", True)
        monkeypatch.setattr(main, "active_rpc", None)
        monkeypatch.setattr(main, "active_scrobblers", ())
        monkeypatch.setattr(main, "_current_track_raw", None)
        monkeypatch.setattr(main, "application_state", main.ApplicationState())
        monkeypatch.setattr(main, "tasks", SimpleNamespace(stopping=False, start=isolated_environment))
        timing = state.TrackTimingState()
        monkeypatch.setattr(main, "_timing_state", timing)
        monkeypatch.setattr(main, "_track_timing_cache", timing.cache)
        store = state.ResolvedTrackStore()
        for name, value in (("_resolved_store", store), ("_resolved_cache", store.cache),
                            ("_resolved_track_info", store.track_info), ("_skipped_keys", store.skipped_keys),
                            ("_wrong_song_prompted_keys", set())):
            monkeypatch.setattr(main, name, value)
        for name in ("LOG_DIR", "LOG_PATH", "EVENT_LOG_PATH", "DIAGNOSTICS_PATH", "COMMAND_PATH", "CONFIG_PATH"):
            monkeypatch.setattr(main, name, str(tmp_path / name))
        for name in ("load_config", "update_config_fields", "mutate_config_fields",
                     "_run_picker_async", "_prompt_wrong_song_async", "get_notification_track_sync",
                     "launch_amazon_music_devtools", "restart_amazon_music_devtools", "amazon_music_is_running"):
            monkeypatch.setattr(main, name, isolated_environment)
        monkeypatch.setattr(main, "_amazify_metadata_owner", lambda **_kw: {})
        monkeypatch.setattr(main, "_amazify_compat_snapshot", lambda: {})
        monkeypatch.setattr(main, "_should_prompt_wrong_song", lambda *_args: False)
        monkeypatch.setattr(main, "_write_diagnostics_state", lambda **data: diagnostics.append((current().at, data)))
        monkeypatch.setattr(main, "DiscordRPC", lambda _client_id: rpc)
        monkeypatch.setattr(main, "get_track_sync", read_track)
        monkeypatch.setattr(main, "get_devtools_track_sync", read_native)
        monkeypatch.setattr(main, "get_album_art", art_lookup)
        has_resolver = hasattr(main, "ArtworkResolver")
        if has_resolver:
            monkeypatch.setattr(main, "ArtworkResolver", ScheduledResolver)

        services = {}
        for module, factory, name in (("lastfm", "LastFMScrobbler", "lastfm"),
                                      ("listenbrainz_scrobbler", "ListenBrainzScrobbler", "listenbrainz")):
            service = Mock()
            service.scrobble.side_effect = lambda *args, name=name: submissions.append((current().at, name, args))
            service.close.side_effect = lambda name=name: events.append(f"{name}.close")
            services[name] = service
            monkeypatch.setitem(sys.modules, module, SimpleNamespace(**{factory: Mock(return_value=service)}))
        monkeypatch.setattr(main, "current_config", {
            "lastfm_enabled": True, "lastfm_api_key": "test-key", "lastfm_api_secret": "test-secret",
            "lastfm_session_key": "test-session", "listenbrainz_enabled": True,
            "listenbrainz_token": "test-token", "song_link_enabled": True,
            "song_link_provider": "deezer", **overrides,
        })

        main.rpc_loop()

        assert cursor == len(samples) - 1
        assert not [data["last_error"] for _, data in diagnostics if data.get("last_error")]
        assert main.active_rpc is None
        assert main.active_scrobblers == ()
        return SimpleNamespace(updates=dict(updates), diagnostics=diagnostics, submissions=submissions,
                               events=events, services=services, art_lookup=art_lookup,
                               resolvers=resolvers, has_resolver=has_resolver, rpc=rpc)

    return run
