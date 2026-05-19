# MIT License - Copyright (c) 2026 eripum9

import json
import os
import re
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

APP_VERSION = "3.1.3"
AMAZON_MUSIC_LINK_REGIONS = (
    "com",
    "de",
    "co.uk",
    "fr",
    "it",
    "es",
    "co.jp",
    "ca",
    "com.au",
    "com.br",
    "com.mx",
)

DEFAULTS = {
    "discord_client_id": DEFAULT_CLIENT_ID,
    "use_custom_client_id": False,
    "start_on_startup": False,
    "start_minimized": True,
    "track_mappings": {},
    "custom_albums": [],
    "song_link_enabled": True,
    "song_link_provider": "amazon",
    "amazon_music_link_region": "com",
    "show_paused": True,
    "lastfm_enabled": False,
    "lastfm_api_key": "2c2d97048ae5546831b1b1a025a8f9ec",
    "lastfm_api_secret": "5d9fecd9d4836815d5c1f05cde9a611c",
    "lastfm_session_key": "",
    "lastfm_username": "",
    "listenbrainz_enabled": False,
    "listenbrainz_token": "",
    "notification_enrichment_enabled": False,
    "amazon_devtools_enabled": False,
    "amazon_devtools_auto_launch": False,
    "privacy_private_session": False,
    "privacy_blocked_keywords": "",
    "privacy_disable_scrobbling": True,
    "intro_seen": False,
    "enhanced_metadata_prompt_seen": False,
    "diagnostics_tests_warning_dismissed": False,
    "settings_window_width": 460,
    "settings_window_height": 800,
    "diagnostics_window_width": 940,
    "diagnostics_window_height": 700,
}


def normalize_amazon_music_link_region(value):
    text = str(value or "").strip().lower().lstrip(".")
    return text if text in AMAZON_MUSIC_LINK_REGIONS else "com"


def _complete_config(saved):
    config = {**DEFAULTS, **saved}
    if saved and "enhanced_metadata_prompt_seen" not in saved and "amazon_devtools_enabled" not in saved:
        config["amazon_devtools_enabled"] = True
        config["amazon_devtools_auto_launch"] = True
    return config


def _read_saved_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        saved = json.load(f)
    return saved if isinstance(saved, dict) else {}

STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REDACTION_TEXT = "[redacted]"
SENSITIVE_CONFIG_KEYS = {
    "lastfm_session_key",
    "lastfm_api_secret",
    "listenbrainz_token",
}
SENSITIVE_TEXT_PATTERNS = [
    re.compile(r'("(?:lastfm_session_key|lastfm_api_secret|listenbrainz_token)"\s*:\s*")([^"]+)(")', re.IGNORECASE),
    re.compile(r"(\bToken\s+)([A-Za-z0-9._~+/=-]{6,})", re.IGNORECASE),
    re.compile(r"(\bAuthorization\s*:\s*Token\s+)([A-Za-z0-9._~+/=-]{6,})", re.IGNORECASE),
]


def _sensitive_values(config=None):
    values = set()
    for source in (DEFAULTS, config or {}):
        for key in SENSITIVE_CONFIG_KEYS:
            value = str(source.get(key, "") or "")
            if len(value) >= 6:
                values.add(value)
    return values


def redact_text(value, config=None):
    text = str(value or "")
    for pattern in SENSITIVE_TEXT_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}{REDACTION_TEXT}{match.group(3) if len(match.groups()) > 2 else ''}", text)
    for secret in sorted(_sensitive_values(config), key=len, reverse=True):
        text = text.replace(secret, REDACTION_TEXT)
    return text


def redact_data(value, config=None):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_CONFIG_KEYS:
                redacted[key] = REDACTION_TEXT if item else ""
            else:
                redacted[key] = redact_data(item, config)
        return redacted
    if isinstance(value, list):
        return [redact_data(item, config) for item in value]
    if isinstance(value, str):
        return redact_text(value, config)
    return value


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            saved = _read_saved_config()
        except (OSError, json.JSONDecodeError, TypeError) as e:
            print(f"[Config] Could not read config, using defaults: {e}")
            saved = {}
        config = _complete_config(saved)
    else:
        config = dict(DEFAULTS)
    return config


def load_config_for_update():
    if os.path.exists(CONFIG_PATH):
        return _complete_config(_read_saved_config())
    return dict(DEFAULTS)


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
