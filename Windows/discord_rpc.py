# MIT License - Copyright (c) 2026 eripum9

import os
import time
import traceback
from pypresence import Presence
from pypresence.types import ActivityType

STATUS_DISPLAY_TYPES = {
    "application": 0,
    "artist": 1,
    "album": 1,
    "track": 2,
}


def _discord_activity_text(value, fallback, one_character_label):
    text = str(value or "").strip()
    if not text:
        return fallback
    if len(text) == 1:
        return f"{one_character_label}: {text}"[:128]
    return text[:128]


def _discord_activity_fields(title, artist, album_name, status_display):
    mode = str(status_display or "").strip().lower()
    if mode not in STATUS_DISPLAY_TYPES:
        mode = "artist"

    title_text = _discord_activity_text(title, "Unknown Title", "Track")
    raw_artist = str(artist or "").strip()
    artist_known = raw_artist.casefold() not in {"", "unknown", "unknown artist", "n/a", "none"}
    artist_text = _discord_activity_text(raw_artist if artist_known else "", "Unknown Artist", "Artist")
    album = str(album_name or "").strip()

    if not artist_known:
        mode = "application"

    if mode == "album":
        state = _discord_activity_text(album, artist_text, "Album") if album else artist_text
        details = _discord_activity_text(f"{title_text} by {raw_artist}", title_text, "Track")
    elif mode == "artist":
        details = title_text
        state = artist_text
    else:
        details = title_text
        state = _discord_activity_text(f"by {raw_artist}" if artist_known else "", "Unknown Artist", "Artist")

    return details, state, STATUS_DISPLAY_TYPES[mode]


def _discord_asset_text(album_name, title):
    album = str(album_name or "").strip()
    if len(album) >= 2:
        return album[:128]
    if album:
        return f"Album: {album}"[:128]

    track = str(title or "").strip()
    if len(track) >= 2:
        return track[:128]
    if track:
        return f"Track: {track}"[:128]

    return "Unknown Album"


def _button_signature(buttons):
    if not buttons:
        return ""
    parts = []
    for button in buttons:
        if isinstance(button, dict):
            parts.append(f"{button.get('label', '')}={button.get('url', '')}")
        else:
            parts.append(str(button))
    return "|".join(parts)


class DiscordRPC:
    def __init__(self, client_id):
        self.client_id = client_id
        self.rpc = Presence(client_id)
        self.connected = False
        self._last_track_key = None
        self._last_button_signature = None
        self._backoff = 3
        self._next_retry = 0
        self._closed = False

    def connect(self):
        try:
            self.rpc.connect()
            self._closed = False
            self.connected = True
            self._backoff = 3
            self._next_retry = 0
            print("[RPC] Connected to Discord.")
        except Exception as e:
            self.connected = False
            self._next_retry = time.time() + self._backoff
            print(f"[RPC] Failed to connect (retry in {self._backoff:.0f}s): {e}")
            self._backoff = min(self._backoff * 1.5, 60)

    def disconnect(self):
        if not self._closed:
            try:
                self.rpc.close()
            except Exception:
                pass
            self._closed = True
        self.connected = False

    def shutdown(self):
        try:
            self.rpc.clear()
        except Exception as e:
            print(f"[RPC] Shutdown clear failed: {e}")
        finally:
            self._last_track_key = None
            self._last_button_signature = None
            self.disconnect()

    def _ensure_connected(self):
        if not self.connected:
            if time.time() < self._next_retry:
                return False
            self.connect()
        return self.connected

    def update(self, title, artist, album_art_url=None, album_name=None, start_ts=None, duration=0, buttons=None, small_image=None, small_text=None, status_display="artist"):
        if not self._ensure_connected():
            return

        details, state, status_display_type = _discord_activity_fields(title, artist, album_name, status_display)
        track_key = f"{title}|{artist}|{status_display_type}|{state}"
        button_signature = _button_signature(buttons)
        if self._last_button_signature is not None and button_signature != self._last_button_signature:
            try:
                self.rpc.clear()
                time.sleep(0.35)
            except Exception:
                pass

        activity = {
            "type": ActivityType.LISTENING.value,
            "details": details,
            "state": state,
            "status_display_type": status_display_type,
            "assets": {
                "large_text": _discord_asset_text(album_name, title),
            },
            "instance": True,
        }

        if start_ts:
            start_ms = int(start_ts) * 1000
            activity["timestamps"] = {"start": start_ms}
            if duration > 0:
                end_ms = int(start_ts + duration) * 1000
                activity["timestamps"]["end"] = end_ms

        if album_art_url:
            activity["assets"]["large_image"] = album_art_url

        if small_image:
            activity["assets"]["small_image"] = small_image
            if small_text:
                activity["assets"]["small_text"] = small_text

        if buttons:
            activity["buttons"] = buttons
        elif self._last_button_signature:
            activity["buttons"] = []

        payload = {
            "cmd": "SET_ACTIVITY",
            "args": {
                "pid": os.getpid(),
                "activity": activity,
            },
            "nonce": f"{time.time():.20f}",
        }

        try:
            resp = self.rpc.update(payload_override=payload)
            if track_key != self._last_track_key:
                print(f"[RPC] Now showing: {title} by {artist} | {album_name or 'no album'}")
                print(f"[RPC] Response: {resp}")
                self._last_track_key = track_key
            self._last_button_signature = button_signature
        except Exception as e:
            print(f"[RPC] Update failed: {e}")
            traceback.print_exc()
            self.connected = False

    def clear(self):
        if not self.connected:
            return
        try:
            self.rpc.clear()
            self._last_track_key = None
            self._last_button_signature = None
            print("[RPC] Presence cleared.")
        except Exception as e:
            print(f"[RPC] Clear failed: {e}")
            self.connected = False
