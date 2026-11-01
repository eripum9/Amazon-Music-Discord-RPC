# MIT License - Copyright (c) 2026 eripum9

import discord_rpc


def _rpc(clock):
    sent = []

    class FakePresence:
        def update(self, payload_override=None):
            sent.append(payload_override["args"]["activity"])
            return {}

        def clear(self):
            pass

    rpc = discord_rpc.DiscordRPC.__new__(discord_rpc.DiscordRPC)
    rpc.rpc = FakePresence()
    rpc.connected = True
    rpc._last_track_key = None
    rpc._last_button_signature = None
    rpc._last_activity_signature = None
    rpc._last_activity_sent = 0.0
    rpc._ensure_connected = lambda: True
    return rpc, sent


def test_unchanged_activity_is_not_resent_on_every_poll(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(discord_rpc.time, "time", lambda: clock["t"])
    rpc, sent = _rpc(clock)
    for _ in range(10):  # the playback loop polls every 1-3 s
        rpc.update(title="Song", artist="Artist", album_name="Album", start_ts=900, duration=200)
        clock["t"] += 2
    assert len(sent) == 1

    # A real change goes out immediately.
    rpc.update(title="Next", artist="Artist", album_name="Album", start_ts=1020, duration=180)
    assert len(sent) == 2 and sent[-1]["details"] == "Next"

    # An unchanged activity is still refreshed now and then as a keep-alive.
    clock["t"] += discord_rpc.UNCHANGED_ACTIVITY_RESEND_SECONDS
    rpc.update(title="Next", artist="Artist", album_name="Album", start_ts=1020, duration=180)
    assert len(sent) == 3


def test_clear_forgets_the_last_activity(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(discord_rpc.time, "time", lambda: clock["t"])
    rpc, sent = _rpc(clock)
    rpc.update(title="Song", artist="Artist", start_ts=900, duration=200)
    rpc.clear()
    rpc.update(title="Song", artist="Artist", start_ts=900, duration=200)
    assert len(sent) == 2
