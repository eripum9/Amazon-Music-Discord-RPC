# MIT License - Copyright (c) 2026 eripum9

import importlib

import pytest


def test_matcher_considers_distinct_duration_variants(monkeypatch):
    artwork = importlib.import_module("album_art")
    find_best_match = getattr(artwork, "find_best_match", None)
    if find_best_match is None:
        pytest.skip("Baseline has no scored artwork matcher")

    wrong = {
        "source": "deezer", "title": "Song", "artist": "Artist", "album": "Album",
        "art_url": "https://art.test/album", "track_link": "https://deezer.test/long-version",
        "duration": 320,
    }
    correct = {**wrong, "track_link": "https://deezer.test/requested-version", "duration": 200}
    monkeypatch.setattr(artwork, "_deezer_candidates", lambda *_args, **_kw: [wrong, correct])

    match, _score = find_best_match("Song", "Artist", album="Album", duration=200,
                                  deezer_enabled=True, itunes_enabled=False)

    assert match is not None
    assert match["duration"] == 200
    assert match["track_link"] == correct["track_link"]
