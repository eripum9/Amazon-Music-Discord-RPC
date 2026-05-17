# MIT License - Copyright (c) 2026 eripum9
import json
import os
import tempfile
from config import DEFAULTS, CONFIG_DIR, CONFIG_PATH, load_config, redact_data, redact_text


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
        ok = (
            DEFAULTS.get("amazon_devtools_enabled") is False
            and DEFAULTS.get("amazon_devtools_auto_launch") is False
            and DEFAULTS.get("enhanced_metadata_prompt_seen") is False
            and DEFAULTS.get("notification_enrichment_enabled") is False
        )
        results.append(_result("Enhanced metadata defaults", ok, "Enhanced metadata starts opt-in for new configs"))
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
        from updater import _extract_sha256, verify_file_sha256
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
        from album_art import _clean_title
        ok = _clean_title("Song [Explicit]") == "Song"
        results.append(_result("Metadata cleanup", ok, "Explicit marker stripped"))
    except Exception as e:
        results.append(_result("Metadata cleanup", False, str(e)))

    try:
        from discord_rpc import _discord_asset_text
        ok = (
            _discord_asset_text("Z", "Off the Record") == "Album: Z"
            and _discord_asset_text("", "A") == "Track: A"
            and _discord_asset_text("Wolf", "IFHY") == "Wolf"
            and len(_discord_asset_text("Z", "Off the Record")) >= 2
        )
        results.append(_result("Discord asset text", ok, "One-letter albums are expanded for Discord validation"))
    except Exception as e:
        results.append(_result("Discord asset text", False, str(e)))

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
            zero_ts = main._track_start_ts({"position": 0}, "Fresh|Track", use_cache=False)
        ok = (
            resumed_ts == 896
            and resumed_paused is None
            and refreshed
            and fallback_ts == 900
            and fallback_paused is None
            and not fallback_refreshed
            and zero_ts == 1000
        )
        results.append(_result("Resume timing refresh", ok, "Playing after pause uses current playback position before paused fallback"))
    except Exception as e:
        results.append(_result("Resume timing refresh", False, str(e)))

    try:
        from amazon_devtools import _normalise_track_payload, apply_devtools_to_track
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
        merged, changed = apply_devtools_to_track({"title": "Treehome95", "artist": "", "album": "", "status": "playing"}, devtools)
        ok = changed and merged["artist"].startswith("Tyler") and merged["album"] == "Wolf" and merged["duration"] == 179 and merged["position"] == 138 and merged["status"] == "paused" and merged["_amazon_track_link"] == "https://music.amazon.de/albums/B00C3O5AD8?trackAsin=B00C3O5D3A"
        results.append(_result("Amazon DevTools metadata", ok, "DevTools metadata can repair artist, album, art, position, duration, status, and link"))
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
        bad_target = {
            "type": "page",
            "url": "https://example.com/morpho/webapp/index.html",
            "title": "Amazon Music",
        }
        ok = (
            DEVTOOLS_PORT_MIN <= port <= DEVTOOLS_PORT_MAX
            and port != COMMON_DEVTOOLS_PORT
            and int(env[DEVTOOLS_PORT_ENV]) == port
            and f"--remote-debugging-port={COMMON_DEVTOOLS_PORT}" not in source
            and _is_amazon_music_target(good_target)
            and not _is_amazon_music_target(bad_target)
        )
        reset_devtools_port()
        results.append(_result("Amazon DevTools port hardening", ok, "Runtime port is random and target validation rejects non-Amazon pages"))
    except Exception as e:
        results.append(_result("Amazon DevTools port hardening", False, str(e)))

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
        results.append(_result("Diagnostics cards", len(cards) == 8, f"{len(cards)} cards"))
    except Exception as e:
        results.append(_result("Diagnostics cards", False, str(e)))

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
            html.index('<div class="card-title">Custom Album Art</div>'),
            html.index('<div class="card-title">Startup & Presence</div>'),
            html.index('<div class="card-title">Fallback Metadata</div>'),
            html.index('<div class="card-title">Discord Client ID</div>'),
        ]
        ok = (
            "What\\\\'s new" not in script
            and "\\n\\nWhat's new:\\n" in script
            and "async function init()" in script
            and "renderCustomAlbums" in script
            and "custom_albums" in script
            and "song_link_provider" in script
            and "songLinkProvider" in script
            and "Show listen button" in html
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
