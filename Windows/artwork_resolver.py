# MIT License - Copyright (c) 2026 eripum9

import threading

EMPTY_RESULT = (None, "", "", 0)


def lookup_key(title, artist, album=""):
    return tuple(str(part or "").strip().casefold() for part in (title, artist, album))


class ArtworkResolver:
    def __init__(self, lookup, start_thread=True):
        self._lookup = lookup
        self._start_thread = start_thread
        self._cond = threading.Condition()
        self._wanted = None
        self._pending = None
        self._result = None
        self._thread = None
        self._generation = 0
        self._cancel_event = threading.Event()
        self._closed = False

    def request(self, key, **context):
        with self._cond:
            if self._closed or key == self._wanted:
                return False
            self._invalidate()
            self._wanted = key
            self._pending = (key, self._generation, self._cancel_event, context)
            self._cond.notify_all()
            if self._start_thread and (self._thread is None or not self._thread.is_alive()):
                self._thread = threading.Thread(target=self._run, name="artwork-resolver", daemon=True)
                self._thread.start()
            return True

    def result(self, key):
        with self._cond:
            if self._closed or key != self._wanted or self._result is None:
                return None
            return self._result

    def _invalidate(self):
        self._cancel_event.set()
        self._cancel_event = threading.Event()
        self._generation += 1
        self._wanted = self._pending = self._result = None

    def cancel(self):
        with self._cond:
            self._invalidate()
            self._cond.notify_all()

    def close(self, timeout=0):
        with self._cond:
            self._closed = True
            self._invalidate()
            self._cond.notify_all()
            thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=max(0, timeout))

    def process_pending(self):
        with self._cond:
            job, self._pending = self._pending, None
        if job is not None:
            self._execute(*job)
        return job is not None

    def _run(self):
        while True:
            with self._cond:
                while self._pending is None and not self._closed:
                    self._cond.wait()
                if self._closed:
                    return
                job, self._pending = self._pending, None
            self._execute(*job)

    def _execute(self, key, generation, cancel_event, context):
        with self._cond:
            if self._closed or generation != self._generation:
                return
        try:
            outcome = self._lookup(**context, cancel_event=cancel_event)
        except Exception as error:
            print(f"[Art] Lookup failed: {type(error).__name__}")
            outcome = EMPTY_RESULT
        with self._cond:
            if not self._closed and generation == self._generation and not cancel_event.is_set():
                self._result = outcome or EMPTY_RESULT
                self._cond.notify_all()
