# MIT License - Copyright (c) 2026 eripum9

import time
import traceback
import threading
import liblistenbrainz


class ListenBrainzScrobbler:
    def __init__(self, user_token):
        self.client = liblistenbrainz.ListenBrainz()
        self.client.set_auth_token(user_token, check_validity=False)
        self._pending = []
        self._lock = threading.Lock()

    def update_now_playing(self, title, artist, album=None, duration=None):
        self._run_async("now playing", self._update_now_playing_sync, title, artist, album, duration, drop_if_busy=True)

    def _update_now_playing_sync(self, title, artist, album=None, duration=None):
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
        try:
            self._flush_pending()
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

        threading.Thread(target=runner, daemon=True).start()
