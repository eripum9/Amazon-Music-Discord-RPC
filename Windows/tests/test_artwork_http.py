# MIT License - Copyright (c) 2026 eripum9

import errno
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import socketserver
import ssl
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

import album_art
import artwork_http as transport

TLS_CERT = Path(__file__).parent / "fixtures" / "loopback_tls.pem"

@pytest.fixture(autouse=True)
def isolated_network(monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
                 "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("no_proxy", "*")
    real_connect = socket.socket.connect

    def local_connect(sock, address):
        assert address[0] == "127.0.0.1", "unexpected external connection"
        return real_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", local_connect)
    yield
    assert not any(thread.name == "artwork-http-deadline" for thread in threading.enumerate())


def test_multiple_addresses_share_one_absolute_tcp_budget(monkeypatch):
    clock, attempts, closed, starts = [0.0], [], [], {}
    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    addresses = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                  ("127.0.0.1", port)) for port in (101, 102, 103)]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a: addresses)

    class PendingSocket:
        def __init__(self, *_a):
            starts[self] = clock[0]

        def setblocking(self, value):
            assert value is False

        def connect(self, address):
            attempts.append(address)
            raise BlockingIOError(errno.EINPROGRESS, "pending")

        def getsockopt(self, *_a):
            return errno.ETIMEDOUT

        def close(self):
            closed.append(self)

    def ready(_readers, writers, _errors, wait):
        clock[0] += wait
        if clock[0] - starts[writers[0]] >= 0.3 - 1e-9:
            return [], writers, []
        return [], [], []

    monkeypatch.setattr(socket, "socket", PendingSocket)
    monkeypatch.setattr(transport.select, "select", ready)
    budget = transport.RequestDeadline(0.55)
    with pytest.raises(requests.Timeout):
        budget.connect(SimpleNamespace(_dns_host="offline.test", port=443,
                                       socket_options=None, source_address=None))
    budget.close()
    assert clock[0] == pytest.approx(0.55)
    assert attempts == [("127.0.0.1", 101), ("127.0.0.1", 102)]
    assert len(closed) == 2


def test_cancel_during_tcp_wait_starts_no_next_address(monkeypatch):
    cancelled = threading.Event()
    closed = []

    class PendingSocket:
        def __init__(self, *_a):
            pass

        def setblocking(self, _value):
            pass

        def connect(self, _address):
            raise BlockingIOError(errno.EINPROGRESS, "pending")

        def close(self):
            closed.append(True)

    def cancel(*_a):
        cancelled.set()
        return [], [], []

    monkeypatch.setattr(socket, "socket", PendingSocket)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", port))
        for port in (101, 102, 103)
    ])
    monkeypatch.setattr(transport.select, "select", cancel)
    with pytest.raises(requests.Timeout):
        transport.RequestDeadline(time.monotonic() + 3, cancelled).connect(
            SimpleNamespace(_dns_host="offline.test", port=443, socket_options=None, source_address=None))
    assert closed == [True]


def test_cancel_during_dns_return_opens_no_socket(monkeypatch):
    cancelled = threading.Event()

    def resolved(*_a):
        cancelled.set()
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", resolved)
    monkeypatch.setattr(socket, "socket", lambda *_a: pytest.fail("socket opened after DNS cancellation"))
    with pytest.raises(requests.Timeout):
        transport.RequestDeadline(time.monotonic() + 3, cancelled).connect(
            SimpleNamespace(_dns_host="offline.test", port=443, socket_options=None, source_address=None))


@pytest.mark.parametrize("cancel", [False, True])
def test_real_tls_stall_is_interrupted_by_deadline_and_cancellation(monkeypatch, cancel):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(2)
    hello, stop = threading.Event(), threading.Event()
    cancelled = threading.Event()
    errors = []
    address = listener.getsockname()

    def accept():
        try:
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(2)
                if connection.recv(4096):
                    hello.set()
                stop.wait(2)
        except OSError:
            pass

    def lookup():
        try:
            album_art._get_json("https://itunes.apple.com/search",
                                time.monotonic() + (5 if cancel else 0.55), cancelled)
        except requests.RequestException as error:
            errors.append(error)

    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_kw: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", address)
    ])
    server = threading.Thread(target=accept, daemon=True)
    worker = threading.Thread(target=lookup, daemon=True)
    start = time.monotonic()
    server.start()
    worker.start()
    try:
        assert hello.wait(1), "TLS ClientHello must arrive before cancellation"
        if cancel:
            start = time.monotonic()
            cancelled.set()
        worker.join(timeout=1.2)
        assert not worker.is_alive(), "TLS handshake ignored cancellation/deadline"
        assert errors
        assert time.monotonic() - start < 1.2
    finally:
        cancelled.set()
        stop.set()
        listener.close()
        server.join(timeout=2)
        worker.join(timeout=2)
    assert not server.is_alive()
    assert not worker.is_alive()


@pytest.mark.parametrize("bundle_env", ["REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"])
def test_requests_proxy_and_ca_environment_are_preserved(monkeypatch, bundle_env, tmp_path):
    bundle = str(tmp_path / "ca.pem")
    monkeypatch.setenv(bundle_env, bundle)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:18080")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")
    observed = []

    def send(session, prepared, **options):
        observed.append(options)
        assert isinstance(session.get_adapter(prepared.url), transport.DeadlineAdapter)
        response = requests.Response()
        response.status_code = 200
        response._content = b"{}"
        response._content_consumed = True
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    assert album_art._get_json("https://itunes.apple.com/search", time.monotonic() + 2) == {}
    assert observed[0]["verify"] == bundle
    assert observed[0]["proxies"]["https"] == "http://127.0.0.1:18080"


def test_real_environment_http_proxy_is_used(monkeypatch):
    seen = []

    class Proxy(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            seen.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
    worker = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")
    worker.start()
    try:
        assert album_art._get_json("http://127.0.0.1:1/art", time.monotonic() + 2) == {}
        assert seen == ["http://127.0.0.1:1/art"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=1)
    assert not worker.is_alive()


@pytest.fixture
def verified_tls_server():
    stop, started = threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            started.set()
            try:
                if self.path == "/slow":
                    while not stop.wait(0.02):
                        self.wfile.write(b" ")
                        self.wfile.flush()
                else:
                    self.wfile.write(b'{"verified":true}')
            except OSError:
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(TLS_CERT)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield server.server_port, started
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
    assert not thread.is_alive()


def route_tls_host(monkeypatch, port):
    resolve = socket.getaddrinfo

    def local_dns(host, service, *args, **kwargs):
        if host == "itunes.apple.com":
            return resolve("127.0.0.1", port, *args, **kwargs)
        assert host == "127.0.0.1"
        return resolve(host, service, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", local_dns)


@pytest.mark.parametrize("bundle_env", ["REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"])
def test_verified_https_honors_real_ca_bundle_and_rejects_untrusted(
        monkeypatch, verified_tls_server, bundle_env):
    port, _ = verified_tls_server
    route_tls_host(monkeypatch, port)
    with pytest.raises(requests.exceptions.SSLError):
        album_art._get_json("https://itunes.apple.com/fast", time.monotonic() + 2)
    monkeypatch.setenv(bundle_env, str(TLS_CERT))
    assert album_art._get_json("https://itunes.apple.com/fast", time.monotonic() + 2) == {"verified": True}


@pytest.mark.parametrize("cancel", [False, True])
def test_verified_tls_body_respects_deadline_and_cancellation(monkeypatch, verified_tls_server, cancel):
    port, started = verified_tls_server
    route_tls_host(monkeypatch, port)
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(TLS_CERT))
    cancelled = threading.Event()
    errors = []

    def lookup():
        try:
            album_art._get_json("https://itunes.apple.com/slow",
                                time.monotonic() + (5 if cancel else 0.55), cancelled)
        except requests.RequestException as error:
            errors.append(error)

    worker = threading.Thread(target=lookup, daemon=True)
    start = time.monotonic()
    worker.start()
    try:
        assert started.wait(1)
        if cancel:
            start = time.monotonic()
            cancelled.set()
        worker.join(timeout=1.2)
        assert not worker.is_alive()
        assert errors
        assert time.monotonic() - start < 1.2
    finally:
        cancelled.set()
        worker.join(timeout=2)
    assert not worker.is_alive()


@pytest.mark.parametrize("secure_proxy", [False, True])
def test_https_connect_proxy_retains_verification_and_budget(
        monkeypatch, verified_tls_server, secure_proxy):
    port, _ = verified_tls_server
    seen, stop = [], threading.Event()

    class Tunnel(socketserver.StreamRequestHandler):
        def handle(self):
            seen.append(self.rfile.readline().decode().strip())
            while self.rfile.readline() not in {b"\r\n", b"\n", b""}:
                pass
            with socket.create_connection(("127.0.0.1", port), timeout=1) as upstream:
                self.wfile.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                self.wfile.flush()
                sockets = [self.connection, upstream]
                while not stop.is_set():
                    readable, _, _ = transport.select.select(sockets, [], [], 0.05)
                    for source in readable:
                        payload = source.recv(16384)
                        if not payload:
                            return
                        target = upstream if source is self.connection else self.connection
                        target.sendall(payload)

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Tunnel)
    server.daemon_threads = True
    if secure_proxy:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(TLS_CERT)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(TLS_CERT))
    scheme = "https" if secure_proxy else "http"
    monkeypatch.setenv("HTTPS_PROXY", f"{scheme}://127.0.0.1:{server.server_address[1]}")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")
    worker = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    worker.start()
    try:
        assert album_art._get_json("https://itunes.apple.com/fast", time.monotonic() + 2) == {"verified": True}
        assert len(seen) == 1
        assert seen[0].split()[:2] == ["CONNECT", "itunes.apple.com:443"]
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        worker.join(timeout=1)
    assert not worker.is_alive()
