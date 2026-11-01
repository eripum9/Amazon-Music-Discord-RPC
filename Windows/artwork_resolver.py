# MIT License - Copyright (c) 2026 eripum9

"""Run the artwork/album lookup for the current track off the playback loop.

The playback loop asks for a lookup and keeps polling Amazon/SMTC while the
network request runs.  Only the most recent request is kept: a request that
was superseded (song changed) before it started is skipped, and a result that
finishes after it was superseded is discarded instead of being shown for the
wrong song.
"""

import threading

EMPTY_RESULT = (None, "", "", 0)


def lookup_key(title, artist, album=""):
    """Identity of one lookup.  Duration is context, not identity: Amazon's
    reported duration can wobble by a second while a song plays."""
    return "|".join(str(part or "").strip().casefold() for part in (title, artist, album))


class ArtworkResolver:
    def __init__(self, lookup, start_thread=True):
        self._lookup = lookup
        self._start_thread = start_thread
        self._cond = threading.Condition()
        self._wanted = None
        self._pending = None
        self._result = None
        self._thread = None

    def request(self, key, **context):
        """Ask for ``key`` unless it is already wanted.  Returns True when queued."""
        with self._cond:
            if key == self._wanted:
                return False
            self._wanted = key
            self._pending = (key, context)
            self._result = None
            self._cond.notify()
            if self._start_thread and (self._thread is None or not self._thread.is_alive()):
                self._thread = threading.Thread(target=self._run, name="artwork-resolver", daemon=True)
                self._thread.start()
            return True

    def result(self, key):
        """The finished result for ``key``, or None while it is still running."""
        with self._cond:
            if key != self._wanted or self._result is None or self._result[0] != key:
                return None
            return self._result[1]

    def cancel(self):
        with self._cond:
            self._wanted = None
            self._pending = None
            self._result = None

    def process_pending(self):
        """Run the queued lookup on the calling thread (used by tests)."""
        with self._cond:
            job, self._pending = self._pending, None
        if job is not None:
            self._execute(*job)
        return job is not None

    def _run(self):
        while True:
            with self._cond:
                while self._pending is None:
                    self._cond.wait()
                key, context = self._pending
                self._pending = None
            self._execute(key, context)

    def _execute(self, key, context):
        with self._cond:
            if key != self._wanted:
                return  # superseded before it started
        try:
            outcome = self._lookup(**context)
        except Exception as error:  # a failed lookup must never stop playback updates
            print(f"[Art] Lookup failed: {type(error).__name__}")
            outcome = EMPTY_RESULT
        with self._cond:
            if key == self._wanted:
                self._result = (key, outcome or EMPTY_RESULT)
