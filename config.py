# MIT License - Copyright (c) 2026 eripum9

import json
import os
import sys
import tempfile
import winreg

APP_NAME = "AmazonMusicRPC"
DEFAULT_CLIENT_ID = "1479925587697995857"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", ""), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

if not os.environ.get("APPDATA") or getattr(sys, "frozen", False) is False:
    CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
    CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

APP_VERSION = "2.2.3"

DEFAULTS = {
    "discord_client_id": DEFAULT_CLIENT_ID,
    "use_custom_client_id": False,
    "start_on_startup": False,
    "start_minimized": True,
    "track_mappings": {},
    "custom_albums": [],
    "song_link_enabled": False,
    "show_paused": True,
    "lastfm_enabled": False,
    "lastfm_api_key": "2c2d97048ae5546831b1b1a025a8f9ec",
    "lastfm_api_secret": "5d9fecd9d4836815d5c1f05cde9a611c",
    "lastfm_session_key": "",
    "lastfm_username": "",
    "listenbrainz_enabled": False,
    "listenbrainz_token": "",
    "notification_enrichment_enabled": False,
    "app_probe_enabled": False,
    "privacy_private_session": False,
    "privacy_blocked_keywords": "",
    "privacy_disable_scrobbling": True,
    "intro_seen": False,
    "diagnostics_tests_warning_dismissed": False,
    "settings_window_width": 460,
    "settings_window_height": 800,
    "diagnostics_window_width": 940,
    "diagnostics_window_height": 700,
}

STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, json.JSONDecodeError, TypeError) as e:
            print(f"[Config] Could not read config, using defaults: {e}")
            saved = {}
        config = {**DEFAULTS, **saved}
    else:
        config = dict(DEFAULTS)
    return config


def save_config(config):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="config.", suffix=".tmp", dir=CONFIG_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, CONFIG_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get_exe_path():
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def is_startup_enabled():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_startup(enable, start_minimized=True):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE)
        if enable:
            exe = get_exe_path()
            args = " --startup" if start_minimized else ""
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe}"{args}')
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except OSError as e:
        print(f"[Config] Registry error: {e}")
