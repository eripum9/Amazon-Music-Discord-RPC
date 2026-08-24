# MIT License - Copyright (c) 2026 eripum9

import json
import math
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse


AMAZON_MUSIC_BUNDLE_ID = "com.amazon.music"
MAX_PROBE_OUTPUT_BYTES = 64 * 1024
PROBE_PATH = Path(__file__).with_name("amazon_music_now_playing.js")


def _text(value, limit=2048):
    return str(value or "").strip()[:limit]


def _seconds(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, number) if math.isfinite(number) else 0.0


def _position(value, duration):
    try:
        position = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(position):
        return None
    position = max(0.0, position)
    if duration > 0:
        position = min(position, duration)
    return position


def _https_artwork_url(value):
    url = _text(value, 4096)
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return ""
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port not in (None, 443)
    ):
        return ""
    return url


def parse_probe_payload(payload):
    if not isinstance(payload, Mapping):
        return None
    if payload.get("status") != "found":
        return None
    if _text(payload.get("bundle_identifier"), 256) != AMAZON_MUSIC_BUNDLE_ID:
        return None

    title = _text(payload.get("title"), 512)
    artist = _text(payload.get("artist"), 512)
    album = _text(payload.get("album"), 512)
    if not title:
        return None

    duration = _seconds(payload.get("duration"))
    position = _position(payload.get("position"), duration)
    playback_rate = _seconds(payload.get("playback_rate"))
    status = "playing" if playback_rate > 0 else "paused"
    art_url = _https_artwork_url(payload.get("artwork_url"))

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "status": status,
        "position": position,
        "duration": duration,
        "art_url": art_url,
        "source": "macos_now_playing",
    }


def get_track_sync(timeout=4.0, runner=subprocess.run, platform=None):
    if (platform or sys.platform) != "darwin":
        return None
    try:
        completed = runner(
            ["/usr/bin/osascript", "-l", "JavaScript", str(PROBE_PATH)],
            capture_output=True,
            text=True,
            timeout=max(0.1, float(timeout)),
        )
    except (OSError, subprocess.SubprocessError, TypeError, ValueError):
        return None
    if completed.returncode != 0:
        return None
    output = completed.stdout or ""
    if len(output.encode("utf-8", errors="replace")) > MAX_PROBE_OUTPUT_BYTES:
        return None
    try:
        payload = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return None
    return parse_probe_payload(payload)
