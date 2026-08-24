# MIT License - Copyright (c) 2026 eripum9

"""macOS configuration, Keychain secrets, and login-item integration."""

from __future__ import annotations

import json
import os
import plistlib
import re
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import fcntl


APP_NAME = "AmazonMusicRPC"
APP_DISPLAY_NAME = "Amazon Music RPC"
APP_VERSION = "5.0.1-macos-beta.1"
BUNDLE_IDENTIFIER = "io.github.eripum9.amazon-music-rpc"
DEFAULT_CLIENT_ID = "1479925587697995857"
CONFIG_REVISION_KEY = "_revision"

CONFIG_DIR = str(Path.home() / "Library" / "Application Support" / APP_NAME)
CONFIG_PATH = str(Path(CONFIG_DIR) / "config.json")
LOG_PATH = str(Path(CONFIG_DIR) / "console.log")
EVENT_LOG_PATH = str(Path(CONFIG_DIR) / "events.jsonl")
DIAGNOSTICS_PATH = str(Path(CONFIG_DIR) / "diagnostics.json")
LAUNCH_AGENT_PATH = str(Path.home() / "Library" / "LaunchAgents" / f"{BUNDLE_IDENTIFIER}.plist")
KEYCHAIN_SERVICE = BUNDLE_IDENTIFIER

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
    "amazon_devtools_enabled": True,
    "amazon_devtools_auto_launch": False,
    "amazon_devtools_port": 0,
    "privacy_private_session": False,
    "privacy_blocked_keywords": "",
    "privacy_disable_scrobbling": True,
    "game_mode_enabled": False,
    "game_mode_processes": "",
    "intro_seen": False,
    "setup_wizard_seen": False,
    "setup_wizard_version": "",
    "settings_window_width": 760,
    "settings_window_height": 720,
    "diagnostics_window_width": 940,
    "diagnostics_window_height": 700,
    "automatic_update_checks": True,
    "deezer_lookup_enabled": True,
    "itunes_lookup_enabled": True,
}

SENSITIVE_CONFIG_KEYS = {
    "lastfm_session_key",
    "lastfm_api_secret",
    "listenbrainz_token",
}
REDACTION_TEXT = "[redacted]"
SENSITIVE_TEXT_PATTERNS = (
    re.compile(
        r'("(?:lastfm_session_key|lastfm_api_secret|listenbrainz_token)"\s*:\s*")([^"]+)(")',
        re.IGNORECASE,
    ),
    re.compile(r"(\bToken\s+)([A-Za-z0-9._~+/=-]{6,})", re.IGNORECASE),
    re.compile(r"(\bAuthorization\s*:\s*Token\s+)([A-Za-z0-9._~+/=-]{6,})", re.IGNORECASE),
)

_CONFIG_THREAD_LOCK = threading.RLock()


class ConfigConflictError(RuntimeError):
    pass


def normalize_amazon_music_link_region(value):
    text = str(value or "").strip().lower().lstrip(".")
    return text if text in AMAZON_MUSIC_LINK_REGIONS else "com"


def normalize_discord_status_display(value):
    text = str(value or "").strip().lower()
    return text if text in DISCORD_STATUS_DISPLAY_MODES else "artist"


def _complete_config(saved):
    saved = saved if isinstance(saved, dict) else {}
    config = {**DEFAULTS, **saved}
    config["amazon_music_link_region"] = normalize_amazon_music_link_region(
        config.get("amazon_music_link_region")
    )
    config["discord_status_display"] = normalize_discord_status_display(
        config.get("discord_status_display")
    )
    try:
        config[CONFIG_REVISION_KEY] = max(0, int(saved.get(CONFIG_REVISION_KEY, 0)))
    except (TypeError, ValueError):
        config[CONFIG_REVISION_KEY] = 0
    return config


def _atomic_write(path, payload, mode=0o600):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _atomic_write_json(path, payload):
    _atomic_write(path, json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"))


@contextmanager
def _exclusive_config_lock(timeout=10):
    lock_path = Path(str(CONFIG_PATH) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _CONFIG_THREAD_LOCK, lock_path.open("a+b") as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Timed out waiting for the configuration lock")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _security(args, *, input_text=None, timeout=8):
    try:
        return subprocess.run(
            ["/usr/bin/security", *args],
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _keychain_read(key):
    result = _security(
        ["find-generic-password", "-a", str(key), "-s", KEYCHAIN_SERVICE, "-w"]
    )
    if not result or result.returncode != 0:
        return ""
    return (result.stdout or "").rstrip("\r\n")


def _keychain_write(key, value):
    value = str(value or "")
    if not value:
        return _keychain_delete(key)
    result = _security(
        [
            "add-generic-password",
            "-U",
            "-a",
            str(key),
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
            value,
        ]
    )
    return bool(result and result.returncode == 0)


def _keychain_delete(key):
    result = _security(
        ["delete-generic-password", "-a", str(key), "-s", KEYCHAIN_SERVICE]
    )
    return bool(result is None or result.returncode in (0, 44))


def _read_public_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _public_config(config):
    return {
        key: value
        for key, value in dict(config or {}).items()
        if key not in SENSITIVE_CONFIG_KEYS
    }


def _load_config_locked():
    public = _read_public_config()
    # Migrate any pre-Keychain prototype files without retaining plaintext secrets.
    migrated = False
    for key in SENSITIVE_CONFIG_KEYS:
        legacy = str(public.pop(key, "") or "")
        if legacy:
            _keychain_write(key, legacy)
            migrated = True
    if migrated:
        _atomic_write_json(CONFIG_PATH, public)
    secrets = {key: _keychain_read(key) for key in SENSITIVE_CONFIG_KEYS}
    return _complete_config({**public, **{k: v for k, v in secrets.items() if v}})


def load_config():
    with _exclusive_config_lock():
        return _load_config_locked()


def load_config_for_update():
    return load_config()


def _stored_revision(config):
    try:
        return max(0, int((config or {}).get(CONFIG_REVISION_KEY, 0)))
    except (TypeError, ValueError):
        return 0


def _persist_config_locked(config, revision):
    persisted = _complete_config(config)
    persisted[CONFIG_REVISION_KEY] = int(revision)
    for key in SENSITIVE_CONFIG_KEYS:
        if key in persisted and not _keychain_write(key, persisted.get(key, "")):
            raise OSError(f"Could not store {key} in macOS Keychain")
    _atomic_write_json(CONFIG_PATH, _public_config(persisted))
    return persisted


def save_config(config):
    with _exclusive_config_lock():
        current = _load_config_locked()
        current_revision = _stored_revision(current)
        expected = (config or {}).get(CONFIG_REVISION_KEY)
        if Path(CONFIG_PATH).exists() and expected is None:
            raise ConfigConflictError("Whole-configuration saves require a revision")
        if expected is not None and int(expected) != current_revision:
            raise ConfigConflictError(
                f"Configuration changed from revision {expected} to {current_revision}"
            )
        return _persist_config_locked(config, current_revision + 1)


def update_config_fields(updates, expected_revision=None):
    if not isinstance(updates, dict):
        raise TypeError("Configuration updates must be a dictionary")
    invalid = set(updates).difference(DEFAULTS)
    if invalid:
        raise KeyError(f"Unsupported configuration fields: {', '.join(sorted(invalid))}")
    with _exclusive_config_lock():
        current = _load_config_locked()
        current_revision = _stored_revision(current)
        if expected_revision is not None and int(expected_revision) > current_revision:
            raise ConfigConflictError("Configuration revision is newer than the stored revision")
        current.update(updates)
        return _persist_config_locked(current, current_revision + 1)


def mutate_config_fields(fields, transform):
    allowed = set(fields or ())
    if not allowed or allowed.difference(DEFAULTS):
        raise KeyError("Configuration mutation fields must be known settings")
    with _exclusive_config_lock():
        current = _load_config_locked()
        proposed = transform({key: current.get(key) for key in allowed})
        if not isinstance(proposed, dict) or set(proposed).difference(allowed):
            raise ValueError("Configuration mutation changed fields outside its declared scope")
        current.update(proposed)
        return _persist_config_locked(current, _stored_revision(current) + 1)


def credential_storage_status():
    available = Path("/usr/bin/security").exists()
    keys = [key for key in sorted(SENSITIVE_CONFIG_KEYS) if available and _keychain_read(key)]
    return {
        "keychain_available": available,
        "keychain_keys": keys,
        "credential_manager_available": available,
        "credential_manager_keys": keys,
        "dpapi_fallback_keys": [],
    }


def clear_sensitive_credentials():
    with _exclusive_config_lock():
        removed = all(_keychain_delete(key) for key in SENSITIVE_CONFIG_KEYS)
        public = _read_public_config()
        if public:
            public[CONFIG_REVISION_KEY] = _stored_revision(public) + 1
            _atomic_write_json(CONFIG_PATH, _public_config(public))
        return removed


def migrate_sensitive_config():
    with _exclusive_config_lock():
        before = _read_public_config()
        had_secrets = any(key in before for key in SENSITIVE_CONFIG_KEYS)
        _load_config_locked()
        return had_secrets


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
        text = pattern.sub(
            lambda match: f"{match.group(1)}{REDACTION_TEXT}{match.group(3) if len(match.groups()) > 2 else ''}",
            text,
        )
    for secret in sorted(_sensitive_values(config), key=len, reverse=True):
        text = text.replace(secret, REDACTION_TEXT)
    return text


def redact_data(value, config=None):
    if isinstance(value, dict):
        return {
            key: REDACTION_TEXT if str(key).lower() in SENSITIVE_CONFIG_KEYS and item else redact_data(item, config)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_data(item, config) for item in value]
    if isinstance(value, str):
        return redact_text(value, config)
    return value


def get_exe_path():
    return sys.executable if getattr(sys, "frozen", False) else str(Path(sys.argv[0]).resolve())


def _startup_arguments(start_minimized=True):
    if getattr(sys, "frozen", False):
        args = [sys.executable]
    else:
        args = [sys.executable, str(Path(__file__).with_name("main.py"))]
    if start_minimized:
        args.append("--startup")
    return args


def is_startup_enabled():
    path = Path(LAUNCH_AGENT_PATH)
    if not path.exists():
        return False
    try:
        with path.open("rb") as handle:
            payload = plistlib.load(handle)
        return payload.get("Label") == BUNDLE_IDENTIFIER and bool(payload.get("RunAtLoad"))
    except (OSError, plistlib.InvalidFileException):
        return False


def set_startup(enable, start_minimized=True):
    path = Path(LAUNCH_AGENT_PATH)
    if not enable:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return True
    payload = {
        "Label": BUNDLE_IDENTIFIER,
        "ProgramArguments": _startup_arguments(start_minimized),
        "RunAtLoad": True,
        "ProcessType": "Interactive",
        "StandardOutPath": LOG_PATH,
        "StandardErrorPath": LOG_PATH,
    }
    _atomic_write(path, plistlib.dumps(payload, fmt=plistlib.FMT_XML))
    return True
