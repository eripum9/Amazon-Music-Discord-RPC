# MIT License - Copyright (c) 2026 eripum9

import importlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time

import pytest
import requests


@pytest.mark.parametrize("phase", ["body", "headers"])
def test_artwork_http_deadline_bounds_a_trickling_body(phase):
    get_json = getattr(importlib.import_module("album_art"), "_get_json", None)
    if get_json is None:
        pytest.skip("Baseline has no streaming artwork HTTP helper")

    stop = threading.Event()
    body = b'{"value":"' + b"x" * 80 + b'"}'

    class TrickleHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            try:
                if phase == "headers":
                    for byte in b"HTTP/1.0 200 OK\r\nX-Slow: " + b"x" * 80 + b"\r\n\r\n":
                        if stop.wait(0.02):
                            return
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                for byte in body:
                    if stop.wait(0.02):
                        break
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), TrickleHandler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        start = time.monotonic()
        with pytest.raises(requests.RequestException):
            get_json(f"http://127.0.0.1:{server.server_port}/art", start + 0.6)
        elapsed = time.monotonic() - start
        # Bytes arrive faster than the socket timeout; the total deadline must win.
        assert elapsed < 1.3, f"0.6s artwork budget took {elapsed:.2f}s under a trickling response"
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
    assert not thread.is_alive()


@pytest.fixture
def controlled_http():
    stop, started = threading.Event(), threading.Event()
    paths = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            paths.append(self.path)
            self.send_response(302 if self.path == "/redirect" else 200)
            if self.path == "/redirect":
                self.send_header("Location", "https://outside.test/never")
            self.end_headers()
            started.set()
            try:
                if self.path == "/slow":
                    while not stop.wait(0.02):
                        self.wfile.write(b" ")
                        self.wfile.flush()
                elif self.path == "/fast":
                    self.wfile.write(
                        b'{"results":[{"trackName":"Song","artistName":"Artist","collectionName":"Album",'
                        b'"artworkUrl100":"https://art.test/100x100bb.jpg","trackTimeMillis":200000}]}'
                    )
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", started, paths
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
    assert not thread.is_alive()


def test_real_slow_provider_leaves_time_for_fallback(monkeypatch, controlled_http):
    artwork = importlib.import_module("album_art")
    base, _, paths = controlled_http
    real_get_json = artwork._get_json

    def routed_json(url, deadline, cancel_event=None):
        path = "/slow" if "deezer" in url else "/fast"
        return real_get_json(base + path, deadline, cancel_event)

    monkeypatch.setattr(artwork, "_get_json", routed_json)
    start = time.monotonic()
    match, _ = artwork.find_best_match("Song", "Artist", album="Album", duration=200,
                                       deezer_enabled=True, itunes_enabled=True, budget=2)
    assert match["source"] == "itunes"
    assert paths == ["/slow", "/fast"]
    assert time.monotonic() - start < 2.7


def test_cancellation_interrupts_real_body_and_frees_worker(controlled_http):
    from artwork_resolver import ArtworkResolver

    artwork = importlib.import_module("album_art")
    base, started, paths = controlled_http
    done = threading.Event()

    def lookup(path, cancel_event):
        payload = artwork._get_json(base + path, time.monotonic() + 5, cancel_event)
        done.set()
        return (payload, "", "", 0)

    resolver = ArtworkResolver(lookup)
    try:
        resolver.request("old", path="/slow")
        assert started.wait(1)
        start = time.monotonic()
        resolver.request("new", path="/fast")
        assert done.wait(1), "cancelled body must not monopolize the worker"
        with resolver._cond:
            assert resolver._cond.wait_for(lambda: resolver._result is not None, timeout=1)
        assert resolver.result("old") is None
        assert resolver.result("new")[0]["results"][0]["trackName"] == "Song"
        assert time.monotonic() - start < 1.3
        assert paths == ["/slow", "/fast"]
    finally:
        resolver.close(timeout=1)
    assert not resolver._thread.is_alive()


def test_http_size_limit_and_redirects_fail_closed(monkeypatch, controlled_http):
    artwork = importlib.import_module("album_art")
    base, _, paths = controlled_http
    monkeypatch.setattr(artwork, "MAX_RESPONSE_BYTES", 16)
    with pytest.raises(ValueError, match="too large"):
        artwork._get_json(base + "/fast", time.monotonic() + 2)
    with pytest.raises(requests.HTTPError):
        artwork._get_json(base + "/redirect", time.monotonic() + 2)
    assert paths == ["/fast", "/redirect"]


@pytest.mark.parametrize("url", [
    "http://api.deezer.com/search", "https://outside.test/search",
    "https://user:secret@api.deezer.com/search", "https://api.deezer.com:444/search",
])
def test_http_rejects_unapproved_endpoints_without_connecting(url):
    artwork = importlib.import_module("album_art")
    with pytest.raises(requests.RequestException, match="endpoint"):
        artwork._get_json(url, time.monotonic() + 2)
