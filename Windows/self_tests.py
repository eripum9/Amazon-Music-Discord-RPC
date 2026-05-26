# MIT License - Copyright (c) 2026 eripum9
import json
import os
import tempfile
import zipfile
from config import DEFAULTS, CONFIG_DIR, CONFIG_PATH, load_config, load_config_for_update, normalize_amazon_music_link_region, redact_data, redact_text


def _result(name, ok, detail):
    return {
        "name": name,
        "status": "pass" if ok else "fail",
        "detail": detail,
    }


def run_self_tests(log_dir, diagnostics_path):
    results = []

    try:
        config = load_config()
        missing = [key for key in DEFAULTS if key not in config]
        results.append(_result("Config defaults", not missing, "All defaults loaded" if not missing else f"Missing: {', '.join(missing)}"))
    except Exception as e:
        results.append(_result("Config defaults", False, str(e)))

    try:
        import config as config_module
        import settings_ui
        old_dir = config_module.CONFIG_DIR
        old_path = config_module.CONFIG_PATH
        with tempfile.TemporaryDirectory(prefix="amrpc_config_guard_", dir=CONFIG_DIR) as temp_dir:
            config_module.CONFIG_DIR = temp_dir
            config_module.CONFIG_PATH = os.path.join(temp_dir, "config.json")
            with open(config_module.CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write("")
            strict_failed = False
            try:
                load_config_for_update()
            except json.JSONDecodeError:
                strict_failed = True
            settings_ui._save_window_size(420, 560)
            with open(config_module.CONFIG_PATH, "r", encoding="utf-8") as f:
                preserved = f.read() == ""
            fallback = load_config()
            payload_rejected = False
            try:
                settings_ui._Api(None, lambda: None).save_settings({})
            except ValueError:
                payload_rejected = True
        config_module.CONFIG_DIR = old_dir
        config_module.CONFIG_PATH = old_path
        ok = strict_failed and preserved and payload_rejected and all(key in fallback for key in DEFAULTS)
        results.append(_result("Config update guard", ok, "Unsafe config reads and incomplete settings payloads do not get saved over"))
    except Exception as e:
        try:
            config_module.CONFIG_DIR = old_dir
            config_module.CONFIG_PATH = old_path
        except Exception:
            pass
        results.append(_result("Config update guard", False, str(e)))

    try:
        ok = (
            DEFAULTS.get("amazon_devtools_enabled") is False
            and DEFAULTS.get("amazon_devtools_auto_launch") is False
            and DEFAULTS.get("enhanced_metadata_prompt_seen") is False
            and DEFAULTS.get("notification_enrichment_enabled") is False
            and DEFAULTS.get("amazon_music_link_region") == "com"
            and normalize_amazon_music_link_region("de") == "de"
            and normalize_amazon_music_link_region(".com") == "com"
            and normalize_amazon_music_link_region("bad") == "com"
        )
        results.append(_result("Enhanced metadata defaults", ok, "Enhanced metadata starts opt-in and Amazon links default to .com"))
    except Exception as e:
        results.append(_result("Enhanced metadata defaults", False, str(e)))

    try:
        secrets = {
            "listenbrainz_token": "listenbrainz_secret_value",
            "lastfm_session_key": "lastfm_secret_value",
            "lastfm_api_secret": "lastfm_app_secret_value",
        }
        text = 'Token listenbrainz_secret_value "lastfm_session_key": "lastfm_secret_value" lastfm_app_secret_value'
        redacted_text = redact_text(text, secrets)
        redacted_data = redact_data({"listenbrainz_token": secrets["listenbrainz_token"], "nested": {"value": secrets["lastfm_session_key"]}}, secrets)
        combined = redacted_text + json.dumps(redacted_data)
        ok = all(secret not in combined for secret in secrets.values()) and "[redacted]" in combined
        results.append(_result("Secret redaction", ok, "Tokens are redacted from text and diagnostics data"))
    except Exception as e:
        results.append(_result("Secret redaction", False, str(e)))

    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        fd, path = tempfile.mkstemp(prefix="amrpc_test_", suffix=".tmp", dir=CONFIG_DIR)
        os.close(fd)
        os.remove(path)
        results.append(_result("Config directory write", True, CONFIG_DIR))
    except Exception as e:
        results.append(_result("Config directory write", False, str(e)))

    try:
        os.makedirs(log_dir, exist_ok=True)
        fd, path = tempfile.mkstemp(prefix="amrpc_log_test_", suffix=".tmp", dir=log_dir)
        os.close(fd)
        os.remove(path)
        results.append(_result("Log directory write", True, log_dir))
    except Exception as e:
        results.append(_result("Log directory write", False, str(e)))

    try:
        if os.path.exists(diagnostics_path):
            with open(diagnostics_path, "r", encoding="utf-8") as f:
                json.load(f)
            detail = diagnostics_path
        else:
            detail = "Diagnostics state has not been written yet"
        results.append(_result("Diagnostics state", True, detail))
    except Exception as e:
        results.append(_result("Diagnostics state", False, str(e)))

    try:
        from updater import _parse_version
        ok = _parse_version("v2.1.0") == (2, 1, 0)
        results.append(_result("Version parsing", ok, "v2.1.0"))
    except Exception as e:
        results.append(_result("Version parsing", False, str(e)))

    try:
        from updater import _format_changelog
        body = "Intro paragraph\n\n## What's New\n\n### New Features\n\n- Added diagnostics\n- Fixed privacy\n\n## Installation\n\nDownload the installer."
        formatted = _format_changelog(body)
        ok = "Added diagnostics" in formatted and "Fixed privacy" in formatted and "Intro paragraph" not in formatted and "Download the installer" not in formatted
        results.append(_result("Update changelog", ok, formatted or "No changelog"))
    except Exception as e:
        results.append(_result("Update changelog", False, str(e)))

    try:
        import hashlib
        import inspect
        from updater import _extract_sha256, verify_file_sha256, prompt_for_update, launch_installer
        fd, path = tempfile.mkstemp(prefix="amrpc_hash_", suffix=".bin", dir=log_dir)
        with os.fdopen(fd, "wb") as f:
            f.write(b"amazon music rpc installer test")
        digest = hashlib.sha256(b"amazon music rpc installer test").hexdigest()
        body = f"## Release\n\nAmazonMusicRPC_Setup.exe SHA256: {digest}\nother.exe SHA256: {'0' * 64}"
        extracted = _extract_sha256(body, "AmazonMusicRPC_Setup.exe")
        verified = verify_file_sha256(path, digest) == digest
        os.remove(path)
        ok = extracted == digest and verified
        results.append(_result("Updater SHA256 trust", ok, "Release hashes can be parsed and verified"))
    except Exception as e:
        results.append(_result("Updater SHA256 trust", False, str(e)))

    try:
        import inspect
        from updater import _ps_literal, prompt_for_update, launch_installer
        prompt_source = inspect.getsource(prompt_for_update)
        launch_source = inspect.getsource(launch_installer)
        ok = (
            _ps_literal("a'b") == "'a''b'"
            and "defer_until_exit" in prompt_source
            and "launch_installer" in prompt_source
            and "Get-Process -Id $pidToWait" in launch_source
            and "Start-Process -FilePath $installer" in launch_source
        )
        results.append(_result("Updater installer handoff", ok, "Auto-updates can defer installer launch until the app exits"))
    except Exception as e:
        results.append(_result("Updater installer handoff", False, str(e)))

    try:
        installer_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "installer.iss")
        with open(installer_path, "r", encoding="utf-8") as f:
            installer_script = f.read()
        ok = (
            "CloseApplications=no" in installer_script
            and "RestartApplications=no" in installer_script
            and "BeforeInstall: KillRunningApp" in installer_script
            and '/F /T /IM "{#MyAppExeName}"' in installer_script
            and 'WorkingDir: "{app}"' in installer_script
        )
        results.append(_result("Installer running-app guard", ok, "Installer stops the running app before replacing files and launches from the install directory"))
    except Exception as e:
        results.append(_result("Installer running-app guard", False, str(e)))

    try:
        from album_art import _clean_title
        ok = _clean_title("Song [Explicit]") == "Song"
        results.append(_result("Metadata cleanup", ok, "Explicit marker stripped"))
    except Exception as e:
        results.append(_result("Metadata cleanup", False, str(e)))

    try:
        import discord_rpc
        from discord_rpc import _discord_asset_text, _button_signature, DiscordRPC
        class FakePresence:
            def __init__(self):
                self.calls = []

            def update(self, payload_override=None):
                self.calls.append(("update", payload_override))
                return {"ok": True}

            def clear(self):
                self.calls.append(("clear", None))

        original_sleep = discord_rpc.time.sleep
        discord_rpc.time.sleep = lambda _: None
        fake = FakePresence()
        try:
            rpc = DiscordRPC.__new__(DiscordRPC)
            rpc.client_id = "client"
            rpc.rpc = fake
            rpc.connected = True
            rpc._last_track_key = None
            rpc._last_button_signature = None
            rpc._backoff = 3
            rpc._next_retry = 0
            rpc.update("Song A", "Artist", buttons=[{"label": "Listen on Amazon Music", "url": "https://music.amazon.com/tracks/a"}])
            rpc.update("Song B", "Artist", buttons=[{"label": "Listen on Amazon Music", "url": "https://music.amazon.com/tracks/b"}])
            rpc.update("Song C", "Artist")
        finally:
            discord_rpc.time.sleep = original_sleep
        call_order = [call[0] for call in fake.calls]
        last_payload = fake.calls[-1][1]["args"]["activity"]
        ok = (
            _discord_asset_text("Z", "Off the Record") == "Album: Z"
            and _discord_asset_text("", "A") == "Track: A"
            and _discord_asset_text("Wolf", "IFHY") == "Wolf"
            and len(_discord_asset_text("Z", "Off the Record")) >= 2
            and _button_signature([{"label": "A", "url": "1"}]) != _button_signature([{"label": "A", "url": "2"}])
            and call_order == ["update", "clear", "update", "clear", "update"]
            and last_payload.get("buttons") == []
        )
        results.append(_result("Discord presence payload", ok, "One-letter asset text and button URL refresh behavior are guarded"))
    except Exception as e:
        results.append(_result("Discord presence payload", False, str(e)))

    try:
        import main
        configured = main._configured_game_mode_processes({"game_mode_processes": "Game.exe, C:\\Tools\\OtherGame.exe\nNoExt"})
        ok = (
            configured == {"game.exe", "othergame.exe", "noext"}
            and main._game_mode_matches_processes(configured, {"game.exe"})
            and main._game_mode_matches_processes({"noext"}, {"NoExt.exe"})
            and main._should_prompt_wrong_song("Song|Song", "Song", "Song", {"game_mode_enabled": False, "game_mode_processes": ""})
            and not main._should_prompt_wrong_song("Song|Song", "Song", "Song", {"game_mode_enabled": True, "game_mode_processes": ""})
            and not main._should_prompt_wrong_song("Song|Artist", "Song", "Artist", {"game_mode_enabled": False, "game_mode_processes": ""})
        )
        main._game_mode_suppressed_keys.discard("Song|Song")
        results.append(_result("Game Mode picker suppression", ok, "Manual and process Game Mode can suppress automatic wrong-song prompts"))
    except Exception as e:
        results.append(_result("Game Mode picker suppression", False, str(e)))

    try:
        import inspect
        import main
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
            snapshot = main._tray_menu_snapshot({
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
            })
            main_source = inspect.getsource(main)
            ok = (
                snapshot.get("rpc") == "On"
                and snapshot.get("discord") == "Connected"
                and snapshot.get("source") == "Amazon Metadata"
                and snapshot.get("devtools_status") == "Found"
                and snapshot.get("time") == "1:05 / 5:15"
                and main._tray_icon_title(snapshot) == "Rusty - Tyler, The Creator"
                and "QtTrayController" in main_source
                and "--tray-popup-host" not in main_source
                and "_install_custom_tray_click" not in main_source
                and "pystray._win32" not in main_source
            )
        finally:
            main.rpc_running = old_running
            main.current_config = old_config
        results.append(_result("Qt tray state", ok, "Tray state exposes live RPC, source, track, link, and timing state"))
    except Exception as e:
        results.append(_result("Qt tray state", False, str(e)))

    try:
        import inspect
        import qt_tray_ui
        snapshot = {
            "rpc": "On",
            "discord": "Connected",
            "presence": "Visible",
            "source": "Amazon Metadata",
            "source_detail": "Noid",
            "title": "Noid",
            "artist": "Tyler, The Creator",
            "album": "Chromakopia",
            "time": "1:01 / 4:35",
            "private": False,
            "devtools_status": "Found",
            "game_mode": "Off",
        }
        payload = qt_tray_ui.drawer_payload(snapshot)
        bottom_right = qt_tray_ui.drawer_geometry(10_000, 10_000, (0, 0, 1920, 1080))
        top_left = qt_tray_ui.drawer_geometry(0, 0, (0, 0, 320, 500))
        source = inspect.getsource(qt_tray_ui)
        ok = (
            payload.get("status") == "Running"
            and payload.get("title") == "Noid"
            and "Album: Chromakopia" in payload.get("meta")
            and any(row[0] == "DevTools" and row[1] == "Found" for row in payload.get("diagnostics", []))
            and qt_tray_ui.DRAWER_WIDTH == 336
            and qt_tray_ui.DRAWER_HEIGHT == 464
            and bottom_right[2:] == (336, 464)
            and bottom_right[0] <= 1920 - 336
            and bottom_right[1] <= 1080 - 464
            and top_left[0] >= 0
            and top_left[1] >= 0
            and "setFixedSize(DRAWER_WIDTH, DRAWER_HEIGHT)" in source
            and "QSystemTrayIcon" in source
            and "QWidgetAction" in source
            and "setContextMenu" in source
            and "WindowDeactivate" not in source
            and {"settings", "diagnostics", "launch_amazon", "private", "game_mode", "wrong_song", "toggle_rpc", "updates", "quit"}.issubset(qt_tray_ui.TRAY_COMMANDS)
        )
        results.append(_result("Qt tray drawer", ok, "Qt tray drawer payload, commands, and geometry are stable"))
    except Exception as e:
        results.append(_result("Qt tray drawer", False, str(e)))

    try:
        import inspect
        from album_art import search_tracks
        params = inspect.signature(search_tracks).parameters
        ok = "offset" in params
        results.append(_result("Paged search", ok, "search_tracks accepts offset"))
    except Exception as e:
        results.append(_result("Paged search", False, str(e)))

    try:
        from album_art import find_custom_album_art
        custom = find_custom_album_art(
            {
                "custom_albums": [
                    {
                        "album": "Correct Album",
                        "aliases": ["Wrong Album", "Alt Album"],
                        "art_url": "https://example.com/cover.jpg",
                    }
                ]
            },
            "wrong album",
        )
        ok = bool(custom) and custom["album"] == "Correct Album" and custom["art_url"].endswith("cover.jpg")
        results.append(_result("Custom album art", ok, "Album aliases match custom artwork"))
    except Exception as e:
        results.append(_result("Custom album art", False, str(e)))

    try:
        import main
        main._resolved_cache["raw title|raw artist"] = ("Fixed Title", "Fixed Artist")
        title, artist, applied = main._apply_resolved_cache("raw title|raw artist", "raw title", "raw artist")
        main._resolved_cache.pop("raw title|raw artist", None)
        ok = applied and title == "Fixed Title" and artist == "Fixed Artist" and main._same_track_field("Same Name", " same   name ")
        results.append(_result("Track correction cache", ok, "Resolved corrections apply to full metadata tracks"))
    except Exception as e:
        results.append(_result("Track correction cache", False, str(e)))

    try:
        import main
        from unittest.mock import patch
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
                {"position": 70.5},
                "Song|Artist",
                930,
                None,
                False,
            )
            zero_ts = main._track_start_ts({"position": 0}, "Fresh|Track", use_cache=False)
        ok = (
            resumed_ts == 896
            and resumed_paused is None
            and refreshed
            and fallback_ts == 900
            and fallback_paused is None
            and not fallback_refreshed
            and seek_forward_ts == 910
            and seek_forward_paused is None
            and seek_forward_refreshed
            and seek_back_ts == 960
            and seek_back_paused is None
            and seek_back_refreshed
            and stable_ts == 930
            and stable_paused is None
            and not stable_refreshed
            and zero_ts == 1000
        )
        results.append(_result("Playback timing refresh", ok, "Playing after pause and timebar seek changes refresh Discord timer"))
    except Exception as e:
        results.append(_result("Playback timing refresh", False, str(e)))

    try:
        from amazon_devtools import _normalise_track_payload, apply_devtools_to_track, amazon_music_search_link
        devtools = _normalise_track_payload({
            "status": "found",
            "title": "Treehome95 [Explicit]",
            "secondary": "Tyler, The Creator feat. Coco O. & Erykah Badu \u2022 Wolf [Explicit]",
            "art_url": "https://m.media-amazon.com/images/I/41SsO6U8VML.jpg",
            "position_text": "02:18",
            "remaining_text": "-00:41",
            "playback_status": "paused",
            "track_asin": "B00C3O5D3A",
            "album_asin": "B00C3O5AD8",
            "music_host": "music.amazon.de",
        })
        devtools_de = _normalise_track_payload({
            "status": "found",
            "title": "Treehome95",
            "artist": "Tyler, The Creator",
            "track_asin": "B00C3O5D3A",
            "album_asin": "B00C3O5AD8",
            "music_host": "music.amazon.de",
        }, "de")
        stale_direct = _normalise_track_payload({
            "status": "found",
            "title": "Current Song",
            "artist": "Current Artist",
            "track_link": "https://music.amazon.de/tracks/OLDTRACK",
            "music_host": "music.amazon.de",
        })
        merged, changed = apply_devtools_to_track({"title": "Treehome95", "artist": "", "album": "", "status": "playing"}, devtools)
        ok = changed and merged["artist"].startswith("Tyler") and merged["album"] == "Wolf" and merged["duration"] == 179 and merged["position"] == 138 and merged["status"] == "paused" and merged["_amazon_track_link"] == "https://music.amazon.com/tracks/B00C3O5D3A" and devtools_de.get("track_link") == "https://music.amazon.de/tracks/B00C3O5D3A" and stale_direct.get("track_link") == "https://music.amazon.com/search/Current%20Song%20Current%20Artist" and amazon_music_search_link("Noid", "Tyler, The Creator", "de") == "https://music.amazon.de/search/Noid%20Tyler%2C%20The%20Creator"
        results.append(_result("Amazon DevTools metadata", ok, "DevTools metadata can repair artist, album, art, position, duration, status, and configurable region link"))
    except Exception as e:
        results.append(_result("Amazon DevTools metadata", False, str(e)))

    try:
        from amazon_devtools import _normalise_track_payload
        devtools = _normalise_track_payload({
            "status": "found",
            "title": "Song",
            "secondary": "Artist Only",
        })
        ok = devtools.get("status") == "found" and devtools.get("artist") == "Artist Only" and devtools.get("album") == ""
        results.append(_result("Amazon DevTools secondary fallback", ok, "Single secondary label is treated as artist"))
    except Exception as e:
        results.append(_result("Amazon DevTools secondary fallback", False, str(e)))

    try:
        from amazon_devtools import _TRANSPORT_EXPRESSION, _normalise_track_payload
        from discord_rpc import _discord_asset_text
        explicit = _normalise_track_payload({
            "status": "found",
            "title": "A [Explicit]",
            "artist": "Artist",
            "album": "Z [Explicit]",
            "playback_status": "paused",
            "position_text": "00:07",
            "remaining_text": "-00:53",
        })
        missing_art = _normalise_track_payload({
            "status": "found",
            "title": "Bare Song",
            "secondary": "Bare Artist",
            "art_url": "",
            "playback_status": "stopped",
        })
        incomplete = _normalise_track_payload({
            "status": "found",
            "title": "No Artist",
            "album": "Album",
        })
        sample_html = """
<div id="transportContainer" class="hasTrackLoaded">
  <div class="trackMetadataWrapper">
    <div class="albumArt"><img class="artImage" src="https://example.com/cover.jpg"></div>
    <div class="primaryContainer"><a href="https://music.amazon.com/tracks/B012345678">A [Explicit]</a></div>
    <div class="secondaryText">Artist • Z [Explicit]</div>
    <span class="secondaryInnerText">Artist</span>
    <span class="secondaryInnerText">Z [Explicit]</span>
  </div>
  <span class="currentPlaybackPosition">00:07</span>
  <span class="currentRemainingPosition">-00:53</span>
  <button class="playPause"><svg><use href="#pause"></use></svg></button>
</div>
"""
        selectors = [
            ".trackMetadataWrapper .primaryContainer",
            ".trackMetadataWrapper .secondaryText",
            ".trackMetadataWrapper .secondaryInnerText",
            ".trackMetadataWrapper .albumArt img.artImage",
            ".currentPlaybackPosition",
            ".currentRemainingPosition",
            "button.playPause",
        ]
        ok = (
            explicit.get("title") == "A"
            and explicit.get("album") == "Z"
            and explicit.get("duration") == 60
            and explicit.get("playback_status") == "paused"
            and _discord_asset_text(explicit.get("album"), explicit.get("title")) == "Album: Z"
            and missing_art.get("status") == "found"
            and missing_art.get("artist") == "Bare Artist"
            and missing_art.get("art_url") == ""
            and missing_art.get("playback_status") == "playing"
            and incomplete.get("status") == "no_match"
            and all(fragment in sample_html for fragment in ("trackMetadataWrapper", "secondaryInnerText", "artImage", "currentPlaybackPosition", "currentRemainingPosition", "playPause"))
            and all(selector in _TRANSPORT_EXPRESSION for selector in selectors)
        )
        results.append(_result("Amazon DevTools fragile payloads", ok, "Sample DOM shape, selectors, explicit cleanup, pause state, missing art, and one-letter album cases are covered"))
    except Exception as e:
        results.append(_result("Amazon DevTools fragile payloads", False, str(e)))

    try:
        import inspect
        from amazon_devtools import (
            COMMON_DEVTOOLS_PORT,
            DEVTOOLS_PORT_ENV,
            DEVTOOLS_PORT_MAX,
            DEVTOOLS_PORT_MIN,
            _is_amazon_music_target,
            devtools_environment,
            get_devtools_port,
            launch_amazon_music_devtools,
            reset_devtools_port,
        )
        reset_devtools_port()
        port = get_devtools_port()
        env = devtools_environment({})
        source = inspect.getsource(launch_amazon_music_devtools)
        good_target = {
            "type": "page",
            "url": "https://music.amazon.de/morpho/webapp/index.html",
            "title": "Amazon Music",
        }
        regional_target = {
            "type": "page",
            "url": "https://www.amazon.de/morpho/webapp/index.html#/home",
            "title": "Amazon Music Desktop",
        }
        bad_target = {
            "type": "page",
            "url": "https://example.com/morpho/webapp/index.html",
            "title": "Amazon Music",
        }
        bad_amazon_target = {
            "type": "page",
            "url": "https://www.amazon.de/",
            "title": "Amazon Music Desktop",
        }
        ok = (
            DEVTOOLS_PORT_MIN <= port <= DEVTOOLS_PORT_MAX
            and port != COMMON_DEVTOOLS_PORT
            and int(env[DEVTOOLS_PORT_ENV]) == port
            and f"--remote-debugging-port={COMMON_DEVTOOLS_PORT}" not in source
            and _is_amazon_music_target(good_target)
            and _is_amazon_music_target(regional_target)
            and not _is_amazon_music_target(bad_target)
            and not _is_amazon_music_target(bad_amazon_target)
        )
        reset_devtools_port()
        results.append(_result("Amazon DevTools port hardening", ok, "Runtime port is random and target validation rejects non-Amazon pages"))
    except Exception as e:
        results.append(_result("Amazon DevTools port hardening", False, str(e)))

    try:
        import inspect
        from amazon_devtools import (
            APP_USER_MODEL_ID,
            LAUNCH_FAILURE_HELP,
            _appx_aumid_candidates,
            _attempt_failure,
            _build_aumid,
            _launcher_candidates,
            _launch_aumid,
            _launch_exe,
            _start_app_candidates,
            amazon_music_launcher_candidates,
        )
        existing_path = r"C:\Amazon Music\Amazon Music.exe"
        exists = lambda path: path == existing_path
        start_apps = [
            {"Name": "Amazon Music", "AppID": "Website.Package!AmazonMusic"},
            {"Name": "Amazon Music", "AppID": existing_path},
            {"Name": "Amazon Music", "AppID": r"C:\Missing\Amazon Music.exe"},
            {"Name": "Amazon Music RPC", "AppID": r"C:\Amazon Music RPC\AmazonMusicRPC.exe"},
        ]
        appx_apps = [
            {"PackageFamilyName": "AmazonMobileLLC.AmazonMusic_alt", "AppId": "AmazonMusic"},
        ]
        candidates = _launcher_candidates("Override.Package!App", start_apps, appx_apps, exists)
        methods = [candidate.get("method") for candidate in candidates]
        values = [candidate.get("value") for candidate in candidates]
        missing_path_candidates = _start_app_candidates([{"Name": "Amazon Music", "AppID": r"C:\Missing\Amazon Music.exe"}], lambda path: False)
        package_failure = _attempt_failure({"method": "auto-aumid", "value": "Missing.Package!App"}, 'Package was not found. 0x80073CF1')
        ok = (
            _build_aumid("PackageFamily", "App") == "PackageFamily!App"
            and values[:4] == ["Override.Package!App", "Website.Package!AmazonMusic", existing_path, "AmazonMobileLLC.AmazonMusic_alt!AmazonMusic"]
            and methods[:4] == ["override-aumid", "auto-aumid", "auto-exe", "auto-aumid"]
            and candidates[-1].get("method") == "hardcoded-store"
            and candidates[-1].get("value") == APP_USER_MODEL_ID
            and isinstance(amazon_music_launcher_candidates("Override.Package!App"), list)
            and not missing_path_candidates
            and "package was not found" in package_failure.lower()
            and LAUNCH_FAILURE_HELP.startswith("Could not launch Amazon Music")
            and "--remote-debugging-port={port}" in inspect.getsource(_launch_aumid)
            and "--remote-debugging-port={port}" in inspect.getsource(_launch_exe)
        )
        results.append(_result("Amazon DevTools launcher discovery", ok, "Launcher candidates cover override, Start Apps, Appx, executable paths, and Store fallback"))
    except Exception as e:
        results.append(_result("Amazon DevTools launcher discovery", False, str(e)))

    try:
        import main
        unavailable = {"enabled": True, "status": "unavailable", "detail": "DevTools unavailable"}
        error = {"enabled": True, "status": "error", "detail": "Socket failed"}
        launching = {"enabled": True, "status": "launching", "detail": "Starting Amazon Music"}
        restarting = {"enabled": True, "status": "restarting", "detail": "Restarting Amazon Music"}
        waiting = main._devtools_no_track_state(True, {"enabled": True, "status": "no_match", "detail": "No title"})
        ok = (
            main._devtools_no_track_state(True, unavailable) == unavailable
            and main._devtools_no_track_state(True, error) == error
            and main._devtools_no_track_state(True, launching) == launching
            and main._devtools_no_track_state(True, restarting) == restarting
            and waiting.get("status") == "waiting"
        )
        results.append(_result("Amazon DevTools diagnostics state", ok, "Unavailable, launch, restart, and error states are preserved without a track"))
    except Exception as e:
        results.append(_result("Amazon DevTools diagnostics state", False, str(e)))

    try:
        from amazon_devtools import amazon_devtools_launcher_state, _shortcut_launcher_command, amazon_music_is_running
        state = amazon_devtools_launcher_state()
        target, arguments, working_dir, icon_path = _shortcut_launcher_command()
        ok = state.get("path", "").endswith("Amazon Music Metadata.lnk") and target and "--launch-amazon-devtools" in arguments and working_dir and icon_path and isinstance(amazon_music_is_running(), bool)
        results.append(_result("Amazon DevTools launcher", ok, "Launcher command and cleanup path are available"))
    except Exception as e:
        results.append(_result("Amazon DevTools launcher", False, str(e)))

    try:
        from amazon_status_overlay import AmazonStatusOverlay, OVERLAY_VERSION, build_overlay_payload
        private = build_overlay_payload(
            {"privacy_private_session": True},
            {"discord_status": "connected", "amazon_devtools": {"status": "found"}},
            True,
        )
        paused = build_overlay_payload(
            {"privacy_private_session": False},
            {"discord_status": "connected", "track": {"status": "paused"}, "amazon_devtools": {"status": "found"}},
            True,
        )
        overlay = AmazonStatusOverlay(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png"),
            lambda: {},
            lambda: {},
            lambda: True,
            lambda enabled: None,
        )
        overlay.bridge_url = "https://localhost:17680"
        script = overlay._script()
        ok = (
            private.get("statusLabel") == "Private"
            and private.get("privacy") is True
            and paused.get("statusLabel") == "Paused"
            and any(row.get("label") == "Source" and row.get("value") == "DevTools DOM" for row in paused.get("diagnostics", []))
            and OVERLAY_VERSION in script
            and "privacyBusy" in script
            and "data-busy" in script
            and "amrpc-toggle-track" in script
        )
        results.append(_result("Amazon status overlay", ok, "Overlay payload and injected privacy control are guarded"))
    except Exception as e:
        results.append(_result("Amazon status overlay", False, str(e)))

    try:
        import diagnostics_ui
        cards = diagnostics_ui._build_cards({}, load_config(), {"value": "Unavailable", "state": "bad"})
        ok = len(cards) == 9 and any(card.get("label") == "Source" for card in cards)
        results.append(_result("Diagnostics cards", ok, f"{len(cards)} cards"))
    except Exception as e:
        results.append(_result("Diagnostics cards", False, str(e)))

    try:
        from status_summary import metadata_source_summary
        private = metadata_source_summary({"privacy": {"hidden": True, "reason": "Keyword filter"}}, {})
        amazon = metadata_source_summary({"track": {"status": "playing", "title": "Song"}, "amazon_devtools": {"status": "found", "title": "Song"}}, {"amazon_devtools_enabled": True})
        paused = metadata_source_summary({"track": {"status": "paused", "title": "Song"}}, {})
        notify = metadata_source_summary({"track": {"status": "playing", "title": "Song"}, "notification": {"title": "Song"}}, {"notification_enrichment_enabled": True})
        smtc = metadata_source_summary({"track": {"status": "playing", "title": "Song"}}, {})
        ok = (
            private.get("label") == "Private"
            and amazon.get("label") == "Amazon Metadata"
            and paused.get("label") == "Paused"
            and notify.get("label") == "Notification Fallback"
            and smtc.get("label") == "SMTC Fallback"
        )
        results.append(_result("Metadata source summary", ok, "Source labels cover privacy, Amazon, notification, SMTC, and pause states"))
    except Exception as e:
        results.append(_result("Metadata source summary", False, str(e)))

    try:
        import diagnostics_ui
        logs = diagnostics_ui._log_files()
        ok = bool(logs) and all("label" in item and "path" in item for item in logs)
        results.append(_result("Diagnostics log history", ok, f"{len(logs)} log entries"))
    except Exception as e:
        results.append(_result("Diagnostics log history", False, str(e)))

    try:
        import diagnostics_ui
        api = diagnostics_ui._Api(lambda: None)
        snapshot = api.get_snapshot()
        ok = "cards" in snapshot and "log_files" in snapshot and "config_path" in snapshot
        results.append(_result("Diagnostics snapshot", ok, "Snapshot API returned expected fields"))
    except Exception as e:
        results.append(_result("Diagnostics snapshot", False, str(e)))

    try:
        import diagnostics_ui
        import inspect
        fd, report_path = tempfile.mkstemp(prefix="amrpc_diag_report_", suffix=".zip", dir=CONFIG_DIR)
        os.close(fd)
        diagnostics_ui._write_diagnostics_report(report_path, include_tests=False)
        with zipfile.ZipFile(report_path, "r") as archive:
            names = set(archive.namelist())
            report = json.loads(archive.read("report.json").decode("utf-8"))
        os.remove(report_path)
        ok = (
            {"report.json", "config.redacted.json", "diagnostics.redacted.json"}.issubset(names)
            and "source_summary" in report
            and "create_file_dialog" not in inspect.getsource(diagnostics_ui._Api.export_diagnostics_report)
        )
        results.append(_result("Diagnostics export", ok, "Diagnostics ZIP includes redacted state, config, logs, source, and launcher data"))
    except Exception as e:
        results.append(_result("Diagnostics export", False, str(e)))

    try:
        import settings_ui
        import inspect
        existing = {**DEFAULTS, "listenbrainz_token": "old-token", "lastfm_session_key": "old-session"}
        exported = settings_ui._settings_export_payload({**existing, "listenbrainz_token": "secret-token"}, False)
        exported_with_tokens = settings_ui._settings_export_payload({**existing, "listenbrainz_token": "secret-token"}, True)
        imported = settings_ui._settings_import_config(
            {"include_tokens": False, "config": {"listenbrainz_token": "new-token", "start_minimized": False, "amazon_music_link_region": "de"}},
            existing,
        )
        imported_with_tokens = settings_ui._settings_import_config(
            {"include_tokens": True, "config": {"listenbrainz_token": "new-token"}},
            existing,
        )
        ok = (
            "listenbrainz_token" not in exported.get("config", {})
            and exported_with_tokens.get("config", {}).get("listenbrainz_token") == "secret-token"
            and imported.get("listenbrainz_token") == "old-token"
            and imported.get("start_minimized") is False
            and imported.get("amazon_music_link_region") == "de"
            and imported_with_tokens.get("listenbrainz_token") == "new-token"
            and "create_file_dialog" not in inspect.getsource(settings_ui._Api.export_settings)
            and "create_file_dialog" not in inspect.getsource(settings_ui._Api.import_settings)
        )
        results.append(_result("Settings backup restore", ok, "Settings export redacts tokens unless requested and import preserves tokens by default"))
    except Exception as e:
        results.append(_result("Settings backup restore", False, str(e)))

    try:
        from windows_file_dialog import _ps_literal
        ok = _ps_literal("a'b") == "'a''b'"
        results.append(_result("Windows file dialogs", ok, "External file picker quoting is available"))
    except Exception as e:
        results.append(_result("Windows file dialogs", False, str(e)))

    try:
        import settings_ui
        html = (
            settings_ui.HTML_TEMPLATE
            .replace("{icon_b64}", "")
            .replace("{version}", "0.0.0")
            .replace("{config_json}", json.dumps(settings_ui._settings_payload()))
        )
        script = html[html.index("<script>") + len("<script>"):html.index("</script>")]
        card_order = [
            html.index('<div class="card-title">Amazon Metadata</div>'),
            html.index('<div class="card-title">Song Link</div>'),
            html.index('<div class="card-title">Privacy</div>'),
            html.index('<div class="card-title">Game Mode</div>'),
            html.index('<div class="card-title">Custom Album Art</div>'),
            html.index('<div class="card-title">Startup & Presence</div>'),
            html.index('<div class="card-title">Fallback Metadata</div>'),
            html.index('<div class="card-title">Discord Client ID</div>'),
            html.index('<div class="card-title">Settings Backup</div>'),
        ]
        ok = (
            "What\\\\'s new" not in script
            and "\\n\\nWhat's new:\\n" in script
            and "async function init()" in script
            and "renderCustomAlbums" in script
            and "custom_albums" in script
            and "song_link_provider" in script
            and "songLinkProvider" in script
            and "amazon_music_link_region" in script
            and "amazonMusicLinkRegion" in script
            and "Amazon Music region" in html
            and "onSongLinkProviderChange" in script
            and "Show listen button" in html
            and "amazon_music_launcher_override" in script
            and "amazonLauncherOverride" in script
            and "Advanced Amazon Music launcher" in html
            and "Choose Launcher" in html
            and "loadLauncherCandidates" in script
            and "testLauncherOverride" in script
            and "game_mode_enabled" in script
            and "gameModeEnabled" in script
            and "game_mode_processes" in script
            and "gameModeProcesses" in script
            and "Suppress automatic wrong-song picker popups" in html
            and "Auto-restart Amazon Music" in html
            and "Reads Windows notifications locally" in html
            and "Only Amazon Music notification text is used" in html
            and card_order == sorted(card_order)
            and "metadataWarning" in html
            and "enhancedMetadataPrompt" in html
            and "Enhanced metadata is recommended" in script
            and "Your current setup already uses enhanced Amazon metadata" in script
            and "set_enhanced_metadata_prompt" in script
            and "listenbrainz_token_present" in script
            and "Token saved. Paste a new token to replace it." in script
            and "clearScrobblingTokens" in script
            and "clear_scrobbling_tokens" in script
            and "Settings Backup" in html
            and "exportSettings" in script
            and "importSettings" in script
            and "sourceStrip" in html
            and "renderSourceSummary" in script
            and "renderWizard" in script
            and "wizardNext" in script
            and "wizardBack" in script
            and "closeMetadataWarning" in script
            and "acceptMetadataWarning" in script
            and "window.confirm" not in script
            and "amazon_devtools_enabled" in script
            and "amazon_devtools_auto_launch" in script
            and "launchAmazonDevtools" in script
            and "toggleAmazonLauncher" in script
            and "onAmazonMetadataToggle" in script
            and "collectSettingsData" in script
            and "queueAutoSave" in script
            and "syncExternalConfig" in script
            and "not recommended" in html
            and "beta metadata" not in html.lower()
        )
        results.append(_result("Settings script", ok, "Settings JavaScript guard"))
    except Exception as e:
        results.append(_result("Settings script", False, str(e)))

    return results
