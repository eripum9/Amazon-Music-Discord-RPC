import main
import qt_tray_ui
from status_summary import metadata_source_summary


def test_metadata_source_summary_labels():
    private = metadata_source_summary({"privacy": {"hidden": True, "reason": "Keyword filter"}}, {})
    amazon = metadata_source_summary(
        {"track": {"status": "playing", "title": "Song"}, "amazon_devtools": {"status": "found", "title": "Song"}},
        {"amazon_devtools_enabled": True},
    )
    paused = metadata_source_summary({"track": {"status": "paused", "title": "Song"}}, {})
    notify = metadata_source_summary(
        {"track": {"status": "playing", "title": "Song"}, "notification": {"title": "Song"}},
        {"notification_enrichment_enabled": True},
    )
    smtc = metadata_source_summary({"track": {"status": "playing", "title": "Song"}}, {})
    assert private["label"] == "Private"
    assert amazon["label"] == "Amazon Metadata"
    assert paused["label"] == "Paused"
    assert notify["label"] == "Notification Fallback"
    assert smtc["label"] == "SMTC Fallback"


def test_tray_snapshot_payload_and_geometry():
    old_running = main.rpc_running
    old_config = dict(main.current_config) if isinstance(main.current_config, dict) else {}
    main.rpc_running = True
    main.current_config = {
        **old_config,
        "privacy_private_session": False,
        "amazon_devtools_enabled": True,
        "game_mode_enabled": True,
        "song_link_provider": "amazon",
    }
    try:
        snapshot = main._tray_menu_snapshot(
            {
                "discord_status": "connected",
                "presence_visible": True,
                "track": {
                    "title": "Rusty",
                    "artist": "Tyler, The Creator",
                    "album": "Wolf",
                    "position": 65,
                    "duration": 315,
                    "status": "playing",
                },
                "amazon_devtools": {"status": "found", "title": "Rusty"},
                "track_link": "https://music.amazon.com/search/Rusty",
            }
        )
    finally:
        main.rpc_running = old_running
        main.current_config = old_config
    payload = qt_tray_ui.drawer_payload(snapshot)
    bottom_right = qt_tray_ui.drawer_geometry(10_000, 10_000, (0, 0, 1920, 1080))
    top_left = qt_tray_ui.drawer_geometry(0, 0, (0, 0, 320, 500))
    assert snapshot["rpc"] == "On"
    assert snapshot["discord"] == "Connected"
    assert snapshot["source"] == "Amazon Metadata"
    assert snapshot["devtools_status"] == "Found"
    assert snapshot["time"] == "1:05 / 5:15"
    assert main._tray_icon_title(snapshot) == "Rusty - Tyler, The Creator"
    assert payload["status"] == "Running"
    assert payload["title"] == "Rusty"
    assert "Album: Wolf" in payload["meta"]
    assert any(row[0] == "DevTools" and row[1] == "Found" for row in payload["diagnostics"])
    assert qt_tray_ui.DRAWER_WIDTH == 336
    assert qt_tray_ui.DRAWER_HEIGHT == 464
    assert bottom_right[2:] == (336, 464)
    assert bottom_right[0] <= 1920 - 336
    assert bottom_right[1] <= 1080 - 464
    assert top_left[0] >= 0
    assert top_left[1] >= 0
    assert {"settings", "diagnostics", "launch_amazon", "private", "game_mode", "wrong_song", "toggle_rpc", "updates", "quit"}.issubset(qt_tray_ui.TRAY_COMMANDS)
