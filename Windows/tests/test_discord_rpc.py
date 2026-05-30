import discord_rpc
from discord_rpc import DiscordRPC, _button_signature, _discord_asset_text


class FakePresence:
    def __init__(self):
        self.calls = []

    def update(self, payload_override=None):
        self.calls.append(("update", payload_override))
        return {"ok": True}

    def clear(self):
        self.calls.append(("clear", None))


def make_rpc(fake):
    rpc = DiscordRPC.__new__(DiscordRPC)
    rpc.client_id = "client"
    rpc.rpc = fake
    rpc.connected = True
    rpc._last_track_key = None
    rpc._last_button_signature = None
    rpc._backoff = 3
    rpc._next_retry = 0
    return rpc


def test_asset_text_handles_one_letter_album_and_track():
    assert _discord_asset_text("Z", "Off the Record") == "Album: Z"
    assert _discord_asset_text("", "A") == "Track: A"
    assert _discord_asset_text("Wolf", "IFHY") == "Wolf"
    assert len(_discord_asset_text("Z", "Off the Record")) >= 2


def test_button_url_changes_clear_presence(monkeypatch):
    monkeypatch.setattr(discord_rpc.time, "sleep", lambda _: None)
    fake = FakePresence()
    rpc = make_rpc(fake)
    rpc.update("Song A", "Artist", buttons=[{"label": "Listen on Amazon Music", "url": "https://music.amazon.com/tracks/a"}])
    rpc.update("Song B", "Artist", buttons=[{"label": "Listen on Amazon Music", "url": "https://music.amazon.com/tracks/b"}])
    rpc.update("Song C", "Artist")
    assert _button_signature([{"label": "A", "url": "1"}]) != _button_signature([{"label": "A", "url": "2"}])
    assert [call[0] for call in fake.calls] == ["update", "clear", "update", "clear", "update"]
    assert fake.calls[-1][1]["args"]["activity"]["buttons"] == []
