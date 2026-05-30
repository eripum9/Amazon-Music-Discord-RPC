import csv
import os
import subprocess
import time


PLAYBACK_TIME_DRIFT_SECONDS = 1.0


def privacy_keywords(config):
    raw = config.get("privacy_blocked_keywords", "")
    return [item.strip().lower() for item in raw.replace("\n", ",").split(",") if item.strip()]


def privacy_match(config, title="", artist="", album=""):
    if config.get("privacy_private_session"):
        return "Private session enabled"
    haystack = f"{title} {artist} {album}".lower()
    for keyword in privacy_keywords(config):
        if keyword in haystack:
            return f"Matched privacy keyword: {keyword}"
    return ""


def normalised_text(value):
    return " ".join(str(value or "").strip().lower().split())


def same_track_field(left, right):
    left = normalised_text(left)
    right = normalised_text(right)
    return bool(left and right and left == right)


def duration_value(value):
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def track_info_payload(track):
    return {
        "title": track.get("title", ""),
        "artist": track.get("artist", ""),
        "album": track.get("album", ""),
        "art_url": track.get("art_url", ""),
        "track_link": track.get("track_link", ""),
        "duration": duration_value(track.get("duration", 0)),
    }


def normalise_process_name(value):
    text = str(value or "").strip().strip('"').strip("'").lower()
    return os.path.basename(text)


def configured_game_mode_processes(config):
    value = config.get("game_mode_processes", "")
    if isinstance(value, list):
        parts = value
    else:
        parts = str(value or "").replace(";", ",").replace("\n", ",").split(",")
    return {name for name in (normalise_process_name(part) for part in parts) if name}


def game_mode_matches_processes(configured, running_names):
    running = set()
    for name in running_names:
        clean = normalise_process_name(name)
        if clean:
            running.add(clean)
            stem, ext = os.path.splitext(clean)
            if ext == ".exe" and stem:
                running.add(stem)
    for name in configured:
        clean = normalise_process_name(name)
        if clean in running:
            return True
        stem, ext = os.path.splitext(clean)
        if ext == ".exe" and stem in running:
            return True
        if not ext and f"{clean}.exe" in running:
            return True
    return False


def running_process_names():
    try:
        completed = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        if completed.returncode != 0:
            return set()
        names = set()
        for row in csv.reader(completed.stdout.splitlines()):
            if row:
                name = normalise_process_name(row[0])
                if name:
                    names.add(name)
        return names
    except Exception:
        return set()


class ResolvedTrackStore:
    def __init__(self):
        self.cache = {}
        self.track_info = {}
        self.skipped_keys = set()

    def store_track(self, raw_key, track):
        if not isinstance(track, dict):
            return
        payload = track_info_payload(track)
        if raw_key:
            self.track_info[raw_key] = payload
        resolved_key = f"{payload['title']}|{payload['artist']}"
        if payload["title"] or payload["artist"]:
            self.track_info[resolved_key] = payload

    def apply_cache(self, raw_key, title, artist):
        resolved = self.cache.get(raw_key)
        if not resolved:
            return title, artist, False
        return resolved[0] or title, resolved[1] or artist, True

    def resolved_art(self, raw_key, title, artist, fallback_album=""):
        info = self.track_info.get(raw_key) or self.track_info.get(f"{title}|{artist}")
        if not info or not info.get("art_url"):
            return None
        return (
            info.get("art_url", ""),
            info.get("album", "") or fallback_album,
            info.get("track_link", ""),
            duration_value(info.get("duration", 0)),
        )

    def clear_choice(self, raw_key):
        self.cache.pop(raw_key, None)
        self.track_info.pop(raw_key, None)
        self.skipped_keys.discard(raw_key)


class GameModeState:
    def __init__(self):
        self.process_cache = {"signature": "", "checked_at": 0.0, "active": False}
        self.suppressed_keys = set()

    def active(self, config, running_names_fn=running_process_names):
        if bool(config.get("game_mode_enabled")):
            return True
        configured = configured_game_mode_processes(config)
        if not configured:
            return False
        signature = "\n".join(sorted(configured))
        now = time.time()
        if self.process_cache.get("signature") == signature and now - self.process_cache.get("checked_at", 0.0) < 5:
            return bool(self.process_cache.get("active"))
        active = game_mode_matches_processes(configured, running_names_fn())
        self.process_cache.update({"signature": signature, "checked_at": now, "active": active})
        return active

    def should_prompt_wrong_song(self, raw_key, title, artist, config, running_names_fn=running_process_names, on_suppressed=None):
        if not same_track_field(title, artist):
            return False
        if self.active(config, running_names_fn):
            if raw_key not in self.suppressed_keys:
                if on_suppressed:
                    on_suppressed()
                self.suppressed_keys.add(raw_key)
            return False
        return True


class TrackTimingState:
    def __init__(self):
        self.cache = {}

    def cached_start_ts(self, raw_key):
        cached = self.cache.get(raw_key)
        if not cached:
            return None
        if time.time() - cached.get("updated_at", 0) > 45:
            self.cache.pop(raw_key, None)
            return None
        return cached.get("start_ts")

    def track_start_ts(self, track, raw_key, use_cache=True):
        position = track.get("position")
        start_ts = None
        try:
            if position is not None and float(position) >= 0:
                start_ts = int(time.time() - float(position))
        except (TypeError, ValueError):
            start_ts = None
        if start_ts is None and use_cache:
            start_ts = self.cached_start_ts(raw_key) or int(time.time())
        if start_ts is None:
            start_ts = int(time.time())
        self.cache[raw_key] = {
            "start_ts": start_ts,
            "updated_at": time.time(),
        }
        return start_ts

    def playing_start_ts(self, track, raw_key, last_start_ts, paused_position, resumed_from_pause):
        position = track_position(track)
        if resumed_from_pause and position is not None:
            return self.track_start_ts(track, raw_key, use_cache=False), None, True
        if last_start_ts is None:
            if position is not None:
                return self.track_start_ts(track, raw_key), None, False
            if paused_position is not None:
                return int(time.time() - paused_position), None, False
        elif position is not None:
            drift = position - (time.time() - last_start_ts)
            if abs(drift) > PLAYBACK_TIME_DRIFT_SECONDS:
                return self.track_start_ts(track, raw_key, use_cache=False), None, True
        return last_start_ts, paused_position, False


def track_position(track):
    try:
        position = track.get("position")
        if position is not None and float(position) >= 0:
            return float(position)
    except (TypeError, ValueError):
        pass
    return None


def devtools_no_track_state(enabled, current_state):
    if not enabled:
        return current_state
    current_state = current_state if isinstance(current_state, dict) else {}
    if current_state.get("status") in {"unavailable", "error", "launching", "restarting"}:
        return current_state
    return {
        "enabled": True,
        "status": "waiting",
        "detail": "No Amazon Music metadata or SMTC fallback session",
    }


def hidden_privacy_track(track):
    return {
        "title": "Hidden by privacy controls",
        "artist": "",
        "album": "",
        "status": track.get("status", ""),
        "position": track.get("position"),
        "duration": track.get("duration"),
    }
