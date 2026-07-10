# MIT License - Copyright (c) 2026 eripum9

import base64
import ctypes
import json
import os
import re
import sys
import tempfile
import winreg
from ctypes import wintypes

APP_NAME = "AmazonMusicRPC"
DEFAULT_CLIENT_ID = "1479925587697995857"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", ""), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

if not os.environ.get("APPDATA") or getattr(sys, "frozen", False) is False:
    CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
    CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

APP_VERSION = "4.0.1"
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
DISCORD_STATUS_DISPLAY_MODES = ("application", "artist", "album", "track")

DEFAULTS = {
    "discord_client_id": DEFAULT_CLIENT_ID,
    "use_custom_client_id": False,
    "discord_status_display": "artist",
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
    "amazon_music_launcher_override": "",
    "privacy_private_session": False,
    "privacy_blocked_keywords": "",
    "privacy_disable_scrobbling": True,
    "game_mode_enabled": False,
    "game_mode_processes": "",
    "intro_seen": False,
    "setup_wizard_seen": False,
    "setup_wizard_version": "",
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


def normalize_discord_status_display(value):
    text = str(value or "").strip().lower()
    return text if text in DISCORD_STATUS_DISPLAY_MODES else "artist"


def _complete_config(saved):
    config = {**DEFAULTS, **saved}
    config["discord_status_display"] = normalize_discord_status_display(config.get("discord_status_display"))
    if saved and "enhanced_metadata_prompt_seen" not in saved and "amazon_devtools_enabled" not in saved:
        config["amazon_devtools_enabled"] = True
        config["amazon_devtools_auto_launch"] = True
    if saved and "setup_wizard_seen" not in saved:
        config["setup_wizard_seen"] = True
        config["setup_wizard_version"] = config.get("setup_wizard_version") or APP_VERSION
    return config


def _read_saved_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        saved = json.load(f)
    return saved if isinstance(saved, dict) else {}


def _secret_path():
    return os.path.join(os.path.dirname(CONFIG_PATH), "secrets.dpapi.json")


STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REDACTION_TEXT = "[redacted]"
SENSITIVE_CONFIG_KEYS = {
    "lastfm_session_key",
    "lastfm_api_secret",
    "listenbrainz_token",
}
DPAPI_PREFIX = "dpapi:"
SENSITIVE_TEXT_PATTERNS = [
    re.compile(r'("(?:lastfm_session_key|lastfm_api_secret|listenbrainz_token)"\s*:\s*")([^"]+)(")', re.IGNORECASE),
    re.compile(r"(\bToken\s+)([A-Za-z0-9._~+/=-]{6,})", re.IGNORECASE),
    re.compile(r"(\bAuthorization\s*:\s*Token\s+)([A-Za-z0-9._~+/=-]{6,})", re.IGNORECASE),
]


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _dpapi_blob(data):
    buffer = ctypes.create_string_buffer(data)
    return _DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _dpapi_available():
    return os.name == "nt" and hasattr(ctypes, "windll")


def _dpapi_protect_text(value):
    text = str(value or "")
    if not text or text.startswith(DPAPI_PREFIX) or not _dpapi_available():
        return text
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    in_blob, buffer = _dpapi_blob(text.encode("utf-8"))
    out_blob = _DATA_BLOB()
    if not crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        raw = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return DPAPI_PREFIX + base64.b64encode(raw).decode("ascii")
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect_text(value):
    text = str(value or "")
    if not text.startswith(DPAPI_PREFIX) or not _dpapi_available():
        return text
    try:
        encrypted = base64.b64decode(text[len(DPAPI_PREFIX):])
    except Exception:
        return ""
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    in_blob, buffer = _dpapi_blob(encrypted)
    out_blob = _DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        return ""
    try:
        raw = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return raw.decode("utf-8")
    finally:
        kernel32.LocalFree(out_blob.pbData)


def protect_sensitive_config(config):
    protected = dict(config or {})
    for key in SENSITIVE_CONFIG_KEYS:
        if key in protected:
            protected[key] = _dpapi_protect_text(protected.get(key))
    return protected


def unprotect_sensitive_config(config):
    unprotected = dict(config or {})
    for key in SENSITIVE_CONFIG_KEYS:
        if key in unprotected:
            unprotected[key] = _dpapi_unprotect_text(unprotected.get(key))
    return unprotected


def _atomic_write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _read_secret_config():
    path = _secret_path()
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    return unprotect_sensitive_config(data)


def _write_secret_config(secrets):
    secrets = {key: value for key, value in (secrets or {}).items() if key in SENSITIVE_CONFIG_KEYS and str(value or "")}
    path = _secret_path()
    if secrets:
        _atomic_write_json(path, protect_sensitive_config(secrets))
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def _public_config(config):
    return {key: value for key, value in dict(config or {}).items() if key not in SENSITIVE_CONFIG_KEYS}


def _config_secret_values(config):
    return {key: (config or {}).get(key, "") for key in SENSITIVE_CONFIG_KEYS if key in (config or {})}


def _load_public_and_secret_config():
    saved = _read_saved_config()
    secrets = _read_secret_config()
    moved = _config_secret_values(saved)
    if moved:
        for key, value in moved.items():
            if str(value or ""):
                secrets[key] = _dpapi_unprotect_text(value)
            else:
                secrets.pop(key, None)
        saved = _public_config(saved)
        _write_secret_config(secrets)
        _atomic_write_json(CONFIG_PATH, saved)
    return {**saved, **secrets}


def migrate_sensitive_config():
    if not os.path.exists(CONFIG_PATH):
        return False
    saved = _read_saved_config()
    if not any(key in saved for key in SENSITIVE_CONFIG_KEYS):
        return False
    _load_public_and_secret_config()
    return True


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
            saved = _load_public_and_secret_config()
        except (OSError, json.JSONDecodeError, TypeError) as e:
            print(f"[Config] Could not read config, using defaults: {e}")
            saved = {}
        config = _complete_config(saved)
    else:
        config = dict(DEFAULTS)
    return config


def load_config_for_update():
    if os.path.exists(CONFIG_PATH):
        return _complete_config(_load_public_and_secret_config())
    return dict(DEFAULTS)


def save_config(config):
    secrets = _read_secret_config()
    for key, value in _config_secret_values(config).items():
        if str(value or ""):
            secrets[key] = value
        else:
            secrets.pop(key, None)
    _write_secret_config(secrets)
    _atomic_write_json(CONFIG_PATH, _public_config(config))


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
