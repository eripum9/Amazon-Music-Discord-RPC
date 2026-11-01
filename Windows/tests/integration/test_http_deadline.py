# MIT License - Copyright (c) 2026 eripum9

import importlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import time

import pytest
import requests


def test_artwork_http_deadline_bounds_a_trickling_body():
    get_json = getattr(importlib.import_module("album_art"), "_get_json", None)
    if get_json is None:
        pytest.skip("Baseline has no streaming artwork HTTP helper")

    stop = threading.Event()
    body = b'{"value":"' + b"x" * 80 + b'"}'

    class TrickleHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                for byte in body:
                    if stop.wait(0.02):
                        break
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    server = HTTPServer(("127.0.0.1", 0), TrickleHandler)
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
