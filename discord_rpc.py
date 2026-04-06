# MIT License - Copyright (c) 2026 eripum9

import os
import time
import traceback
from pypresence import Presence
from pypresence.types import ActivityType


class DiscordRPC:
    def __init__(self, client_id):
        self.client_id = client_id
        self.rpc = Presence(client_id)
        self.connected = False
        self._last_track_key = None
        self._backoff = 3
        self._next_retry = 0

    def connect(self):
        try:
            self.rpc.connect()
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
        if self.connected:
            try:
                self.rpc.close()
            except Exception:
                pass
            self.connected = False

    def _ensure_connected(self):
        if not self.connected:
            if time.time() < self._next_retry:
                return False
            self.connect()
        return self.connected

    def update(self, title, artist, album_art_url=None, album_name=None, start_ts=None, duration=0, buttons=None, small_image=None, small_text=None):
        if not self._ensure_connected():
            return

        track_key = f"{title}|{artist}"

        activity = {
            "type": ActivityType.LISTENING.value,
            "details": title[:128] if title else "Unknown Title",
            "state": f"by {artist}" if artist else "Unknown Artist",
            "assets": {
                "large_text": album_name if album_name else f"{title}",
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
            print("[RPC] Presence cleared.")
        except Exception as e:
            print(f"[RPC] Clear failed: {e}")
            self.connected = False
