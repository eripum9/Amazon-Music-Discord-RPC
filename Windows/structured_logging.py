# MIT License - Copyright (c) 2026 eripum9

import io
import json
import os
import re
import threading
from datetime import datetime, timezone


_COMPONENT_RE = re.compile(r"^\[([^\]]+)\]\s*(.*)$", re.DOTALL)


def rotate_logs(directory, filename, old_count=5):
    os.makedirs(directory, exist_ok=True)
    stem, extension = os.path.splitext(filename)
    oldest = os.path.join(directory, f"{stem}.{old_count}{extension}")
    if os.path.exists(oldest):
        os.remove(oldest)
    for index in range(old_count - 1, 0, -1):
        source = os.path.join(directory, f"{stem}.{index}{extension}")
        destination = os.path.join(directory, f"{stem}.{index + 1}{extension}")
        if os.path.exists(source):
            os.replace(source, destination)
    current = os.path.join(directory, filename)
    if os.path.exists(current) and os.path.getsize(current) > 0:
        os.replace(current, os.path.join(directory, f"{stem}.1{extension}"))
    with open(current, "w", encoding="utf-8"):
        pass


class StructuredLogTee(io.TextIOBase):
    def __init__(self, original, text_path, event_path, stream, redactor=None):
        self._original = original
        self._stream = stream
        self._redactor = redactor or (lambda value: value)
        self._lock = threading.RLock()
        self._buffer = ""
        os.makedirs(os.path.dirname(text_path), exist_ok=True)
        self._text = open(text_path, "a", encoding="utf-8", errors="replace")
        self._events = open(event_path, "a", encoding="utf-8", errors="replace")

    def write(self, value):
        text = str(value or "")
        with self._lock:
            if self._original:
                try:
                    self._original.write(text)
                except Exception:
                    pass
            try:
                self._text.write(text)
                self._text.flush()
            except Exception:
                pass
            self._buffer += text
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                self._write_event(line)
        return len(text)

    def _write_event(self, line):
        clean = self._redactor(line.rstrip("\r"))
        if not clean:
            return
        match = _COMPONENT_RE.match(clean)
        component = match.group(1) if match else self._stream
        message = match.group(2) if match else clean
        lowered = message.lower()
        level = "error" if any(term in lowered for term in ("error", "failed", "exception", "traceback")) else "warning" if any(term in lowered for term in ("warning", "unavailable", "retry")) else "info"
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": level,
            "component": component,
            "message": message,
            "thread": threading.current_thread().name,
            "stream": self._stream,
        }
        try:
            self._events.write(json.dumps(event, ensure_ascii=True) + "\n")
            self._events.flush()
        except Exception:
            pass

    def flush(self):
        with self._lock:
            if self._original:
                try:
                    self._original.flush()
                except Exception:
                    pass
            try:
                self._text.flush()
                self._events.flush()
            except Exception:
                pass

    def close(self):
        with self._lock:
            if self._buffer:
                self._write_event(self._buffer)
                self._buffer = ""
            self._text.close()
            self._events.close()
        super().close()
