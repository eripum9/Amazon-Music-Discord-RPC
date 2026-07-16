# MIT License - Copyright (c) 2026 eripum9

import threading
from copy import deepcopy

from app_models import DiagnosticsSnapshot, TrackSnapshot


class ApplicationState:
    def __init__(self):
        self._lock = threading.RLock()
        self._config = {}
        self._rpc_running = False
        self._current_track_key = ""
        self._track = None
        self._diagnostics = {}
        self._active_rpc = None

    def replace_config(self, config):
        with self._lock:
            self._config = dict(config or {})
            return dict(self._config)

    def config(self):
        with self._lock:
            return dict(self._config)

    def set_rpc_running(self, running):
        with self._lock:
            self._rpc_running = bool(running)

    def rpc_running(self):
        with self._lock:
            return self._rpc_running

    def set_active_rpc(self, rpc):
        with self._lock:
            self._active_rpc = rpc

    def active_rpc(self):
        with self._lock:
            return self._active_rpc

    def set_current_track(self, raw_key, track=None):
        snapshot = TrackSnapshot.from_mapping(track) if track else None
        with self._lock:
            self._current_track_key = str(raw_key or "")
            self._track = snapshot

    def current_track_key(self):
        with self._lock:
            return self._current_track_key

    def track(self):
        with self._lock:
            return self._track

    def update_diagnostics(self, snapshot: DiagnosticsSnapshot):
        payload = snapshot.to_dict() if isinstance(snapshot, DiagnosticsSnapshot) else deepcopy(dict(snapshot or {}))
        with self._lock:
            self._diagnostics = payload
            track = payload.get("track")
            if track:
                self._track = TrackSnapshot.from_mapping(track)
            return deepcopy(payload)

    def diagnostics(self):
        with self._lock:
            return deepcopy(self._diagnostics)

    def snapshot(self):
        with self._lock:
            return {
                "config": dict(self._config),
                "rpc_running": self._rpc_running,
                "current_track_key": self._current_track_key,
                "track": self._track.to_dict() if self._track else None,
                "diagnostics": deepcopy(self._diagnostics),
            }
