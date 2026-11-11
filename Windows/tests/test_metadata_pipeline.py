# MIT License - Copyright (c) 2026 eripum9

import metadata_pipeline


def test_devtools_source_wins_before_fallback_track():
    fallback = {
        "title": "Wrong",
        "artist": "Wrong",
        "album": "",
        "status": "playing",
        "position": 0,
        "duration": 0,
    }
    devtools = {
        "status": "found",
        "title": "Correct",
        "artist": "Artist",
        "album": "Album",
    }

    def apply_fn(track, payload):
        merged = dict(track)
        merged.update({key: payload[key] for key in ("title", "artist", "album")})
        return merged, True

    track, changed, found = metadata_pipeline.apply_devtools_source(fallback, devtools, apply_fn)
    assert found is True
    assert changed is True
    assert track["title"] == "Correct"
    assert track["artist"] == "Artist"
    assert track["album"] == "Album"


def test_notification_metadata_only_merges_matching_tracks():
    track = {"title": "Song", "artist": "SMTC", "album": "", "status": "playing"}
    notification = {"title": "Song", "artist": "Notif Artist", "album": "Notif Album"}
    merged, notif_album, keep = metadata_pipeline.merge_notification_metadata(track, notification)
    assert keep is True
    assert notif_album == "Notif Album"
    assert merged["artist"] == "Notif Artist"
    assert merged["album"] == "Notif Album"
    stale, stale_album, stale_keep = metadata_pipeline.merge_notification_metadata(track, {"title": "Other"})
    assert stale == track
    assert stale_album is None
    assert stale_keep is False


def test_link_buttons_and_art_state_are_provider_aware():
    search = lambda title, artist, region: f"https://music.amazon.{region}/search/{title}-{artist}"
    amazon_buttons = metadata_pipeline.link_buttons(True, "amazon", "de", "", "", "Noid", "Tyler", search)
    deezer_buttons = metadata_pipeline.link_buttons(True, "deezer", "com", "", "https://deezer.example/track", "Noid", "Tyler", search)
    art_state = metadata_pipeline.apply_art_result(
        {"album": "Amazon Album", "_amazon_art_url": "https://amazon.example/art.jpg", "_amazon_track_link": "https://music.amazon.com/tracks/1", "duration": 200},
        fetched=("https://deezer.example/art.jpg", "Deezer Album", "https://deezer.example/track", 199),
    )
    assert amazon_buttons == [{"label": "Listen on Amazon Music", "url": "https://music.amazon.de/search/Noid-Tyler"}]
    assert deezer_buttons == [{"label": "Listen on Deezer", "url": "https://deezer.example/track"}]
    assert art_state["art_url"] == "https://amazon.example/art.jpg"
    assert art_state["album"] == "Amazon Album"
    assert art_state["amazon_link"] == "https://music.amazon.com/tracks/1"


def test_autoplay_labels_are_not_album_hints():
    for label in ("Autoplay: Song", "Reproducci\u00f3n autom\u00e1tica: Song",
                  "Automatische Wiedergabe: Song", "Lecture automatique: Song"):
        assert metadata_pipeline.album_from_player_label(label) == ""
    assert metadata_pipeline.album_from_player_label("Selected Album") == "Selected Album"


def test_manual_art_album_and_duration_win_over_native_and_notification():
    state = metadata_pipeline.apply_art_result(
        {"album": "Native", "_amazon_art_url": "https://art.test/native", "duration": 200},
        resolved=("https://art.test/chosen", "Chosen", "https://deezer.test/chosen", 210),
        fetched=("https://art.test/obsolete", "Obsolete", "", 180), notification_album="Notification",
    )
    assert (state["art_url"], state["album"], state["deezer_link"], state["duration"]) == (
        "https://art.test/chosen", "Chosen", "https://deezer.test/chosen", 210,
    )
