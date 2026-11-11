# MIT License - Copyright (c) 2026 eripum9

from urllib.parse import parse_qs, urlsplit

import pytest
import requests
import threading

import album_art as art


def recording(title="Song", artist="Artist", album="Album", duration=200, **kw):
    return {"title": title, "artist": artist, "album": album, "duration": duration,
            "art_url": "https://art.test/cover", "track_link": "https://deezer.test/track",
            "source": "deezer", **kw}


@pytest.mark.parametrize("title,artist,candidate", [
    ("Tit\u00ed Me Pregunt\u00f3 (feat. Nadie)", "Bad Bunny",
     recording("Titi Me Pregunto", "Bad Bunny", "Un Verano Sin Ti")),
    ("Bohemian Rhapsody - Remastered 2011", "Queen",
     recording("Bohemian Rhapsody", "Queen", "A Night At The Opera")),
    ("Sessions", "Shakira, Bizarrap", recording("Sessions", "Bizarrap")),
])
def test_normalized_metadata_matches(title, artist, candidate):
    assert art.score_candidate(candidate, title, artist) >= art.GOOD_MATCH_SCORE


def test_best_candidate_not_first_and_live_version_agrees(monkeypatch):
    candidates = [recording(artist="Tribute band"), recording(duration=320),
                  recording(title="Song (Live)", album="Concert (Live)", duration=200)]
    monkeypatch.setattr(art, "_deezer_candidates", lambda *_a, **_kw: candidates)
    best, _ = art.find_best_match("Song (Live)", "Artist", duration=200,
                                  deezer_enabled=True, itunes_enabled=False)
    assert best is candidates[2]
    assert art.score_candidate(recording("Completely Different", "Other"),
                                "Song", "Artist") < art.MIN_MATCH_SCORE


def test_supplied_album_query_precedes_incorrect_strong_result(monkeypatch):
    queries = []

    def candidates(query, **_kw):
        queries.append(query)
        return [recording(album="XYZ" if 'album:"XYZ"' in query else "ABC")]

    monkeypatch.setattr(art, "_deezer_candidates", candidates)
    best, _ = art.find_best_match("Song", "Artist", album="XYZ", duration=200,
                                  deezer_enabled=True, itunes_enabled=False)
    assert best["album"] == "XYZ"
    assert 'album:"XYZ"' in queries[0]
    assert not art._satisfies_context(recording(album="ABC"), 0.95, "Song", "XYZ")


def test_cache_duration_and_provider_policy_identity(monkeypatch):
    art._cache.clear()
    calls = []

    def match(*_args, **kw):
        calls.append((_args, kw))
        return recording(duration=_args[3]), 1.0

    monkeypatch.setattr(art, "find_best_match", match)
    try:
        for duration in (200, 320, 200):
            assert art.get_album_art("Song", "Artist", True, False, duration=duration)[3] == duration
        assert len(calls) == 2
        assert art.get_album_art("Song", "Artist", False, False, duration=200) == (None, "", "", 0)
        assert len(calls) == 2
    finally:
        art._cache.clear()


def test_deezer_outage_reserves_itunes_budget_and_audits_every_attempt(monkeypatch):
    clock, attempts, audit = [0.0], [], []
    monkeypatch.setattr(art, "_monotonic", lambda: clock[0])
    monkeypatch.setattr(art, "_network_event", lambda *args: audit.append(args))

    def get_json(url, deadline, _cancel_event=None):
        attempts.append((url, deadline))
        if "deezer" in url:
            clock[0] = deadline
            raise requests.Timeout()
        return {"results": [{"trackName": "Song", "artistName": "Artist", "collectionName": "Album",
                             "artworkUrl100": "https://art.test/100x100bb.jpg", "trackTimeMillis": 200000}]}

    monkeypatch.setattr(art, "_get_json", get_json)
    best, _ = art.find_best_match("Song", "Artist", album="Album", duration=200,
                                  deezer_enabled=True, itunes_enabled=True)
    assert best["source"] == "itunes"
    assert best["duration"] == 200
    assert [urlsplit(url).hostname for url, _ in attempts] == ["api.deezer.com", "itunes.apple.com"]
    assert attempts[0][1] == pytest.approx(4.8)
    assert attempts[1][1] == 8
    assert [entry[:3] for entry in audit] == [
        ("deezer", "artwork-lookup", "error"), ("itunes", "artwork-lookup", "success")]
    assert all("Song" not in entry[3] and "Artist" not in entry[3] for entry in audit)


def test_provider_queries_carry_real_album_and_duration_context(monkeypatch):
    seen = []

    def get_json(url, *_args):
        seen.append(parse_qs(urlsplit(url).query)["q"][0])
        return {"data": [{"title": "Song", "artist": {"name": "Artist"},
                          "album": {"title": "Album", "cover_xl": "https://art.test/image"},
                          "link": "https://deezer.test/track", "duration": 200}]}

    monkeypatch.setattr(art, "_get_json", get_json)
    best, score = art.find_best_match("Song", "Artist", album="Album", duration=200,
                                     deezer_enabled=True, itunes_enabled=False)
    assert best["duration"] == 200 and score == 1.0
    assert seen == ['artist:"Artist" album:"Album" track:"Song"']


def test_cancellation_suppresses_followup_provider_and_cache_write(monkeypatch):
    cancelled = threading.Event()
    contacted = []

    def get_json(url, *_args):
        contacted.append(url)
        cancelled.set()
        raise requests.Timeout()

    monkeypatch.setattr(art, "_get_json", get_json)
    art._cache.clear()
    assert art.get_album_art("Private", "Artist", True, True, cancel_event=cancelled) == (None, "", "", 0)
    assert len(contacted) == 1
    assert not art._cache
