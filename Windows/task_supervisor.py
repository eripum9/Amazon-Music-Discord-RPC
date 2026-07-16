# MIT License - Copyright (c) 2026 eripum9

import threading
import time
import traceback


class TaskSupervisor:
    def __init__(self, error_handler=None):
        self._lock = threading.RLock()
        self._tasks = {}
        self._counter = 0
        self.stop_event = threading.Event()
        self._error_handler = error_handler

    @property
    def stopping(self):
        return self.stop_event.is_set()

    def start(self, name, target, args=(), kwargs=None, daemon=True, replace=False):
        kwargs = dict(kwargs or {})
        with self._lock:
            existing = self._tasks.get(name)
            if existing and existing.is_alive() and not replace:
                return existing

        def runner():
            try:
                target(*args, **kwargs)
            except Exception as error:
                if self._error_handler:
                    self._error_handler(name, error, traceback.format_exc())
            finally:
                with self._lock:
                    if self._tasks.get(name) is threading.current_thread():
                        self._tasks.pop(name, None)

        thread = threading.Thread(target=runner, name=f"AmazonMusicRPC:{name}", daemon=daemon)
        with self._lock:
            self._tasks[name] = thread
        thread.start()
        return thread

    def start_unique(self, prefix, target, args=(), kwargs=None, daemon=True):
        with self._lock:
            self._counter += 1
            name = f"{prefix}-{self._counter}"
        return self.start(name, target, args, kwargs, daemon=daemon)

    def request_stop(self):
        self.stop_event.set()

    def wait(self, seconds):
        return self.stop_event.wait(max(0.0, float(seconds)))

    def join(self, timeout=10):
        deadline = time.monotonic() + max(0.0, float(timeout))
        while True:
            with self._lock:
                threads = [thread for thread in self._tasks.values() if thread is not threading.current_thread() and thread.is_alive()]
            if not threads:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            for thread in threads:
                thread.join(min(0.25, remaining))

    def snapshot(self):
        with self._lock:
            return {name: {"alive": thread.is_alive(), "daemon": thread.daemon} for name, thread in self._tasks.items()}
