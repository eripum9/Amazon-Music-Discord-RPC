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
        import diagnostics_ui
        cards = diagnostics_ui._build_cards({}, load_config(), {"value": "Unavailable", "state": "bad"})
        results.append(_result("Diagnostics cards", len(cards) == 7, f"{len(cards)} cards"))
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
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings_ui.py"), "r", encoding="utf-8") as f:
            source = f.read()
        ok = "What\\\\'s new" not in source and "async function init()" in source
        results.append(_result("Settings script", ok, "Settings JavaScript guard"))
    except Exception as e:
        results.append(_result("Settings script", False, str(e)))

    return results
