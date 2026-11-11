# MIT License - Copyright (c) 2026 eripum9

import errno
import select
import socket
import ssl
import threading
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import NewConnectionError
from urllib3.util.connection import allowed_gai_family
from urllib3.util.ssl_ import create_urllib3_context


class RequestDeadline:
    def __init__(self, deadline, cancel_event=None):
        self.deadline = deadline
        self.cancel_event = cancel_event
        self._finished = threading.Event()
        self._lock = threading.Lock()
        self._sockets = []
        self._watcher = None

    def remaining(self):
        left = self.deadline - time.monotonic()
        if left <= 0 or (self.cancel_event and self.cancel_event.is_set()):
            raise requests.Timeout("artwork lookup cancelled or deadline passed")
        return left

    def connect(self, connection):
        self.remaining()
        addresses = socket.getaddrinfo(connection._dns_host, connection.port,
                                       allowed_gai_family(), socket.SOCK_STREAM)
        error = None
        for family, kind, protocol, _, address in addresses:
            self.remaining()
            sock = socket.socket(family, kind, protocol)
            try:
                for option in connection.socket_options or ():
                    sock.setsockopt(*option)
                if connection.source_address:
                    sock.bind(connection.source_address)
                sock.setblocking(False)
                try:
                    sock.connect(address)
                except OSError as pending:
                    if pending.errno not in {
                        errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY,
                        10035, 10036, 10037,
                    }:
                        raise
                    while True:
                        left = self.remaining()
                        _, writable, failed = select.select([], [sock], [sock], min(left, 0.05))
                        if writable or failed:
                            code = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                            if code:
                                raise OSError(code, "artwork connection failed")
                            break
                self.remaining()
                sock.settimeout(self.remaining())
                self._arm(sock)
                return sock
            except requests.RequestException:
                sock.close()
                raise
            except OSError as failure:
                sock.close()
                error = failure
        self.remaining()
        raise NewConnectionError(connection, "artwork connection failed") from error

    def _arm(self, sock):
        # A duplicate retains the TCP handle when TLS wraps/detaches the original
        # socket, and when HTTPResponse takes ownership after Connection: close.
        duplicate = sock.dup()
        with self._lock:
            self._sockets.append(duplicate)
            if self._watcher is None:
                self._watcher = threading.Thread(target=self._watch, name="artwork-http-deadline", daemon=True)
                self._watcher.start()

    def _watch(self):
        while not self._finished.is_set():
            try:
                left = self.remaining()
            except requests.Timeout:
                with self._lock:
                    for sock in self._sockets:
                        try:
                            sock.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                return
            self._finished.wait(min(left, 0.02))

    def close(self):
        self._finished.set()
        if self._watcher:
            self._watcher.join()
        for sock in self._sockets:
            sock.close()


class DeadlineAdapter(HTTPAdapter):
    def __init__(self, deadline):
        class BoundedSSLSocket(ssl.SSLSocket):
            def _perform(self, operation, *args):
                self.setblocking(False)
                while True:
                    deadline.remaining()
                    try:
                        return operation(*args)
                    except ssl.SSLWantReadError:
                        readers, writers = [self], []
                    except ssl.SSLWantWriteError:
                        readers, writers = [], [self]
                    select.select(readers, writers, [], min(deadline.remaining(), 0.05))

            def do_handshake(self, block=False):
                return self._perform(super().do_handshake)

            def read(self, length=1024, buffer=None):
                return self._perform(super().read, length, buffer)

            def send(self, data, flags=0):
                return self._perform(super().send, data, flags)

            def write(self, data):
                return self._perform(super().write, data)

        class BoundedHTTPConnection(HTTPConnection):
            def _new_conn(self):
                return deadline.connect(self)

        class BoundedHTTPSConnection(HTTPSConnection):
            def _new_conn(self):
                return deadline.connect(self)

        class BoundedHTTPPool(HTTPConnectionPool):
            ConnectionCls = BoundedHTTPConnection

        class BoundedHTTPSPool(HTTPSConnectionPool):
            ConnectionCls = BoundedHTTPSConnection

        self._pool_classes = {"http": BoundedHTTPPool, "https": BoundedHTTPSPool}
        self._ssl_context = create_urllib3_context()
        self._ssl_context.sslsocket_class = BoundedSSLSocket
        super().__init__(max_retries=0)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self._ssl_context
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = self._pool_classes

    def cert_verify(self, connection, url, verify, cert):
        super().cert_verify(connection, url, verify, cert)
        if verify and (connection.ca_certs or connection.ca_cert_dir):
            try:
                self._ssl_context.load_verify_locations(
                    cafile=connection.ca_certs, capath=connection.ca_cert_dir
                )
            except ssl.SSLError as error:
                raise requests.exceptions.SSLError("invalid artwork CA bundle") from error

    def proxy_manager_for(self, proxy, **kwargs):
        if not proxy.lower().startswith(("http://", "https://")):
            raise requests.exceptions.InvalidSchema("artwork lookup requires an HTTP(S) proxy")
        kwargs["ssl_context"] = self._ssl_context
        kwargs["proxy_ssl_context"] = self._ssl_context
        manager = super().proxy_manager_for(proxy, **kwargs)
        manager.pool_classes_by_scheme = self._pool_classes
        return manager


def get_with_deadline(url, deadline, cancel_event, max_bytes):
    budget = RequestDeadline(deadline, cancel_event)
    try:
        with requests.Session() as session:
            adapter = DeadlineAdapter(budget)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            with session.get(url, timeout=budget.remaining(), stream=True, allow_redirects=False,
                             headers={"Accept": "application/json", "Accept-Encoding": "identity"}) as response:
                if response.status_code != 200:
                    raise requests.HTTPError(f"artwork HTTP status {response.status_code}")
                body, size = [], 0
                for chunk in response.iter_content(16384):
                    budget.remaining()
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("artwork lookup response too large")
                    body.append(chunk)
                budget.remaining()
                return b"".join(body)
    finally:
        budget.close()
