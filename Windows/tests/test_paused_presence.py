# MIT License - Copyright (c) 2026 eripum9

import discord_rpc
import rpc_state


def test_paused_text_shows_frozen_position():
    assert rpc_state.paused_presence_text(9.4, 200) == "Paused at 0:09 / 3:20"
    assert rpc_state.paused_presence_text(9.4, 0) == "Paused at 0:09"
    assert rpc_state.paused_presence_text(None, 200) == "Paused"


def test_paused_presence_sends_no_running_timer():
    sent = []

    class FakePresence:
        def update(self, payload_override=None):
            sent.append(payload_override)
            return {}

    rpc = discord_rpc.DiscordRPC.__new__(discord_rpc.DiscordRPC)
    rpc.rpc = FakePresence()
    rpc.connected = True
    rpc._last_track_key = None
    rpc._last_button_signature = None
    rpc._ensure_connected = lambda: True

    rpc.update(title="Song", artist="Artist", album_name="11: 59", start_ts=None, duration=0,
               small_image="pause.png", small_text=rpc_state.paused_presence_text(9, 200),
               large_text=rpc_state.paused_album_line(9, 200, "11: 59"))
    activity = sent[-1]["args"]["activity"]
    assert "timestamps" not in activity
    assert activity["assets"]["small_text"] == "Paused at 0:09 / 3:20"
    assert activity["assets"]["large_text"] == "\u23f8 0:09 / 3:20 \u00b7 11: 59"

    rpc.update(title="Song", artist="Artist", album_name="11: 59", start_ts=1000, duration=200)
    assert sent[-1]["args"]["activity"]["assets"]["large_text"] == "11: 59"


def test_paused_album_line_variants():
    assert rpc_state.paused_album_line(65, 0, "") == "\u23f8 1:05"
    assert rpc_state.paused_album_line(None, 200, "Album") is None
