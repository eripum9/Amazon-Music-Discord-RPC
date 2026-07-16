# MIT License - Copyright (c) 2026 eripum9

import threading
import time

import lastfm
import listenbrainz_scrobbler


def test_listenbrainz_auth_skips_startup_validation(monkeypatch):
    calls = []

    class FakeClient:
        def set_auth_token(self, token, check_validity=True):
            calls.append((token, check_validity))

    class FakeListen:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeErrors:
        ListenBrainzAPIException = Exception

    class FakeLib:
        ListenBrainz = FakeClient
        Listen = FakeListen
        errors = FakeErrors

    monkeypatch.setattr(listenbrainz_scrobbler, "liblistenbrainz", FakeLib)

    listenbrainz_scrobbler.ListenBrainzScrobbler("token")

    assert calls == [("token", False)]


def test_listenbrainz_now_playing_does_not_block(monkeypatch):
    called = threading.Event()

    class FakeClient:
        def set_auth_token(self, token, check_validity=True):
            pass

        def submit_playing_now(self, listen):
            called.set()
            time.sleep(0.5)

    class FakeListen:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeErrors:
        ListenBrainzAPIException = Exception

    class FakeLib:
        ListenBrainz = FakeClient
        Listen = FakeListen
        errors = FakeErrors

    monkeypatch.setattr(listenbrainz_scrobbler, "liblistenbrainz", FakeLib)
    scrobbler = listenbrainz_scrobbler.ListenBrainzScrobbler("token")

    started = time.perf_counter()
    scrobbler.update_now_playing("Song", "Artist", "Album", 180)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.2
    assert called.wait(1)


def test_lastfm_now_playing_does_not_block(monkeypatch):
    called = threading.Event()

    class FakeNetwork:
        def __init__(self, **kwargs):
            pass

        def update_now_playing(self, **kwargs):
            called.set()
            time.sleep(0.5)

    class FakePylast:
        LastFMNetwork = FakeNetwork
        NetworkError = RuntimeError
        MalformedResponseError = ValueError

    monkeypatch.setattr(lastfm, "pylast", FakePylast)
    scrobbler = lastfm.LastFMScrobbler("key", "secret", "session")

    started = time.perf_counter()
    scrobbler.update_now_playing("Song", "Artist", "Album", 180)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.2
    assert called.wait(1)


def test_lastfm_scrobble_waits_in_background_when_busy(monkeypatch):
    update_started = threading.Event()
    release_update = threading.Event()
    scrobbled = threading.Event()

    class FakeNetwork:
        def __init__(self, **kwargs):
            pass

        def update_now_playing(self, **kwargs):
            update_started.set()
            release_update.wait(1)

        def scrobble(self, **kwargs):
            scrobbled.set()

    class FakePylast:
        LastFMNetwork = FakeNetwork
        NetworkError = RuntimeError
        MalformedResponseError = ValueError

    monkeypatch.setattr(lastfm, "pylast", FakePylast)
    scrobbler = lastfm.LastFMScrobbler("key", "secret", "session")
    scrobbler.update_now_playing("Song", "Artist", "Album", 180)
    assert update_started.wait(1)

    started = time.perf_counter()
    scrobbler.scrobble("Song", "Artist", 1000, "Album", 180)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.2
    assert not scrobbled.is_set()
    release_update.set()
    assert scrobbled.wait(1)


def test_lastfm_queued_worker_cannot_submit_after_privacy_enabled(monkeypatch):
    update_started = threading.Event()
    release_update = threading.Event()
    submitted = threading.Event()

    class FakeNetwork:
        def __init__(self, **kwargs):
            pass

        def update_now_playing(self, **kwargs):
            update_started.set()
            release_update.wait(2)

        def scrobble(self, **kwargs):
            submitted.set()

    class FakePylast:
        LastFMNetwork = FakeNetwork
        NetworkError = RuntimeError
        MalformedResponseError = ValueError

    monkeypatch.setattr(lastfm, "pylast", FakePylast)
    scrobbler = lastfm.LastFMScrobbler("key", "secret", "session")
    scrobbler.update_now_playing("Song", "Artist")
    assert update_started.wait(1)
    scrobbler.scrobble("Song", "Artist", 1000)
    privacy = threading.Thread(target=scrobbler.set_privacy, args=(True,))
    privacy.start()
    release_update.set()
    privacy.join(2)
    assert not privacy.is_alive()
    assert scrobbler._tasks.join(1)
    assert not submitted.is_set()


def test_listenbrainz_queued_worker_cannot_submit_after_privacy_enabled(monkeypatch):
    update_started = threading.Event()
    release_update = threading.Event()
    submitted = threading.Event()

    class FakeClient:
        def set_auth_token(self, token, check_validity=True):
            pass

        def submit_playing_now(self, listen):
            update_started.set()
            release_update.wait(2)

        def submit_single_listen(self, listen):
            submitted.set()

    class FakeListen:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeErrors:
        ListenBrainzAPIException = RuntimeError

    class FakeLib:
        ListenBrainz = FakeClient
        Listen = FakeListen
        errors = FakeErrors

    monkeypatch.setattr(listenbrainz_scrobbler, "liblistenbrainz", FakeLib)
    scrobbler = listenbrainz_scrobbler.ListenBrainzScrobbler("token")
    scrobbler.update_now_playing("Song", "Artist")
    assert update_started.wait(1)
    scrobbler.scrobble("Song", "Artist", 1000)
    privacy = threading.Thread(target=scrobbler.set_privacy, args=(True,))
    privacy.start()
    release_update.set()
    privacy.join(2)
    assert not privacy.is_alive()
    assert scrobbler._tasks.join(1)
    assert not submitted.is_set()
