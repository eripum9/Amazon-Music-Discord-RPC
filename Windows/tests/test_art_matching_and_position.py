# MIT License - Copyright (c) 2026 eripum9

from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import requests

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
    media_reader._timeline_state.clear()
    now = 1_800_000_000.0
    # Windows says "45 s" but that snapshot was taken 30 s ago.
    position = media_reader.live_position("Song|Artist", "playing", 45.0, 200.0, now - 30, now=now)
    assert position == 75.0


def test_live_position_does_not_advance_when_paused_and_caps_at_duration():
    media_reader._last_snapshot.clear()
    media_reader._timeline_state.clear()
    now = 1_800_000_000.0
    assert media_reader.live_position("S|A", "paused", 45.0, 200.0, now - 30, now=now) == 45.0
    assert media_reader.live_position("S|A", "playing", 190.0, 200.0, now - 60, now=now) == 200.0


def test_live_position_without_timestamp_ignores_repeated_stale_snapshot():
    media_reader._last_snapshot.clear()
    media_reader._timeline_state.clear()
    assert media_reader.live_position("S|A", "playing", 12.0, 200.0, None) == 12.0
    assert media_reader.live_position("S|A", "playing", 12.0, 200.0, None) is None
    assert media_reader.live_position("S|A", "playing", 95.0, 200.0, None) == 95.0  # seek


def test_live_position_unknown_when_player_has_no_timeline():
    media_reader._last_snapshot.clear()
    media_reader._timeline_state.clear()
    assert media_reader.live_position("S|A", "playing", 0.0, 0.0, None) is None


def test_winrt_time_conversions():
    future = datetime.now(timezone.utc) + timedelta(days=1)
    assert media_reader._epoch_seconds(future) is None  # in the future -> ignored
    past = datetime.now(timezone.utc) - timedelta(seconds=10)
    assert abs(media_reader._epoch_seconds(past) - past.timestamp()) < 0.01
    assert media_reader._epoch_seconds(datetime(1601, 1, 1, tzinfo=timezone.utc)) is None
    assert media_reader._seconds(timedelta(seconds=83.5)) == 83.5


# --- review follow-ups (#62) -------------------------------------------------

def test_pause_resume_without_new_snapshot_excludes_paused_time():
    media_reader._last_snapshot.clear()
    media_reader._timeline_state.clear()
    live = media_reader.live_position
    # Unchanged snapshot: position 45 s taken at t=1000.
    assert live("S|A", "playing", 45.0, 300.0, 1000.0, now=1030.0) == 75.0
    assert live("S|A", "paused", 45.0, 300.0, 1000.0, now=1030.0) == 75.0
    assert live("S|A", "paused", 45.0, 300.0, 1000.0, now=1060.0) == 75.0
    assert live("S|A", "playing", 45.0, 300.0, 1000.0, now=1090.0) == 75.0
    assert live("S|A", "playing", 45.0, 300.0, 1000.0, now=1100.0) == 85.0
    # A refreshed snapshot resets the pause bookkeeping.
    assert live("S|A", "playing", 120.0, 300.0, 1200.0, now=1205.0) == 125.0


def test_first_paused_observation_does_not_extrapolate():
    media_reader._timeline_state.clear()
    assert media_reader.live_position("S|A", "paused", 45.0, 300.0, 1000.0, now=1500.0) == 45.0


def _query_of(url):
    text = unquote(url)
    return text.split("q=", 1)[1] if "q=" in text else text.split("term=", 1)[1]


def test_known_album_is_checked_before_an_early_exit(monkeypatch):
    album_art._cache.clear()
    calls = []

    def fake(url, timeout=5):
        calls.append(_query_of(url))
        if "deezer" not in url:
            return _Response({"results": []})
        if 'album:"XYZ"' in _query_of(url):
            return _Response({"data": [_deezer("Song", "Artist", "XYZ", 200)]})
        return _Response({"data": [_deezer("Song", "Artist", "ABC", 200)]})

    monkeypatch.setattr(album_art.requests, "get", fake)
    art, album, _, _ = album_art.get_album_art("Song", "Artist", deezer_enabled=True, itunes_enabled=False, album="XYZ", duration=200)
    assert album == "XYZ" and art.endswith("XYZ.jpg")
    assert 'album:"XYZ"' in calls[0]


def test_strong_match_with_wrong_album_is_not_final():
    candidate = {"title": "Song", "artist": "Artist", "album": "ABC", "duration": 200, "art_url": "x"}
    score = album_art.score_candidate(candidate, "Song", "Artist", "XYZ", 200)
    assert score >= album_art.GOOD_MATCH_SCORE - 0.1
    assert album_art._satisfies_context(candidate, score, "Song", "XYZ") is False
    assert album_art._satisfies_context(candidate, 0.95, "Song", "") is True


def test_lookup_respects_the_total_time_budget(monkeypatch):
    album_art._cache.clear()
    clock = {"t": 0.0}
    timeouts = []
    monkeypatch.setattr(album_art, "_monotonic", lambda: clock["t"])

    def slow(url, timeout=5):
        timeouts.append(timeout)
        clock["t"] += timeout          # every request times out
        raise requests.Timeout()

    monkeypatch.setattr(album_art.requests, "get", slow)
    result = album_art.get_album_art("Song", "Artist", deezer_enabled=True, itunes_enabled=True, album="Album")
    assert result == (None, "", "", 0)
    assert clock["t"] <= album_art.ARTWORK_LOOKUP_BUDGET_SECONDS
    assert all(t <= album_art.PER_REQUEST_TIMEOUT_SECONDS for t in timeouts)
    assert len(timeouts) < 5


def test_cache_identity_includes_duration(monkeypatch):
    album_art._cache.clear()
    results = [
        _deezer("Song", "Artist", "Single", 200),
        _deezer("Song", "Artist", "Extended", 320),
    ]
    monkeypatch.setattr(album_art.requests, "get", _fake_get(results))
    _, short_album, _, _ = album_art.get_album_art("Song", "Artist", deezer_enabled=True, itunes_enabled=False, duration=200)
    _, long_album, _, _ = album_art.get_album_art("Song", "Artist", deezer_enabled=True, itunes_enabled=False, duration=320)
    assert (short_album, long_album) == ("Single", "Extended")


def test_every_contacted_provider_is_recorded(monkeypatch):
    album_art._cache.clear()
    events = []
    monkeypatch.setattr(album_art, "_network_event", lambda service, operation, status, detail="": events.append((service, operation, status)))
    itunes = [{
        "trackName": "La Bachata", "artistName": "Manuel Turizo", "collectionName": "2000",
        "artworkUrl100": "https://itunes/100x100bb.jpg", "trackTimeMillis": 162000,
    }]
    monkeypatch.setattr(album_art.requests, "get", _fake_get([_deezer("Other", "Someone", "X", 100)], itunes))
    album_art.get_album_art("La Bachata", "Manuel Turizo", deezer_enabled=True, itunes_enabled=True)
    deezer_calls = [e for e in events if e[0] == "deezer" and e[1] == "artwork-lookup"]
    itunes_calls = [e for e in events if e[0] == "itunes" and e[1] == "artwork-lookup"]
    assert len(deezer_calls) >= 2 and itunes_calls
    assert all(status == "success" for _, _, status in deezer_calls + itunes_calls)
