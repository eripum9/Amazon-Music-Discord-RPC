# MIT License - Copyright (c) 2026 eripum9

"""One-instance lock and small owner-only command socket for the menu-bar app."""

from __future__ import annotations

import fcntl
import hashlib
import os
import socket
import stat
import tempfile
import threading
from pathlib import Path

from . import config


ALLOWED_COMMANDS = {"settings", "diagnostics", "activate", "quit"}


class SingleInstance:
    def __init__(self, on_command=None, directory=None):
        self.directory = Path(directory or config.CONFIG_DIR)
        self.lock_path = self.directory / "instance.lock"
        socket_path = self.directory / "instance.sock"
        if len(os.fsencode(socket_path)) > 96:
            digest = hashlib.sha256(os.fsencode(self.directory.resolve())).hexdigest()[:16]
            socket_path = Path(tempfile.gettempdir()) / f"amrpc-{os.getuid()}-{digest}.sock"
        self.socket_path = socket_path
        self.on_command = on_command
        self._lock_handle = None
        self._server = None
        self._thread = None
        self._stopping = threading.Event()
        self._owns_socket = False

    def acquire(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(self.directory, 0o700)
        except OSError:
            pass
        handle = self.lock_path.open("a+b")
        os.chmod(self.lock_path, 0o600)
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False
        self._lock_handle = handle
        self._remove_stale_socket()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.socket_path))
            self._owns_socket = True
            os.chmod(self.socket_path, 0o600)
            server.listen(4)
            server.settimeout(0.5)
        except Exception:
            server.close()
            self.close()
            raise
        self._server = server
        self._thread = threading.Thread(target=self._serve, name="macos-instance-ipc", daemon=True)
        self._thread.start()
        return True

    def _remove_stale_socket(self):
        try:
            info = self.socket_path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise RuntimeError("Refusing to replace an untrusted instance socket path")
        self.socket_path.unlink()

    def _serve(self):
        while not self._stopping.is_set() and self._server:
            try:
                client, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with client:
                try:
                    payload = client.recv(1024).decode("utf-8", errors="replace").strip()
                except OSError:
                    continue
            if payload in ALLOWED_COMMANDS and self.on_command:
                try:
                    self.on_command(payload)
                except Exception:
                    pass

    def notify(self, command="activate", timeout=1.5):
        command = str(command or "").strip()
        if command not in ALLOWED_COMMANDS:
            raise ValueError("Unsupported instance command")
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(timeout)
        try:
            client.connect(str(self.socket_path))
            client.sendall(command.encode("utf-8"))
            return True
        except OSError:
            return False
        finally:
            client.close()

    def close(self):
        self._stopping.set()
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.5)
        self._thread = None
        if self._lock_handle:
            try:
                fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
                self._lock_handle.close()
            except OSError:
                pass
            self._lock_handle = None
        if self._owns_socket:
            try:
                info = self.socket_path.lstat()
                if stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid():
                    self.socket_path.unlink()
            except FileNotFoundError:
                pass
            self._owns_socket = False

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("Amazon Music RPC is already running")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False
