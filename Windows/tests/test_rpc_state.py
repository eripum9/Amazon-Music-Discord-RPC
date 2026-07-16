# MIT License - Copyright (c) 2026 eripum9

import rpc_state


def test_resolved_track_store_keeps_art_and_duration():
    store = rpc_state.ResolvedTrackStore()
    store.cache["Raw|Artist"] = ("Fixed", "Artist")
    track = {
        "title": "Fixed",
        "artist": "Artist",
        "album": "Album",
        "art_url": "https://example.com/art.jpg",
        "track_link": "https://example.com/track",
        "duration": "123.9",
    }
    store.store_track("Raw|Artist", track)
    assert store.apply_cache("Raw|Artist", "Raw", "Artist") == ("Fixed", "Artist", True)
    assert store.resolved_art("Raw|Artist", "Fixed", "Artist") == (
        "https://example.com/art.jpg",
        "Album",
        "https://example.com/track",
        123,
    )
    store.clear_choice("Raw|Artist")
    assert store.apply_cache("Raw|Artist", "Raw", "Artist") == ("Raw", "Artist", False)


def test_game_mode_state_caches_process_matches_and_suppresses_once():
    state = rpc_state.GameModeState()
    messages = []
    config = {"game_mode_enabled": False, "game_mode_processes": "Game.exe"}
    assert state.should_prompt_wrong_song(
        "Song|Song",
        "Song",
        "Song",
        config,
        lambda: {"game"},
        lambda: messages.append("suppressed"),
    ) is False
    assert state.should_prompt_wrong_song(
        "Song|Song",
        "Song",
        "Song",
        config,
        lambda: {"game"},
        lambda: messages.append("suppressed"),
    ) is False
    assert messages == ["suppressed"]
    assert state.should_prompt_wrong_song("Song|Artist", "Song", "Artist", config, lambda: set()) is False
    assert state.should_prompt_wrong_song("Track|Track", "Track", "Track", {"game_mode_enabled": False, "game_mode_processes": ""}, lambda: set()) is True


def test_hidden_privacy_track_preserves_status_and_time():
    hidden = rpc_state.hidden_privacy_track({"status": "paused", "position": 42, "duration": 180})
    assert hidden == {
        "title": "Hidden by privacy controls",
        "artist": "",
        "album": "",
        "status": "paused",
        "position": 42,
        "duration": 180,
    }
