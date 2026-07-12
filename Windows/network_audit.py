import json
import os
import tempfile
import threading
import time


MAX_EVENTS = 50
_LOCK = threading.Lock()


def _history_path(config_dir=None):
    if config_dir is None:
        from config import CONFIG_DIR
        config_dir = CONFIG_DIR
    return os.path.join(config_dir, "network-history.json")


def network_history(config_dir=None):
    path = _history_path(config_dir)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data[-MAX_EVENTS:] if isinstance(item, dict)]


def record_network_event(service, operation, status, detail="", config_dir=None):
    event = {
        "timestamp": time.time(),
        "service": str(service or "unknown")[:40],
        "operation": str(operation or "request")[:60],
        "status": str(status or "unknown")[:24],
        "detail": str(detail or "")[:160],
    }
    path = _history_path(config_dir)
    with _LOCK:
        events = network_history(config_dir)
        events.append(event)
        events = events[-MAX_EVENTS:]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="network-history.", suffix=".tmp", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(events, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
    return event


def network_summary(config_dir=None):
    events = network_history(config_dir)
    return {
        "count": len(events),
        "latest": events[-1] if events else None,
        "events": events,
    }
