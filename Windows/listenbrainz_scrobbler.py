# MIT License - Copyright (c) 2026 eripum9

import traceback
import threading
import liblistenbrainz

try:
    from .task_supervisor import TaskSupervisor
except ImportError:  # Direct execution and the existing Windows frozen entrypoint.
    from task_supervisor import TaskSupervisor


class ListenBrainzScrobbler:
    def __init__(self, user_token, privacy_enabled=False):
        self.client = liblistenbrainz.ListenBrainz()
        self.client.set_auth_token(user_token, check_validity=False)
        self._pending = []
        self._lock = threading.Lock()
        self._privacy_blocked = threading.Event()
        if privacy_enabled:
            self._privacy_blocked.set()
        self._tasks = TaskSupervisor()

    def set_privacy(self, enabled):
        if enabled:
            self._privacy_blocked.set()
        with self._lock:
            if enabled:
                self._pending.clear()
            else:
                self._privacy_blocked.clear()

    def _submission_allowed(self):
        return not self._privacy_blocked.is_set() and not self._tasks.stopping

    def update_now_playing(self, title, artist, album=None, duration=None):
        self._run_async("now playing", self._update_now_playing_sync, title, artist, album, duration, drop_if_busy=True)

    def _update_now_playing_sync(self, title, artist, album=None, duration=None):
        if not self._submission_allowed():
            return
        try:
            listen = liblistenbrainz.Listen(
                track_name=title,
                artist_name=artist,
                release_name=album or "",
            )
            self.client.submit_playing_now(listen)
            print(f"[ListenBrainz] Now playing: {title} by {artist}")
        except Exception as e:
            print(f"[ListenBrainz] Now playing failed: {e}")

    def scrobble(self, title, artist, timestamp, album=None, duration=None):
        entry = {
            "track_name": title,
            "artist_name": artist,
            "release_name": album or "",
            "listened_at": int(timestamp),
        }
        self._run_async("scrobble", self._scrobble_sync, entry)

    def _scrobble_sync(self, entry):
        if not self._submission_allowed():
            return
        try:
            self._flush_pending()
            if not self._submission_allowed():
                return
            listen = liblistenbrainz.Listen(**entry)
            self.client.submit_single_listen(listen)
            print(f"[ListenBrainz] Scrobbled: {entry['track_name']} by {entry['artist_name']}")
        except (liblistenbrainz.errors.ListenBrainzAPIException, Exception) as e:
            if "rate" in str(e).lower() or "connect" in str(e).lower() or "timeout" in str(e).lower():
                self._pending.append(entry)
                print(f"[ListenBrainz] Scrobble cached ({len(self._pending)} pending): {e}")
            else:
                print(f"[ListenBrainz] Scrobble failed: {e}")
                traceback.print_exc()

    def _flush_pending(self):
        if not self._pending:
            return
        remaining = []
        for entry in self._pending:
            if not self._submission_allowed():
                self._pending = []
                return
            try:
                listen = liblistenbrainz.Listen(**entry)
                self.client.submit_single_listen(listen)
                print(f"[ListenBrainz] Flushed cached scrobble: {entry['track_name']} by {entry['artist_name']}")
            except Exception:
                remaining.append(entry)
                break
        if remaining:
            idx = self._pending.index(remaining[0])
            self._pending = self._pending[idx:]
        else:
            self._pending = []

    def _run_async(self, label, func, *args, drop_if_busy=False):
        def runner():
            if drop_if_busy and not self._lock.acquire(blocking=False):
                print(f"[ListenBrainz] Skipped {label}: previous request still running")
                return
            if not drop_if_busy:
                self._lock.acquire()
            try:
                func(*args)
            finally:
                self._lock.release()

        self._tasks.start_unique(f"listenbrainz-{label}", runner)

    def close(self):
        self._privacy_blocked.set()
        self._tasks.request_stop()
        self._tasks.join(timeout=3)
