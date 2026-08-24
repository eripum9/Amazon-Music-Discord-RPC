# MIT License - Copyright (c) 2026 eripum9

from Shared import playback


def test_track_normalisation_is_bounded_and_clamps_position():
    result = playback.normalise_track(
        {
            "status": "found",
            "playback_status": "PAUSED",
            "title": "  Song  ",
            "artist": " Artist ",
            "position": "500",
            "duration": "180",
            "_amazon_art_url": "https://example.com/art.jpg",
        },
        "native_backend",
    )
    assert result == {
        "title": "Song",
        "artist": "Artist",
        "album": "",
        "status": "paused",
        "position": 180.0,
        "duration": 180.0,
        "art_url": "https://example.com/art.jpg",
        "track_link": "",
        "source": "native_backend",
    }
    assert playback.normalise_track({"artist": "Artist"}) is None


def test_privacy_matching_accepts_string_and_list_keywords():
    assert playback.privacy_match(
        {"privacy_blocked_keywords": "Work, Secret\nPodcast"},
        "My SECRET Song",
    ) == "Matched privacy keyword: secret"
    assert playback.privacy_keywords([" One ", "TWO"]) == ["one", "two"]
    assert playback.privacy_match({"privacy_private_session": True}, "Song") == "Private session enabled"


def test_process_matching_accepts_windows_and_macos_names_on_any_host():
    configured = playback.configured_game_mode_processes(
        {"game_mode_processes": "Game.exe, C:\\Tools\\OtherGame.exe\nMacGame.app"}
    )
    assert configured == {"game.exe", "othergame.exe", "macgame.app"}
    assert playback.game_mode_matches_processes(configured, {"game"})
    assert playback.game_mode_matches_processes({"othergame"}, {"OtherGame.exe"})
    assert playback.game_mode_matches_processes({"macgame.app"}, {"MacGame"})
    assert not playback.game_mode_matches_processes({"game"}, {"editor"})


def test_remembered_mapping_supports_composite_and_legacy_title_keys():
    track = {"title": " Raw   Song ", "artist": "Artist", "album": "Original"}
    composite = {
        "track_mappings": {
            "raw song|artist": {"title": "Fixed", "album": "Correct Album"},
        }
    }
    assert playback.apply_track_mapping(composite, track) == {
        "title": "Fixed",
        "artist": "Artist",
        "album": "Correct Album",
    }
    legacy = {"track_mappings": {"raw song": {"artist": "Found Artist"}}}
    assert playback.apply_track_mapping(legacy, track)["artist"] == "Found Artist"


def test_custom_art_matches_aliases():
    result = playback.find_custom_album_art(
        {
            "custom_albums": [
                {
                    "album": "Canonical Album",
                    "aliases": "Deluxe Name, Localised Name",
                    "art_url": "https://example.com/custom.png",
                }
            ]
        },
        " localised   name ",
    )
    assert result == {
        "album": "Canonical Album",
        "art_url": "https://example.com/custom.png",
    }


def test_scrobble_eligibility_boundaries():
    assert not playback.scrobble_eligible(29.999, 40)
    assert playback.scrobble_eligible(30, 60)
    assert not playback.scrobble_eligible(30, 180)
    assert playback.scrobble_eligible(90, 180)
    assert not playback.scrobble_eligible(239.999, 0)
    assert playback.scrobble_eligible(240, 0)
