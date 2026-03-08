# MIT License - Copyright (c) 2026 eripum9

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

    def connect(self):
        try:
            self.rpc.connect()
            self.connected = True
            print("[RPC] Connected to Discord.")
        except Exception as e:
            self.connected = False
            print(f"[RPC] Failed to connect to Discord: {e}")
            traceback.print_exc()

    def disconnect(self):
        if self.connected:
            try:
                self.rpc.close()
            except Exception:
                pass
            self.connected = False

    def _ensure_connected(self):
        if not self.connected:
            self.connect()
        return self.connected

    def update(self, title, artist, album_art_url=None, album_name=None, start_ts=None, duration=0):
        if not self._ensure_connected():
            return

        track_key = f"{title}|{artist}"

        kwargs = {
            "activity_type": ActivityType.LISTENING,
            "details": title[:128] if title else "Unknown Title",
            "state": f"by {artist}" if artist else "Unknown Artist",
            "large_text": album_name if album_name else f"{title}",
        }

        if start_ts:
            kwargs["start"] = start_ts
            if duration > 0:
                kwargs["end"] = int(start_ts + duration)

        if album_art_url:
            kwargs["large_image"] = album_art_url

        try:
            resp = self.rpc.update(**kwargs)
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
