# MIT License - Copyright (c) 2026 eripum9

from datetime import datetime, timedelta, timezone

import album_art
import media_reader


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _deezer(title, artist, album, duration, cover="deezer"):
    return {
        "title": title,
        "artist": {"name": artist},
        "album": {"title": album, "cover_xl": f"https://{cover}/{album}.jpg"},
        "link": f"https://deezer.com/{title}",
        "duration": duration,
    }


def _fake_get(deezer_results, itunes_results=()):
    def fake(url, timeout=5):
        if "deezer" in url:
            return _Response({"data": list(deezer_results)})
        return _Response({"results": list(itunes_results)})
    return fake


def test_picks_best_scoring_candidate_not_first_hit(monkeypatch):
    album_art._cache.clear()
    results = [
        _deezer("Blinding Lights (Cover)", "Some Tribute Band", "Pop Covers 2020", 201),
        _deezer("Blinding Lights", "The Weeknd", "Blinding Lights (Remixes)", 260),
        _deezer("Blinding Lights", "The Weeknd", "After Hours", 200),
    ]
    monkeypatch.setattr(album_art.requests, "get", _fake_get(results))
    art, album, _, duration = album_art.get_album_art(
        "Blinding Lights", "The Weeknd", deezer_enabled=True, itunes_enabled=False,
        album="After Hours", duration=200,
    )
    assert album == "After Hours"
    assert art.endswith("After Hours.jpg")
    assert duration == 200


def test_accents_featuring_and_remaster_suffix_still_match(monkeypatch):
    album_art._cache.clear()
    results = [_deezer("Titi Me Pregunto", "Bad Bunny", "Un Verano Sin Ti", 243)]
    monkeypatch.setattr(album_art.requests, "get", _fake_get(results))
    art, album, _, _ = album_art.get_album_art(
        "Tití Me Preguntó (feat. Nadie)", "Bad Bunny", deezer_enabled=True, itunes_enabled=False,
    )
    assert album == "Un Verano Sin Ti" and art

    album_art._cache.clear()
    results = [_deezer("Bohemian Rhapsody", "Queen", "A Night At The Opera", 355)]
    monkeypatch.setattr(album_art.requests, "get", _fake_get(results))
    _, album, _, _ = album_art.get_album_art(
        "Bohemian Rhapsody - Remastered 2011", "Queen", deezer_enabled=True, itunes_enabled=False,
    )
    assert album == "A Night At The Opera"


def test_multiple_amazon_artists_match_any_listed_artist(monkeypatch):
    album_art._cache.clear()
    results = [_deezer("Shakira: Bzrp Music Sessions, Vol. 53", "Bizarrap", "Bzrp Sessions", 218)]
    monkeypatch.setattr(album_art.requests, "get", _fake_get(results))
    _, album, _, _ = album_art.get_album_art(
        "Shakira: Bzrp Music Sessions, Vol. 53", "Shakira, Bizarrap", deezer_enabled=True, itunes_enabled=False,
    )
    assert album == "Bzrp Sessions"


def test_wrong_song_is_rejected_instead_of_showing_bad_art(monkeypatch):
    album_art._cache.clear()
    results = [_deezer("Completely Different", "Another Artist", "Other Album", 180)]
    monkeypatch.setattr(album_art.requests, "get", _fake_get(results))
    assert album_art.get_album_art(
        "Mi Cancion", "Mi Artista", deezer_enabled=True, itunes_enabled=False,
    ) == (None, "", "", 0)


def test_live_version_preferred_when_title_says_live(monkeypatch):
    album_art._cache.clear()
    results = [
        _deezer("Hotel California", "Eagles", "Hotel California", 391),
        _deezer("Hotel California (Live)", "Eagles", "Hell Freezes Over (Live)", 434),
    ]
    monkeypatch.setattr(album_art.requests, "get", _fake_get(results))
    _, album, _, _ = album_art.get_album_art(
        "Hotel California (Live)", "Eagles", deezer_enabled=True, itunes_enabled=False,
    )
    assert album == "Hell Freezes Over (Live)"


def test_itunes_fallback_used_when_deezer_has_no_match(monkeypatch):
    album_art._cache.clear()
    itunes = [{
        "trackName": "La Bachata", "artistName": "Manuel Turizo", "collectionName": "2000",
        "artworkUrl100": "https://itunes/100x100bb.jpg", "trackTimeMillis": 162000,
    }]
    monkeypatch.setattr(album_art.requests, "get", _fake_get([], itunes))
    art, album, link, duration = album_art.get_album_art(
        "La Bachata", "Manuel Turizo", deezer_enabled=True, itunes_enabled=True,
    )
    assert album == "2000" and art.endswith("600x600bb.jpg") and link == "" and duration == 162


# --- playback position -----------------------------------------------------

def test_live_position_advances_stale_snapshot_while_playing():
    media_reader._last_snapshot.clear()
    now = 1_800_000_000.0
    # Windows says "45 s" but that snapshot was taken 30 s ago.
    position = media_reader.live_position("Song|Artist", "playing", 45.0, 200.0, now - 30, now=now)
    assert position == 75.0


def test_live_position_does_not_advance_when_paused_and_caps_at_duration():
    media_reader._last_snapshot.clear()
    now = 1_800_000_000.0
    assert media_reader.live_position("S|A", "paused", 45.0, 200.0, now - 30, now=now) == 45.0
    assert media_reader.live_position("S|A", "playing", 190.0, 200.0, now - 60, now=now) == 200.0


def test_live_position_without_timestamp_ignores_repeated_stale_snapshot():
    media_reader._last_snapshot.clear()
    assert media_reader.live_position("S|A", "playing", 12.0, 200.0, None) == 12.0
    assert media_reader.live_position("S|A", "playing", 12.0, 200.0, None) is None
    assert media_reader.live_position("S|A", "playing", 95.0, 200.0, None) == 95.0  # seek


def test_live_position_unknown_when_player_has_no_timeline():
    media_reader._last_snapshot.clear()
    assert media_reader.live_position("S|A", "playing", 0.0, 0.0, None) is None


def test_winrt_time_conversions():
    future = datetime.now(timezone.utc) + timedelta(days=1)
    assert media_reader._epoch_seconds(future) is None  # in the future -> ignored
    past = datetime.now(timezone.utc) - timedelta(seconds=10)
    assert abs(media_reader._epoch_seconds(past) - past.timestamp()) < 0.01
    assert media_reader._epoch_seconds(datetime(1601, 1, 1, tzinfo=timezone.utc)) is None
    assert media_reader._seconds(timedelta(seconds=83.5)) == 83.5
