# MIT License - Copyright (c) 2026 eripum9

import threading

from artwork_resolver import ArtworkResolver, lookup_key


def test_shared_lookup_including_misses_and_itunes_results():
    calls = []
    for outcome in ((None, "", "", 0), ("art", "Album", "", 200)):
        resolver = ArtworkResolver(lambda **kw: calls.append(kw) or outcome, start_thread=False)
        key = lookup_key("Song", "Artist", "Album")
        try:
            assert resolver.request(key, title="Song", duration=200)
            assert not resolver.request(key, title="Song", duration=201)
            assert resolver.process_pending()
            assert resolver.result(key) == outcome
            assert not resolver.request(key, title="Song", duration=201)
        finally:
            resolver.close()
    assert len(calls) == 2


def test_close_stops_queued_work_and_idle_thread_without_waiting_for_lookup():
    entered, release = threading.Event(), threading.Event()
    calls = []

    def lookup(title, cancel_event):
        calls.append(title)
        entered.set()
        assert release.wait(2)
        assert cancel_event.is_set()
        return ("old", "old", "", 0)

    resolver = ArtworkResolver(lookup)
    try:
        resolver.request("A", title="A")
        assert entered.wait(1)
        resolver.request("B", title="B")
        resolver.close()
        assert resolver._thread.is_alive()
        assert not resolver.request("C", title="C")
        assert resolver.result("A") is None
    finally:
        release.set()
        resolver.close(timeout=1)
    assert not resolver._thread.is_alive()
    assert calls == ["A"]
    assert resolver.result("B") is None
    # An independent private/restarted session creates no waiting thread.
    private = ArtworkResolver(lookup)
    private.close(timeout=1)
    assert private._thread is None


def test_cancel_and_re_request_same_key_rejects_prior_generation():
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []

    def lookup(cancel_event):
        calls.append(cancel_event)
        if len(calls) == 1:
            entered.set()
            assert release.wait(2)
            return ("obsolete", "", "", 0)
        finished.set()
        return ("current", "", "", 200)

    resolver = ArtworkResolver(lookup)
    try:
        resolver.request("same")
        assert entered.wait(1)
        resolver.cancel()
        assert calls[0].is_set()
        resolver.request("same")
        assert resolver.result("same") is None
        release.set()
        assert finished.wait(1)
        with resolver._cond:
            resolver._cond.wait_for(lambda: resolver._result is not None, timeout=1)
        assert resolver.result("same") == ("current", "", "", 200)
    finally:
        release.set()
        resolver.close(timeout=1)
    assert len(calls) == 2
    assert not resolver._thread.is_alive()


def test_cancelled_pending_job_never_starts_and_idle_worker_exits():
    resolver = ArtworkResolver(lambda **_kw: (_ for _ in ()).throw(AssertionError("not called")),
                               start_thread=False)
    resolver.request("queued")
    resolver.cancel()
    assert not resolver.process_pending()
    resolver.close()
    assert resolver.result("queued") is None


def test_lookup_failure_is_consumable_and_not_retried():
    def fail(**_kw):
        raise ValueError("bad provider")

    resolver = ArtworkResolver(fail, start_thread=False)
    resolver.request("track")
    assert resolver.process_pending()
    assert resolver.result("track") == (None, "", "", 0)
    assert not resolver.request("track")
    resolver.close()
