# MIT License - Copyright (c) 2026 eripum9
import json
import os
import tempfile
from config import DEFAULTS, CONFIG_DIR, CONFIG_PATH, load_config


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
        from album_art import _clean_title
        ok = _clean_title("Song [Explicit]") == "Song"
        results.append(_result("Metadata cleanup", ok, "Explicit marker stripped"))
    except Exception as e:
        results.append(_result("Metadata cleanup", False, str(e)))

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
        from amazon_devtools import _normalise_track_payload, apply_devtools_to_track
        devtools = _normalise_track_payload({
            "status": "found",
            "title": "Treehome95 [Explicit]",
            "secondary": "Tyler, The Creator feat. Coco O. & Erykah Badu \u2022 Wolf [Explicit]",
            "art_url": "https://m.media-amazon.com/images/I/41SsO6U8VML.jpg",
            "position_text": "02:18",
            "remaining_text": "-00:41",
        })
        merged, changed = apply_devtools_to_track({"title": "Treehome95", "artist": "", "album": "", "status": "playing"}, devtools)
        ok = changed and merged["artist"].startswith("Tyler") and merged["album"] == "Wolf" and merged["duration"] == 179
        results.append(_result("Amazon DevTools metadata", ok, "DevTools metadata can repair artist, album, art, and duration"))
    except Exception as e:
        results.append(_result("Amazon DevTools metadata", False, str(e)))

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
        ok = (
            "What\\\\'s new" not in script
            and "\\n\\nWhat's new:\\n" in script
            and "async function init()" in script
            and "renderCustomAlbums" in script
            and "custom_albums" in script
            and "amazon_devtools_enabled" in script
            and "launchAmazonDevtools" in script
        )
        results.append(_result("Settings script", ok, "Settings JavaScript guard"))
    except Exception as e:
        results.append(_result("Settings script", False, str(e)))

    return results
