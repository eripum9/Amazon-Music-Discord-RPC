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
    assert art_state["album"] == "Deezer Album"
    assert art_state["amazon_link"] == "https://music.amazon.com/tracks/1"


def test_player_bar_label_is_only_an_album_hint():
    assert metadata_pipeline.album_from_player_label("Reproducci\u00f3n autom\u00e1tica: El Viejo") == ""
    assert metadata_pipeline.album_from_player_label("Autoplay: Pompeii") == ""
    assert metadata_pipeline.album_from_player_label("11: 59") == "11: 59"
    assert metadata_pipeline.album_from_player_label("Radio") == "Radio"


def test_album_comes_from_the_track_match_not_the_play_context():
    amazon = {"album": "Pompeii", "_amazon_art_url": "https://amazon.example/illuminate.jpg", "duration": 187}
    state = metadata_pipeline.apply_art_result(
        amazon,
        fetched=("https://deezer.example/illuminate.jpg", "Illuminate", "https://deezer.example/t", 187),
        previous_album="",
    )
    assert state["album"] == "Illuminate"
    assert state["art_url"] == "https://amazon.example/illuminate.jpg"


def test_player_spelling_kept_when_it_is_the_same_album():
    state = metadata_pipeline.apply_art_result(
        {"album": "11: 59", "_amazon_art_url": "https://amazon.example/a.jpg"},
        fetched=("https://deezer.example/a.jpg", "11:59", "", 200),
    )
    assert state["album"] == "11: 59"


def test_new_track_never_inherits_the_previous_album():
    autoplay = {"album": "Reproducci\u00f3n autom\u00e1tica: El Viejo", "_amazon_art_url": "https://amazon.example/b.jpg"}
    state = metadata_pipeline.apply_art_result(autoplay, fetched=(None, "", "", 0), previous_album="")
    assert state["album"] == ""
    resolved = metadata_pipeline.apply_art_result(
        {"album": "Pompeii"}, resolved=("https://x/r.jpg", "Chosen Album", "", 180), previous_album="Bad Blood",
    )
    assert resolved["album"] == "Chosen Album"
