from unittest.mock import patch

import main


def test_game_mode_process_matching_and_wrong_song_suppression():
    main._game_mode_suppressed_keys.clear()
    configured = main._configured_game_mode_processes({"game_mode_processes": "Game.exe, C:\\Tools\\OtherGame.exe\nNoExt"})
    assert configured == {"game.exe", "othergame.exe", "noext"}
    assert main._game_mode_matches_processes(configured, {"game.exe"})
    assert main._game_mode_matches_processes({"noext"}, {"NoExt.exe"})
    assert main._should_prompt_wrong_song("Song|Song", "Song", "Song", {"game_mode_enabled": False, "game_mode_processes": ""})
    assert not main._should_prompt_wrong_song("Song|Song", "Song", "Song", {"game_mode_enabled": True, "game_mode_processes": ""})
    assert not main._should_prompt_wrong_song("Song|Artist", "Song", "Artist", {"game_mode_enabled": False, "game_mode_processes": ""})


def test_playback_time_resyncs_on_resume_and_seek():
    main._track_timing_cache.clear()
    with patch("main.time.time", return_value=1000):
        resumed_ts, resumed_paused, refreshed = main._playing_start_ts(
            {"position": 104},
            "Song|Artist",
            None,
            100,
            True,
        )
        fallback_ts, fallback_paused, fallback_refreshed = main._playing_start_ts(
            {"position": None},
            "Song|Artist",
            None,
            100,
            True,
        )
        seek_forward_ts, seek_forward_paused, seek_forward_refreshed = main._playing_start_ts(
            {"position": 90},
            "Song|Artist",
            930,
            None,
            False,
        )
        seek_back_ts, seek_back_paused, seek_back_refreshed = main._playing_start_ts(
            {"position": 40},
            "Song|Artist",
            900,
            None,
            False,
        )
        stable_ts, stable_paused, stable_refreshed = main._playing_start_ts(
            {"position": 101},
            "Song|Artist",
            900,
            None,
            False,
        )
        zero_ts = main._track_start_ts({"position": 0}, "Fresh|Track", use_cache=False)
    assert (resumed_ts, resumed_paused, refreshed) == (896, None, True)
    assert (fallback_ts, fallback_paused, fallback_refreshed) == (900, None, False)
    assert (seek_forward_ts, seek_forward_paused, seek_forward_refreshed) == (910, None, True)
    assert (seek_back_ts, seek_back_paused, seek_back_refreshed) == (960, None, True)
    assert (stable_ts, stable_paused, stable_refreshed) == (900, None, False)
    assert zero_ts == 1000


def test_devtools_no_track_state_preserves_actionable_statuses():
    unavailable = {"enabled": True, "status": "unavailable", "detail": "DevTools unavailable"}
    error = {"enabled": True, "status": "error", "detail": "Socket failed"}
    launching = {"enabled": True, "status": "launching", "detail": "Starting Amazon Music"}
    restarting = {"enabled": True, "status": "restarting", "detail": "Restarting Amazon Music"}
    waiting = main._devtools_no_track_state(True, {"enabled": True, "status": "no_match", "detail": "No title"})
    assert main._devtools_no_track_state(True, unavailable) == unavailable
    assert main._devtools_no_track_state(True, error) == error
    assert main._devtools_no_track_state(True, launching) == launching
    assert main._devtools_no_track_state(True, restarting) == restarting
    assert waiting["status"] == "waiting"
    assert main._devtools_no_track_state(False, unavailable) == unavailable
