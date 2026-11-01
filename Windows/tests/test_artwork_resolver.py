# MIT License - Copyright (c) 2026 eripum9

import ast
import os
import threading

import artwork_resolver
from artwork_resolver import ArtworkResolver, lookup_key


def _resolver(results=None, calls=None):
    calls = [] if calls is None else calls

    def lookup(title, artist, album="", duration=0):
        calls.append((title, artist, album, duration))
        return (results or {}).get(title, ("https://art/" + title, title + " Album", "https://deezer/" + title, 200))

    return ArtworkResolver(lookup, start_thread=False), calls


def test_art_and_deezer_button_share_one_lookup_per_track():
    resolver, calls = _resolver()
    key = lookup_key("Song", "Artist", "Album")
    assert resolver.request(key, title="Song", artist="Artist", album="Album", duration=200) is True
    # The Deezer-button path asks for the same track: no second lookup is queued.
    assert resolver.request(key, title="Song", artist="Artist", album="Album", duration=201) is False
    assert resolver.result(key) is None
    resolver.process_pending()
    assert resolver.process_pending() is False
    assert calls == [("Song", "Artist", "Album", 200)]
    assert resolver.result(key)[1] == "Song Album"


def test_lookup_identity_ignores_duration_and_case():
    assert lookup_key("Song", "Artist", "Album") == lookup_key("song ", "ARTIST", "album")


def test_superseded_request_is_skipped_and_late_result_discarded():
    resolver, calls = _resolver()
    first, second = lookup_key("First", "A"), lookup_key("Second", "A")
    resolver.request(first, title="First", artist="A")
    resolver.request(second, title="Second", artist="A")   # song changed before the lookup started
    resolver.process_pending()
    assert calls == [("Second", "A", "", 0)]
    assert resolver.result(first) is None
    assert resolver.result(second)[1] == "Second Album"

    # A lookup that finishes after the song changed is not published.
    gate, started = threading.Event(), threading.Event()

    def slow_lookup(title, artist, album="", duration=0):
        started.set()
        gate.wait(5)
        return ("https://art/old", "Old Album", "", 0)

    slow = ArtworkResolver(slow_lookup)
    old, new = lookup_key("Old", "A"), lookup_key("New", "A")
    slow.request(old, title="Old", artist="A")
    assert started.wait(5)
    slow.request(new, title="New", artist="A")
    gate.set()
    slow._thread.join(0.2)
    assert slow.result(old) is None


def test_failed_lookup_yields_empty_result_instead_of_raising():
    def boom(**context):
        raise RuntimeError("network")

    resolver = ArtworkResolver(boom, start_thread=False)
    key = lookup_key("Song", "Artist")
    resolver.request(key, title="Song", artist="Artist")
    resolver.process_pending()
    assert resolver.result(key) == artwork_resolver.EMPTY_RESULT


def test_background_thread_delivers_the_result():
    done = threading.Event()

    def lookup(title, artist, album="", duration=0):
        done.set()
        return ("https://art/x", "X", "", 0)

    resolver = ArtworkResolver(lookup)
    key = lookup_key("Song", "Artist")
    resolver.request(key, title="Song", artist="Artist")
    assert done.wait(5)
    for _ in range(100):
        if resolver.result(key):
            break
        threading.Event().wait(0.01)
    assert resolver.result(key)[1] == "X"


def test_playback_loop_never_calls_the_network_lookup_directly():
    # Every artwork/album/button lookup in the runtime goes through the
    # background resolver; get_album_art is only handed to it.
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desktop_runtime.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    direct_calls = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "get_album_art"
    ]
    assert direct_calls == []
