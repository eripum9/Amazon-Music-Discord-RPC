# MIT License - Copyright (c) 2026 eripum9

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

    def close(self):
        self.calls.append(("close", None))


def make_rpc(fake):
    rpc = DiscordRPC.__new__(DiscordRPC)
    rpc.client_id = "client"
    rpc.rpc = fake
    rpc.connected = True
    rpc._last_track_key = None
    rpc._last_button_signature = None
    rpc._backoff = 3
    rpc._next_retry = 0
    rpc._closed = False
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


def _activity_for(status_display, title="Song", artist="Artist", album_name="Album"):
    fake = FakePresence()
    rpc = make_rpc(fake)
    rpc.update(title, artist, album_name=album_name, status_display=status_display)
    return fake.calls[-1][1]["args"]["activity"]


def test_status_display_modes_select_expected_discord_field():
    application = _activity_for("application")
    artist = _activity_for("artist")
    album = _activity_for("album")
    track = _activity_for("track")

    assert application["status_display_type"] == 0
    assert application["state"] == "by Artist"
    assert artist["status_display_type"] == 1
    assert artist["state"] == "Artist"
    assert album["status_display_type"] == 1
    assert album["state"] == "Album"
    assert album["details"] == "Song by Artist"
    assert track["status_display_type"] == 2
    assert track["details"] == "Song"


def test_status_fields_are_valid_and_album_falls_back_to_artist():
    activity = _activity_for("album", title="A", artist="B" * 200, album_name="")
    assert activity["details"].startswith("Track: A by ")
    assert 2 <= len(activity["details"]) <= 128
    assert 2 <= len(activity["state"]) <= 128
    assert activity["state"] == ("B" * 128)

    invalid = _activity_for("not-a-mode")
    assert invalid["status_display_type"] == 1
    assert invalid["state"] == "Artist"


def test_unknown_artist_falls_back_to_amazon_music_status():
    for artist in ("", "Unknown", "Unknown Artist", "N/A", "None"):
        for mode in ("artist", "album", "track", "application"):
            activity = _activity_for(mode, artist=artist)
            assert activity["status_display_type"] == 0
            assert activity["state"] == "Unknown Artist"


def test_one_character_artist_does_not_leak_helper_label_into_byline():
    application = _activity_for("application", artist="A")
    album = _activity_for("album", artist="A")
    track = _activity_for("track", artist="A")

    assert application["state"] == "by A"
    assert album["details"] == "Song by A"
    assert track["state"] == "by A"


def test_shutdown_closes_transport_even_when_presence_clear_fails():
    class FailingClearPresence(FakePresence):
        def clear(self):
            self.calls.append(("clear", None))
            raise RuntimeError("update transport failed")

    fake = FailingClearPresence()
    rpc = make_rpc(fake)
    rpc.shutdown()
    assert [call[0] for call in fake.calls] == ["clear", "close"]
    assert rpc.connected is False
    assert rpc._closed is True


def test_shutdown_attempts_clear_after_update_marked_transport_disconnected():
    fake = FakePresence()
    rpc = make_rpc(fake)
    rpc.connected = False
    rpc.shutdown()
    assert [call[0] for call in fake.calls] == ["clear", "close"]
