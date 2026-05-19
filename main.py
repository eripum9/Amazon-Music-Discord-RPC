# MIT License - Copyright (c) 2026 eripum9

import time
import sys
import os
import subprocess
import threading
import ctypes
import json
import tempfile
import io

from PIL import Image
import pystray

from media_reader import get_track_sync
from notification_reader import get_notification_track_sync, is_new_notification
from album_art import get_album_art, search_tracks, find_custom_album_art
from amazon_devtools import get_devtools_track_sync, apply_devtools_to_track, launch_amazon_music_devtools, restart_amazon_music_devtools, amazon_music_is_running, devtools_environment
from amazon_status_overlay import AmazonStatusOverlay
from discord_rpc import DiscordRPC
from config import load_config, load_config_for_update, save_config, get_exe_path, DEFAULT_CLIENT_ID, CONFIG_PATH, APP_VERSION, redact_data
from updater import check_for_update, prompt_for_update

if getattr(sys, 'frozen', False):
    BUNDLE_DIR = sys._MEIPASS
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, 'frozen', False) else os.path.dirname(sys.executable)
ICON_PATH = os.path.join(BUNDLE_DIR, "icon.png")

MUTEX_NAME = "AmazonMusicRPC_SingleInstance"
EVENT_NAME = "AmazonMusicRPC_OpenSettings"
EVENT_NAME_LAUNCH_AMAZON = "AmazonMusicRPC_LaunchAmazonDevtools"

if getattr(sys, 'frozen', False):
    LOG_DIR = os.path.join(os.environ.get("APPDATA", ""), "AmazonMusicRPC")
else:
    LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(LOG_DIR, "console.log")
DIAGNOSTICS_PATH = os.path.join(LOG_DIR, "diagnostics.json")
MAX_OLD_LOGS = 5
DEVTOOLS_REPAIR_GRACE_SECONDS = 7

rpc_thread = None
rpc_running = False
tray_icon = None
current_config = {}
settings_proc = None
diagnostics_proc = None
status_overlay = None
_picker_lock = threading.Lock()
_picker_pending_key = None
_resolved_cache = {}
_resolved_track_info = {}
_skipped_keys = set()
_wrong_song_prompted_keys = set()
_current_track_raw = None
active_rpc = None
_track_timing_cache = {}
_privacy_restart_lock = threading.Lock()

RPC_CONFIG_KEYS = {
    "discord_client_id",
    "use_custom_client_id",
    "track_mappings",
    "custom_albums",
    "song_link_enabled",
    "song_link_provider",
    "amazon_music_link_region",
    "show_paused",
    "lastfm_enabled",
    "lastfm_api_key",
    "lastfm_api_secret",
    "lastfm_session_key",
    "listenbrainz_enabled",
    "listenbrainz_token",
    "notification_enrichment_enabled",
    "amazon_devtools_enabled",
    "amazon_devtools_auto_launch",
    "privacy_private_session",
    "privacy_blocked_keywords",
    "privacy_disable_scrobbling",
}


def _rpc_config_snapshot(config):
    return {key: config.get(key) for key in RPC_CONFIG_KEYS}


def _write_diagnostics_state(**state):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        payload = {
            "updated_at": time.time(),
            "app_version": APP_VERSION,
            **state,
        }
        payload = redact_data(payload, current_config)
        tmp_path = DIAGNOSTICS_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_path, DIAGNOSTICS_PATH)
    except Exception:
        pass


def _read_diagnostics_state():
    try:
        with open(DIAGNOSTICS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _set_private_session_enabled(enabled):
    global current_config
    enabled = bool(enabled)
    config = load_config_for_update()
    if bool(config.get("privacy_private_session")) == enabled:
        current_config = config
        update_tray_menu()
        return
    config["privacy_private_session"] = enabled
    save_config(config)
    current_config = config
    update_tray_menu()
    if enabled:
        clear_current_presence("private session enabled")

    def _restart():
        with _privacy_restart_lock:
            restart_rpc()
            print(f"[Privacy] Private session {'enabled' if enabled else 'disabled'} from Amazon Music.")

    threading.Thread(target=_restart, daemon=True).start()


def _sync_status_overlay(config=None):
    global status_overlay
    config = config or load_config()
    if config.get("amazon_devtools_enabled"):
        if status_overlay is None:
            status_overlay = AmazonStatusOverlay(
                ICON_PATH,
                load_config,
                _read_diagnostics_state,
                lambda: bool(rpc_running),
                _set_private_session_enabled,
            )
        status_overlay.start()
        return
    if status_overlay is not None:
        status_overlay.stop()
        status_overlay = None


def _privacy_keywords(config):
    raw = config.get("privacy_blocked_keywords", "")
    return [item.strip().lower() for item in raw.replace("\n", ",").split(",") if item.strip()]


def _privacy_match(config, title="", artist="", album=""):
    if config.get("privacy_private_session"):
        return "Private session enabled"
    haystack = f"{title} {artist} {album}".lower()
    for keyword in _privacy_keywords(config):
        if keyword in haystack:
            return f"Matched privacy keyword: {keyword}"
    return ""


def _normalised_text(value):
    return " ".join(str(value or "").strip().lower().split())


def _same_track_field(left, right):
    left = _normalised_text(left)
    right = _normalised_text(right)
    return bool(left and right and left == right)


def _duration_value(value):
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _track_info_payload(track):
    return {
        "title": track.get("title", ""),
        "artist": track.get("artist", ""),
        "album": track.get("album", ""),
        "art_url": track.get("art_url", ""),
        "track_link": track.get("track_link", ""),
        "duration": _duration_value(track.get("duration", 0)),
    }


def _store_resolved_track(raw_key, track):
    if not isinstance(track, dict):
        return
    payload = _track_info_payload(track)
    if raw_key:
        _resolved_track_info[raw_key] = payload
    resolved_key = f"{payload['title']}|{payload['artist']}"
    if payload["title"] or payload["artist"]:
        _resolved_track_info[resolved_key] = payload


def _apply_custom_album_override(config, art_url, album_name, *album_names):
    custom = find_custom_album_art(config, album_name, *album_names)
    if custom:
        return custom.get("art_url", art_url), custom.get("album", album_name) or album_name
    return art_url, album_name


def _apply_resolved_cache(raw_key, title, artist):
    resolved = _resolved_cache.get(raw_key)
    if not resolved:
        return title, artist, False
    return resolved[0] or title, resolved[1] or artist, True


def _resolved_art(raw_key, title, artist, fallback_album=""):
    info = _resolved_track_info.get(raw_key) or _resolved_track_info.get(f"{title}|{artist}")
    if not info or not info.get("art_url"):
        return None
    return (
        info.get("art_url", ""),
        info.get("album", "") or fallback_album,
        info.get("track_link", ""),
        _duration_value(info.get("duration", 0)),
    )


def _apply_wrong_song_choice(choice, raw_key, title, artist, config):
    if not choice:
        return
    _resolved_cache.pop(raw_key, None)
    _resolved_track_info.pop(raw_key, None)
    _skipped_keys.discard(raw_key)
    if choice == "artist":
        if not title:
            return
        mappings = config.get("track_mappings", {})
        mappings.pop(title.lower().strip(), None)
        _resolve_missing_artist(title, "", config, raw_key)
    elif choice == "title":
        if not artist:
            return
        _resolve_missing_title("", artist, raw_key)


def _prompt_wrong_song_async(raw_key, title, artist, config, force=False):
    global _picker_pending_key
    if not force and raw_key in _wrong_song_prompted_keys:
        return
    with _picker_lock:
        if _picker_pending_key is not None:
            return
        _picker_pending_key = raw_key
    _wrong_song_prompted_keys.add(raw_key)

    def _worker():
        global _picker_pending_key
        response = {}
        try:
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
            json.dump({"mode": "wrongsong"}, tmp)
            tmp.close()

            if getattr(sys, 'frozen', False):
                cmd = [sys.executable, '--picker', tmp.name]
            else:
                cmd = [sys.executable, os.path.join(SCRIPT_DIR, "track_picker.py"), tmp.name]

            subprocess.run(cmd, timeout=60)

            with open(tmp.name, "r", encoding="utf-8") as f:
                response = json.load(f)
            os.unlink(tmp.name)
        except Exception as e:
            print(f"[WrongSong] Error: {e}")
        finally:
            with _picker_lock:
                _picker_pending_key = None
        _apply_wrong_song_choice(response.get("choice"), raw_key, title, artist, config)

    threading.Thread(target=_worker, daemon=True).start()


def _cached_start_ts(raw_key):
    cached = _track_timing_cache.get(raw_key)
    if not cached:
        return None
    if time.time() - cached.get("updated_at", 0) > 45:
        _track_timing_cache.pop(raw_key, None)
        return None
    return cached.get("start_ts")


def _track_start_ts(track, raw_key, use_cache=True):
    position = track.get("position")
    start_ts = None
    try:
        if position is not None and float(position) >= 0:
            start_ts = int(time.time() - float(position))
    except (TypeError, ValueError):
        start_ts = None
    if start_ts is None and use_cache:
        start_ts = _cached_start_ts(raw_key) or int(time.time())
    if start_ts is None:
        start_ts = int(time.time())
    _track_timing_cache[raw_key] = {
        "start_ts": start_ts,
        "updated_at": time.time(),
    }
    return start_ts


def _playing_start_ts(track, raw_key, last_start_ts, paused_position, resumed_from_pause):
    if resumed_from_pause and track.get("position") is not None:
        return _track_start_ts(track, raw_key, use_cache=False), None, True
    if last_start_ts is None:
        if track.get("position") is not None:
            return _track_start_ts(track, raw_key), None, False
        if paused_position is not None:
            return int(time.time() - paused_position), None, False
    return last_start_ts, paused_position, False


def _devtools_no_track_state(enabled, current_state):
    if not enabled:
        return current_state
    current_state = current_state if isinstance(current_state, dict) else {}
    if current_state.get("status") in {"unavailable", "error", "launching", "restarting"}:
        return current_state
    return {
        "enabled": True,
        "status": "waiting",
        "detail": "No Amazon Music metadata or SMTC fallback session",
    }


def _signal_primary_launch_amazon():
    try:
        kernel32 = ctypes.windll.kernel32
        event = kernel32.OpenEventW(0x2, False, EVENT_NAME_LAUNCH_AMAZON)
        if event:
            kernel32.SetEvent(event)
            kernel32.CloseHandle(event)
            return True
    except Exception:
        pass
    return False


def _rotated_log_path(index):
    return os.path.join(LOG_DIR, f"console.{index}.log")


def _rotate_logs():
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        oldest = _rotated_log_path(MAX_OLD_LOGS)
        if os.path.exists(oldest):
            os.remove(oldest)
        for index in range(MAX_OLD_LOGS - 1, 0, -1):
            src = _rotated_log_path(index)
            dst = _rotated_log_path(index + 1)
            if os.path.exists(src):
                os.replace(src, dst)
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 0:
            os.replace(LOG_PATH, _rotated_log_path(1))
        open(LOG_PATH, 'w').close()
    except Exception:
        try:
            open(LOG_PATH, 'w').close()
        except Exception:
            pass


class _LogTee(io.TextIOBase):
    def __init__(self, original, log_file_path):
        self._original = original
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        self._file = open(log_file_path, 'a', encoding='utf-8', errors='replace')

    def write(self, s):
        if self._original:
            try:
                self._original.write(s)
            except Exception:
                pass
        try:
            self._file.write(s)
            self._file.flush()
        except Exception:
            pass
        return len(s)

    def flush(self):
        if self._original:
            try:
                self._original.flush()
            except Exception:
                pass
        try:
            self._file.flush()
        except Exception:
            pass


def _run_picker_async(request_data, raw_key, callback):
    global _picker_pending_key
    with _picker_lock:
        if _picker_pending_key is not None:
            return
        _picker_pending_key = raw_key

    def _worker():
        global _picker_pending_key
        response = None
        try:
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
            json.dump(request_data, tmp)
            tmp.close()

            if getattr(sys, 'frozen', False):
                cmd = [sys.executable, '--picker', tmp.name]
            else:
                cmd = [sys.executable, os.path.join(SCRIPT_DIR, "track_picker.py"), tmp.name]

            subprocess.run(cmd, timeout=120)

            with open(tmp.name, "r", encoding="utf-8") as f:
                response = json.load(f)
            os.unlink(tmp.name)
        except Exception as e:
            print(f"[Picker] Error: {e}")
        finally:
            with _picker_lock:
                _picker_pending_key = None
        if response is not None:
            callback(response)

    threading.Thread(target=_worker, daemon=True).start()


def _resolve_missing_artist(title, artist, config, raw_key):
    if raw_key in _resolved_cache:
        return _resolved_cache[raw_key]

    if raw_key in _skipped_keys:
        return title, artist

    mappings = config.get("track_mappings", {})
    mapping_key = title.lower().strip()
    if mapping_key in mappings:
        m = mappings[mapping_key]
        result = (m.get("title", title), m.get("artist", ""))
        _resolved_cache[raw_key] = result
        _store_resolved_track(raw_key, m)
        return result

    with _picker_lock:
        if _picker_pending_key == raw_key:
            return title, artist

    choices = search_tracks(title, limit=5)
    if not choices:
        _skipped_keys.add(raw_key)
        return title, ""

    def _on_result(result):
        if not result:
            _skipped_keys.add(raw_key)
            return
        chosen = result.get("track")
        if not chosen:
            index = result.get("index", -1)
            if index < 0 or index >= len(choices):
                _skipped_keys.add(raw_key)
                return
            chosen = choices[index]
        _resolved_cache[raw_key] = (chosen["title"], chosen["artist"])
        _store_resolved_track(raw_key, chosen)
        if result.get("remember"):
            mappings[mapping_key] = _track_info_payload(chosen)
            config["track_mappings"] = mappings
            save_config(config)

    _run_picker_async(
        {"mode": "choice", "title": title, "choices": choices, "search_query": title, "page_size": 5},
        raw_key,
        _on_result,
    )
    return title, artist


def _resolve_missing_title(title, artist, raw_key):
    if raw_key in _resolved_cache:
        return _resolved_cache[raw_key]

    if raw_key in _skipped_keys:
        return title, artist

    with _picker_lock:
        if _picker_pending_key == raw_key:
            return title, artist

    def _on_result(result):
        if result and result.get("title"):
            _resolved_cache[raw_key] = (result["title"], result.get("artist", artist))
            _store_resolved_track(raw_key, result)
        else:
            _skipped_keys.add(raw_key)

    _run_picker_async({"mode": "input", "artist": artist}, raw_key, _on_result)
    return title, artist


def _try_scrobble(scrobbler, lb_scrobbler, title, artist, start_time, album, duration):
    if not title or not start_time:
        return False
    elapsed = time.time() - start_time
    if not (elapsed >= 30 and (duration > 0 and elapsed >= duration * 0.5 or elapsed >= 240)):
        return False
    if scrobbler:
        try:
            scrobbler.scrobble(title, artist, int(start_time), album, duration)
        except Exception as e:
            print(f"[Last.fm] Scrobble failed: {e}")
    if lb_scrobbler:
        try:
            lb_scrobbler.scrobble(title, artist, int(start_time), album, duration)
        except Exception as e:
            print(f"[ListenBrainz] Scrobble failed: {e}")
    return True


def rpc_loop():
    global rpc_running, _current_track_raw, active_rpc

    config = current_config
    if config.get("use_custom_client_id") and config.get("discord_client_id"):
        client_id = config["discord_client_id"]
    else:
        client_id = DEFAULT_CLIENT_ID

    rpc = DiscordRPC(client_id)
    active_rpc = rpc
    last_track_key = None
    last_art_url = None
    last_album_name = None
    last_art_fetch_key = None
    last_start_ts = None
    last_amazon_track_link = None
    last_deezer_track_link = None
    presence_visible = False
    paused_position = None
    last_playback_status = None

    song_link_enabled = config.get("song_link_enabled", False)
    song_link_provider = config.get("song_link_provider", "amazon")
    if song_link_provider not in {"amazon", "deezer"}:
        song_link_provider = "amazon"
    amazon_music_link_region = config.get("amazon_music_link_region", "com")
    show_paused = config.get("show_paused", True)
    notification_enrichment_enabled = config.get("notification_enrichment_enabled", False)
    amazon_devtools_enabled = config.get("amazon_devtools_enabled", False)
    amazon_devtools_auto_launch = config.get("amazon_devtools_auto_launch", False)
    privacy_disable_scrobbling = config.get("privacy_disable_scrobbling", True)
    devtools_restart_attempted = False
    devtools_unavailable_since = None
    last_amazon_metadata_key = None
    _current_notif_data = None
    _notif_art_fetched_for = None
    _current_amazon_devtools = {
        "enabled": bool(amazon_devtools_enabled),
        "status": "waiting" if amazon_devtools_enabled else "off",
        "detail": "Amazon Music metadata enabled" if amazon_devtools_enabled else "Amazon Music metadata disabled",
    }

    scrobbler = None
    lastfm_state = "disabled"
    if config.get("lastfm_enabled") and config.get("lastfm_session_key"):
        lastfm_state = "error"
        try:
            from lastfm import LastFMScrobbler
            scrobbler = LastFMScrobbler(
                config["lastfm_api_key"],
                config["lastfm_api_secret"],
                config["lastfm_session_key"],
            )
            lastfm_state = "active"
            print("[Last.fm] Scrobbler active.")
        except Exception as e:
            print(f"[Last.fm] Init failed: {e}")
    elif config.get("lastfm_enabled"):
        lastfm_state = "not_authenticated"

    lb_scrobbler = None
    listenbrainz_state = "disabled"
    if config.get("listenbrainz_enabled") and config.get("listenbrainz_token"):
        listenbrainz_state = "error"
        try:
            from listenbrainz_scrobbler import ListenBrainzScrobbler
            lb_scrobbler = ListenBrainzScrobbler(config["listenbrainz_token"])
            listenbrainz_state = "active"
            print("[ListenBrainz] Scrobbler active.")
        except Exception as e:
            print(f"[ListenBrainz] Init failed: {e}")
    elif config.get("listenbrainz_enabled"):
        listenbrainz_state = "missing_token"

    scrobble_track_key = None
    scrobble_start_time = None
    scrobble_duration = 0
    scrobbled = False
    last_deezer_duration = 0
    scrobbling_state = {
        "lastfm": lastfm_state,
        "listenbrainz": listenbrainz_state,
    }

    def _selected_button_link():
        if song_link_provider == "deezer":
            return "Listen on Deezer", last_deezer_track_link
        return "Listen on Amazon Music", last_amazon_track_link

    def _link_buttons():
        if not song_link_enabled:
            return None
        label, url = _selected_button_link()
        if not url:
            return None
        return [{"label": label, "url": url}]

    def _diagnostics_track_link():
        _, url = _selected_button_link()
        return url or last_amazon_track_link or last_deezer_track_link or ""

    def _ensure_deezer_button_link(title, artist):
        nonlocal last_deezer_track_link, last_deezer_duration
        if song_link_provider != "deezer" or last_deezer_track_link or not title or not artist:
            return
        _, _, deezer_link, deezer_duration = get_album_art(title, artist)
        last_deezer_track_link = deezer_link or ""
        if deezer_duration:
            last_deezer_duration = deezer_duration

    def _update_state(track=None, presence=False, error="", privacy_reason=""):
        _write_diagnostics_state(
            rpc_status="running" if rpc_running else "stopped",
            discord_status="connected" if rpc.connected else "retrying",
            client_id=client_id,
            track=track,
            presence_visible=presence,
            album_art_url=last_art_url or "",
            album_name=last_album_name or "",
            track_link=_diagnostics_track_link(),
            notification_enabled=notification_enrichment_enabled,
            notification=_current_notif_data,
            amazon_devtools=_current_amazon_devtools,
            scrobbling=scrobbling_state,
            privacy={
                "private_session": bool(config.get("privacy_private_session")),
                "blocked_keywords": config.get("privacy_blocked_keywords", ""),
                "hidden": bool(privacy_reason),
                "reason": privacy_reason,
            },
            last_error=error,
        )

    print("[RPC] Started.")
    _update_state()

    while rpc_running:
        try:
            track = None

            devtools_found = False
            if amazon_devtools_enabled:
                try:
                    devtools = get_devtools_track_sync(amazon_music_link_region)
                    _current_amazon_devtools = {"enabled": True, **devtools}
                    if devtools.get("status") == "found":
                        devtools_unavailable_since = None
                        devtools_restart_attempted = False
                        devtools_found = True
                        _current_notif_data = None
                        _notif_art_fetched_for = None
                        track = {
                            "title": "",
                            "artist": "",
                            "album": "",
                            "status": "playing",
                            "position": None,
                            "duration": 0,
                        }
                        track, devtools_changed = apply_devtools_to_track(track, devtools)
                        amazon_metadata_key = f"{track.get('title', '')}|{track.get('artist', '')}|{track.get('album', '')}|{track.get('status', '')}"
                        if devtools_changed and amazon_metadata_key != last_amazon_metadata_key:
                            last_amazon_metadata_key = amazon_metadata_key
                            print(f"[Amazon] Metadata: '{track.get('title', '')}' by '{track.get('artist', '')}'")
                    elif devtools.get("status") == "unavailable" and amazon_devtools_auto_launch:
                        now = time.time()
                        if not amazon_music_is_running():
                            devtools_unavailable_since = None
                            devtools_restart_attempted = False
                            _current_amazon_devtools = {
                                "enabled": True,
                                "status": "waiting",
                                "detail": "Amazon Music is closed; waiting for you to open it",
                                "source": "amazon_devtools",
                            }
                        else:
                            if devtools_unavailable_since is None:
                                devtools_unavailable_since = now
                                devtools_restart_attempted = False
                            if not devtools_restart_attempted and now - devtools_unavailable_since >= DEVTOOLS_REPAIR_GRACE_SECONDS:
                                devtools_restart_attempted = True
                                restart_result = restart_amazon_music_devtools()
                                if restart_result.get("ok"):
                                    _current_amazon_devtools = {
                                        "enabled": True,
                                        "status": "restarting",
                                        "detail": "Restarted Amazon Music for metadata",
                                        "source": "amazon_devtools",
                                    }
                                    print("[Amazon] Restarted Amazon Music for metadata.")
                                else:
                                    _current_amazon_devtools = {
                                        "enabled": True,
                                        "status": "error",
                                        "detail": restart_result.get("error") or "Could not restart Amazon Music for metadata",
                                        "source": "amazon_devtools",
                                    }
                            elif not devtools_restart_attempted:
                                _current_amazon_devtools = {
                                    "enabled": True,
                                    "status": "waiting",
                                    "detail": "Amazon Music is open without enhanced metadata; restart repair pending",
                                    "source": "amazon_devtools",
                                }
                except Exception as e:
                    _current_amazon_devtools = {
                        "enabled": True,
                        "status": "error",
                        "detail": str(e),
                        "source": "amazon_devtools",
                    }

            _notif_album = None
            if not devtools_found:
                track = get_track_sync()

            if notification_enrichment_enabled and not devtools_found and track and track["status"] == "playing":
                try:
                    notif = get_notification_track_sync()
                except Exception:
                    notif = None
                if notif and is_new_notification(notif):
                    _current_notif_data = notif
                    print(f"[Notif] New notification: '{notif['title']}' by '{notif['artist']}' — {notif['album']}")
                if _current_notif_data:
                    notif_title = (_current_notif_data["title"] or "").lower().strip()
                    smtc_title = (track["title"] or "").lower().strip()
                    if smtc_title and notif_title and (smtc_title == notif_title or smtc_title in notif_title or notif_title in smtc_title):
                        if _current_notif_data["title"]:
                            track["title"] = _current_notif_data["title"]
                        if _current_notif_data["artist"]:
                            track["artist"] = _current_notif_data["artist"]
                        if _current_notif_data["album"]:
                            track["album"] = _current_notif_data["album"]
                            _notif_album = _current_notif_data["album"]
                    else:
                        _current_notif_data = None

            if track is None:
                _current_amazon_devtools = _devtools_no_track_state(amazon_devtools_enabled, _current_amazon_devtools)
                if presence_visible:
                    rpc.clear()
                    presence_visible = False
                last_track_key = None
                last_art_url = None
                last_album_name = None
                last_art_fetch_key = None
                last_start_ts = None
                last_amazon_track_link = None
                last_deezer_track_link = None
                _current_notif_data = None
                _notif_art_fetched_for = None
                paused_position = None
                last_playback_status = None
                _update_state(track=None, presence=False)
                time.sleep(3)
                continue

            if track["status"] == "paused":
                last_playback_status = "paused"
                privacy_reason = _privacy_match(config, track.get("title", ""), track.get("artist", ""), track.get("album", ""))
                if privacy_reason:
                    if presence_visible:
                        rpc.clear()
                        presence_visible = False
                    if privacy_disable_scrobbling:
                        scrobble_track_key = None
                        scrobble_start_time = None
                        scrobbled = True
                    last_track_key = None
                    last_art_url = None
                    last_album_name = None
                    last_amazon_track_link = None
                    last_deezer_track_link = None
                    hidden_track = {
                        "title": "Hidden by privacy controls",
                        "artist": "",
                        "album": "",
                        "status": track["status"],
                        "position": track.get("position"),
                        "duration": track.get("duration"),
                    }
                    _update_state(track=hidden_track, presence=False, privacy_reason=privacy_reason)
                    time.sleep(3)
                    continue
                paused_key = f"{track.get('title', '')}|{track.get('artist', '')}"
                if paused_key != "|":
                    last_track_key = paused_key
                    if not last_album_name and track.get("album"):
                        last_album_name = track.get("album")
                    if track.get("_amazon_art_url"):
                        last_art_url = track.get("_amazon_art_url")
                    if track.get("_amazon_track_link"):
                        last_amazon_track_link = track.get("_amazon_track_link")
                    if track.get("duration"):
                        last_deezer_duration = track.get("duration")
                    _ensure_deezer_button_link(track.get("title", ""), track.get("artist", ""))
                if show_paused and last_track_key:
                    if track.get("position") is not None:
                        try:
                            paused_position = float(track.get("position"))
                            last_start_ts = None
                        except (TypeError, ValueError):
                            paused_position = None
                    elif last_start_ts is not None:
                        paused_position = time.time() - last_start_ts
                        last_start_ts = None
                    buttons = _link_buttons()
                    title_parts = last_track_key.split("|", 1)
                    pause_start_ts = None
                    pause_duration = 0
                    if paused_position is not None:
                        pause_start_ts = int(time.time() - paused_position)
                        pause_duration = last_deezer_duration or (track["duration"] if track["duration"] else 0)
                    rpc.update(
                        title=title_parts[0],
                        artist=title_parts[1] if len(title_parts) > 1 else "",
                        album_art_url=last_art_url,
                        album_name=last_album_name,
                        start_ts=pause_start_ts,
                        duration=pause_duration,
                        buttons=buttons,
                        small_image="https://raw.githubusercontent.com/eripum9/Amazon-Music-Discord-RPC/master/Images/pause_icon.png",
                        small_text="Paused",
                    )
                    presence_visible = True
                    paused_track = dict(track)
                    paused_track["title"] = title_parts[0]
                    paused_track["artist"] = title_parts[1] if len(title_parts) > 1 else ""
                    paused_track["album"] = last_album_name or track.get("album", "")
                    _update_state(track=paused_track, presence=True)
                elif presence_visible:
                    rpc.clear()
                    presence_visible = False
                    _update_state(track=track, presence=False)
                else:
                    _update_state(track=track, presence=False)
                time.sleep(3)
                continue

            title = track["title"]
            artist = track["artist"]
            raw_key = f"{title}|{artist}"
            resumed_from_pause = last_playback_status == "paused"

            title, artist, resolved_applied = _apply_resolved_cache(raw_key, title, artist)
            if not resolved_applied and _same_track_field(title, artist):
                _prompt_wrong_song_async(raw_key, title, artist, config)

            if title and not artist:
                title, artist = _resolve_missing_artist(title, artist, config, raw_key)

            if artist and not title:
                title, artist = _resolve_missing_title(title, artist, raw_key)

            if not title and not artist:
                if presence_visible:
                    rpc.clear()
                    presence_visible = False
                last_track_key = None
                last_art_url = None
                last_album_name = None
                last_art_fetch_key = None
                last_start_ts = None
                last_amazon_track_link = None
                last_deezer_track_link = None
                paused_position = None
                last_playback_status = "playing"
                _update_state(track=track, presence=False)
                time.sleep(3)
                continue

            privacy_reason = _privacy_match(config, title, artist, track.get("album", ""))
            if privacy_reason:
                private_start_ts = _track_start_ts(track, raw_key)
                if presence_visible:
                    rpc.clear()
                    presence_visible = False
                if privacy_disable_scrobbling:
                    last_start_ts = private_start_ts
                    last_track_key = raw_key
                    last_album_name = track.get("album", "")
                    last_deezer_duration = track["duration"] or 0
                    scrobble_track_key = None
                    scrobble_start_time = None
                    scrobbled = True
                    last_art_url = None
                    last_art_fetch_key = None
                    last_amazon_track_link = None
                    last_deezer_track_link = None
                    hidden_track = {
                        "title": "Hidden by privacy controls",
                        "artist": "",
                        "album": "",
                        "status": track["status"],
                        "position": track.get("position"),
                        "duration": track.get("duration"),
                    }
                    last_playback_status = "playing"
                    _update_state(track=hidden_track, presence=False, privacy_reason=privacy_reason)
                    time.sleep(3)
                    continue

            _current_track_raw = raw_key

            track_art_key = f"{title}|{artist}"

            if raw_key != last_track_key:
                if (scrobbler or lb_scrobbler) and not scrobbled and scrobble_track_key and scrobble_start_time:
                    prev_title, prev_artist = scrobble_track_key.split("|", 1)
                    if _try_scrobble(scrobbler, lb_scrobbler, prev_title, prev_artist, scrobble_start_time, last_album_name, scrobble_duration):
                        scrobbled = True
                    else:
                        elapsed = time.time() - scrobble_start_time
                        print(f"[Scrobble] Previous track not eligible: {elapsed:.0f}s elapsed, {scrobble_duration:.0f}s duration")

                _current_notif_data = None
                _notif_art_fetched_for = None
                last_amazon_track_link = None
                last_deezer_track_link = None

                resolved = _resolved_art(raw_key, title, artist, track.get("album", ""))
                if resolved:
                    last_art_url, last_album_name, last_deezer_track_link, last_deezer_duration = resolved
                elif track.get("_amazon_art_url"):
                    last_art_url = track.get("_amazon_art_url")
                    last_album_name = track.get("album", "")
                    last_amazon_track_link = track.get("_amazon_track_link", "")
                    last_deezer_track_link = None
                    last_deezer_duration = track.get("duration") or 0
                else:
                    last_art_url, last_album_name, last_deezer_track_link, last_deezer_duration = get_album_art(title, artist)
                    last_amazon_track_link = None
                if _notif_album:
                    last_album_name = _notif_album
                elif not last_album_name and track["album"]:
                    last_album_name = track["album"]
                if track.get("_amazon_art_url"):
                    last_art_url = track.get("_amazon_art_url")
                    last_album_name = track.get("album", "") or last_album_name
                    last_deezer_duration = track.get("duration") or last_deezer_duration
                if track.get("_amazon_track_link"):
                    last_amazon_track_link = track.get("_amazon_track_link")
                _ensure_deezer_button_link(title, artist)
                last_art_url, last_album_name = _apply_custom_album_override(
                    config, last_art_url, last_album_name, _notif_album, track.get("album", "")
                )
                last_start_ts = _track_start_ts(track, raw_key)
                if last_art_url:
                    print(f"[Art] Found: '{last_album_name}' for '{title}'")
                else:
                    print(f"[Art] No album art found for '{title}'")
                last_track_key = raw_key
                last_art_fetch_key = track_art_key

                if scrobbler or lb_scrobbler:
                    scrobble_track_key = track_art_key
                    scrobble_start_time = time.time()
                    scrobbled = False
                    scrobble_duration = last_deezer_duration or track["duration"] or 0
                    print(f"[Scrobble] Track duration: {scrobble_duration:.0f}s (deezer={last_deezer_duration}, smtc={track['duration']})")
                    if title:
                        if scrobbler:
                            try:
                                scrobbler.update_now_playing(title, artist, last_album_name, scrobble_duration)
                            except Exception:
                                pass
                        if lb_scrobbler:
                            try:
                                lb_scrobbler.update_now_playing(title, artist, last_album_name, scrobble_duration)
                            except Exception:
                                pass
            elif raw_key in _resolved_cache and last_art_fetch_key != track_art_key:
                resolved = _resolved_art(raw_key, title, artist, track.get("album", ""))
                if resolved:
                    last_art_url, last_album_name, last_deezer_track_link, last_deezer_duration = resolved
                elif track.get("_amazon_art_url"):
                    last_art_url = track.get("_amazon_art_url")
                    last_album_name = track.get("album", "")
                    last_amazon_track_link = track.get("_amazon_track_link", "")
                    last_deezer_track_link = None
                    last_deezer_duration = track.get("duration") or 0
                else:
                    last_art_url, last_album_name, last_deezer_track_link, last_deezer_duration = get_album_art(title, artist)
                    last_amazon_track_link = None
                if _notif_album:
                    last_album_name = _notif_album
                elif not last_album_name and track["album"]:
                    last_album_name = track["album"]
                if track.get("_amazon_art_url"):
                    last_art_url = track.get("_amazon_art_url")
                    last_album_name = track.get("album", "") or last_album_name
                    last_deezer_duration = track.get("duration") or last_deezer_duration
                if track.get("_amazon_track_link"):
                    last_amazon_track_link = track.get("_amazon_track_link")
                _ensure_deezer_button_link(title, artist)
                last_art_url, last_album_name = _apply_custom_album_override(
                    config, last_art_url, last_album_name, _notif_album, track.get("album", "")
                )
                last_art_fetch_key = track_art_key
                print(f"[Art] Refreshed after resolve: '{last_album_name}' for '{title}'")
                if (scrobbler or lb_scrobbler) and scrobble_start_time and not scrobbled:
                    scrobble_track_key = track_art_key
                    scrobble_duration = last_deezer_duration or track["duration"] or scrobble_duration
                    print(f"[Scrobble] Updated scrobble key after resolve: {title}")
                    if scrobbler:
                        try:
                            scrobbler.update_now_playing(title, artist, last_album_name, scrobble_duration)
                        except Exception:
                            pass
                    if lb_scrobbler:
                        try:
                            lb_scrobbler.update_now_playing(title, artist, last_album_name, scrobble_duration)
                        except Exception:
                            pass

            last_start_ts, paused_position, time_refreshed = _playing_start_ts(
                track,
                raw_key,
                last_start_ts,
                paused_position,
                resumed_from_pause,
            )
            if time_refreshed:
                print(f"[RPC] Resumed, refreshed playback time for: {title}")

            if _notif_album:
                last_album_name = _notif_album
                notif_art_key = f"{title}|{artist}|{_notif_album}".lower()
                if _notif_art_fetched_for != notif_art_key:
                    _notif_art, _notif_aname, _notif_link, _notif_dur = get_album_art(title, f"{artist} {_notif_album}")
                    if _notif_art:
                        last_art_url = _notif_art
                        if _notif_link:
                            last_deezer_track_link = _notif_link
                        if _notif_dur:
                            last_deezer_duration = _notif_dur
                        print(f"[Art] Re-fetched art for notification album: '{_notif_album}'")
                    _notif_art_fetched_for = notif_art_key
            last_art_url, last_album_name = _apply_custom_album_override(
                config, last_art_url, last_album_name, _notif_album, track.get("album", "")
            )

            buttons = _link_buttons()

            state_track = dict(track)
            state_track["title"] = title
            state_track["artist"] = artist
            state_track["album"] = last_album_name or track.get("album", "")
            state_track.pop("_amazon_art_url", None)
            state_track.pop("_amazon_track_link", None)
            if privacy_reason:
                hidden_track = {
                    "title": "Hidden by privacy controls",
                    "artist": "",
                    "album": "",
                    "status": track["status"],
                    "position": track.get("position"),
                    "duration": track.get("duration"),
                }
                _update_state(track=hidden_track, presence=False, privacy_reason=privacy_reason)
            else:
                rpc.update(
                    title=title,
                    artist=artist,
                    album_art_url=last_art_url,
                    album_name=last_album_name,
                    start_ts=last_start_ts,
                    duration=track["duration"] or last_deezer_duration,
                    buttons=buttons,
                )
                presence_visible = True
                _update_state(track=state_track, presence=True)

            if (scrobbler or lb_scrobbler) and not scrobbled and scrobble_track_key and scrobble_start_time:
                scrobble_title, scrobble_artist = scrobble_track_key.split("|", 1)
                if _try_scrobble(scrobbler, lb_scrobbler, scrobble_title, scrobble_artist, scrobble_start_time, last_album_name, scrobble_duration):
                    scrobbled = True

            song_duration = last_deezer_duration or (track["duration"] if track["duration"] else 0)
            if song_duration > 0 and last_start_ts and (time.time() - last_start_ts) >= song_duration:
                if track["position"] is not None:
                    last_start_ts = int(time.time() - track["position"])
                else:
                    last_start_ts = int(time.time())
                if scrobbler or lb_scrobbler:
                    scrobble_start_time = time.time()
                    scrobbled = False
                print(f"[RPC] Song ended, restarting: {title}")

            last_playback_status = "playing"
            time.sleep(3)

        except Exception as e:
            print(f"[RPC] Loop error: {e}")
            _update_state(error=str(e))
            time.sleep(3)

    try:
        rpc.clear()
        rpc.disconnect()
    except Exception:
        pass
    if active_rpc is rpc:
        active_rpc = None
    _write_diagnostics_state(
        rpc_status="stopped",
        discord_status="disconnected",
        client_id=client_id,
        track=None,
        presence_visible=False,
        album_art_url="",
        album_name="",
        track_link="",
        notification_enabled=notification_enrichment_enabled,
        notification=None,
        scrobbling=scrobbling_state,
        privacy={
            "private_session": bool(config.get("privacy_private_session")),
            "blocked_keywords": config.get("privacy_blocked_keywords", ""),
            "hidden": False,
            "reason": "",
        },
        last_error="",
    )
    print("[RPC] Stopped.")


def start_rpc():
    global rpc_thread, rpc_running
    if rpc_running:
        return
    rpc_running = True
    rpc_thread = threading.Thread(target=rpc_loop, daemon=True)
    rpc_thread.start()
    update_tray_menu()


def stop_rpc():
    global rpc_running
    rpc_running = False
    update_tray_menu()


def restart_rpc():
    stop_rpc()
    if rpc_thread:
        rpc_thread.join(timeout=10)
    start_rpc()


def clear_current_presence(reason=""):
    rpc = active_rpc
    if rpc:
        try:
            rpc.clear()
            if reason:
                print(f"[Privacy] Cleared Discord presence: {reason}")
            return True
        except Exception as e:
            print(f"[Privacy] Could not clear Discord presence: {e}")
    return False


def toggle_private_session(icon=None, item=None):
    global current_config
    config = load_config_for_update()
    config["privacy_private_session"] = not bool(config.get("privacy_private_session"))
    save_config(config)
    current_config = config
    if config["privacy_private_session"]:
        clear_current_presence("private session enabled")
    restart_rpc()
    print(f"[Privacy] Private session {'enabled' if config['privacy_private_session'] else 'disabled'}.")


def open_settings(icon=None, item=None):
    global current_config, settings_proc
    if settings_proc and settings_proc.poll() is None:
        return
    env = devtools_environment()
    if getattr(sys, 'frozen', False):
        settings_proc = subprocess.Popen([sys.executable, '--settings'], creationflags=0x08000000, env=env)
    else:
        settings_proc = subprocess.Popen(
            [sys.executable, os.path.join(SCRIPT_DIR, 'settings_ui.py')],
            creationflags=0x08000000,
            env=env,
        )
    def _reload_after_delay():
        global current_config
        time.sleep(2)
        old_config = dict(current_config)
        old_rpc_config = _rpc_config_snapshot(old_config)
        for _ in range(300):
            time.sleep(1)
            if settings_proc and settings_proc.poll() is not None:
                new_config = load_config()
                new_rpc_config = _rpc_config_snapshot(new_config)
                if new_config != old_config:
                    current_config = new_config
                    _sync_status_overlay(new_config)
                    if new_rpc_config != old_rpc_config:
                        if new_config.get("privacy_private_session") and not old_config.get("privacy_private_session"):
                            clear_current_presence("private session enabled")
                        restart_rpc()
                        print("[Settings] Config updated, RPC restarted.")
                break
            new_config = load_config()
            new_rpc_config = _rpc_config_snapshot(new_config)
            if new_config != old_config:
                current_config = new_config
                _sync_status_overlay(new_config)
                old_config = dict(new_config)
                if new_rpc_config != old_rpc_config:
                    if new_config.get("privacy_private_session") and not old_rpc_config.get("privacy_private_session"):
                        clear_current_presence("private session enabled")
                    old_rpc_config = new_rpc_config
                    restart_rpc()
                    print("[Settings] Config updated, RPC restarted.")
    threading.Thread(target=_reload_after_delay, daemon=True).start()


def open_diagnostics(icon=None, item=None):
    global diagnostics_proc
    if diagnostics_proc and diagnostics_proc.poll() is None:
        return
    if getattr(sys, 'frozen', False):
        diagnostics_proc = subprocess.Popen([sys.executable, '--diagnostics'], creationflags=0x08000000)
    else:
        diagnostics_proc = subprocess.Popen(
            [sys.executable, os.path.join(SCRIPT_DIR, 'diagnostics_ui.py')],
            creationflags=0x08000000
        )


def launch_amazon_devtools_from_tray(icon=None, item=None):
    def _worker():
        result = launch_amazon_music_devtools()
        if result.get("ok"):
            print("[Amazon] Launched Amazon Music for metadata.")
        else:
            print(f"[Amazon] Could not launch metadata mode: {result.get('error')}")

    threading.Thread(target=_worker, daemon=True).start()


def wrong_song_handler(icon=None, item=None):
    global _current_track_raw
    raw_key = _current_track_raw
    if not raw_key:
        return

    def _worker():
        try:
            track = get_track_sync()
            if not track:
                return
            rk = _current_track_raw or raw_key
            _prompt_wrong_song_async(rk, track["title"], track["artist"], current_config, force=True)
        except Exception as e:
            print(f"[WrongSong] Error: {e}")

    threading.Thread(target=_worker, daemon=True).start()


def _prompt_and_install_update(latest_ver, download_url, changelog="", release_url=None, expected_sha256=""):
    MB_TOPMOST = 0x40000
    print(f"[Update] Downloading installer...")
    try:
        installer_path = prompt_for_update(latest_ver, download_url, changelog, release_url, expected_sha256)
        if not installer_path:
            return
        print(f"[Update] Downloaded to {installer_path}, launching installer...")
        on_quit(tray_icon, None)
    except Exception as e:
        print(f"[Update] Download/install failed: {e}")
        ctypes.windll.user32.MessageBoxW(
            0,
            f"Update failed:\n{e}",
            "Amazon Music RPC — Update Error",
            0x10 | MB_TOPMOST,
        )


def _check_for_update_and_prompt():
    try:
        has_update, latest_ver, download_url, changelog, release_url, expected_sha256 = check_for_update()
        if has_update and download_url:
            print(f"[Update] New version {latest_ver} available!")
            _prompt_and_install_update(latest_ver, download_url, changelog, release_url, expected_sha256)
        elif has_update:
            print(f"[Update] New version {latest_ver} found but no installer asset.")
    except Exception as e:
        print(f"[Update] Check failed: {e}")


def on_quit(icon, item):
    global rpc_running, settings_proc, diagnostics_proc, status_overlay
    rpc_running = False
    if status_overlay is not None:
        status_overlay.stop()
        status_overlay = None
    if settings_proc and settings_proc.poll() is None:
        settings_proc.terminate()
        settings_proc = None
    if diagnostics_proc and diagnostics_proc.poll() is None:
        diagnostics_proc.terminate()
        diagnostics_proc = None
    icon.stop()


def update_tray_menu():
    if tray_icon is None:
        return
    tray_icon.menu = build_menu()
    tray_icon.update_menu()


def build_menu():
    status_text = "Status: Running" if rpc_running else "Status: Stopped"
    return pystray.Menu(
        pystray.MenuItem(status_text, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Settings", open_settings),
        pystray.MenuItem("Diagnostics", open_diagnostics),
        pystray.MenuItem("Launch Amazon Music", launch_amazon_devtools_from_tray),
        pystray.MenuItem("Private Session", toggle_private_session,
                         checked=lambda item: bool(current_config.get("privacy_private_session"))),
        pystray.MenuItem("Wrong Song?", wrong_song_handler),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Start RPC", lambda icon, item: start_rpc(),
                         visible=lambda item: not rpc_running),
        pystray.MenuItem("Stop RPC", lambda icon, item: stop_rpc(),
                         visible=lambda item: rpc_running),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Check for Updates", lambda icon, item: threading.Thread(target=_check_for_update_and_prompt, daemon=True).start()),
        pystray.MenuItem("Quit", on_quit),
    )


def main():
    global tray_icon, current_config

    if '--settings' in sys.argv:
        from settings_ui import SettingsWindow
        SettingsWindow().show()
        return

    if '--diagnostics' in sys.argv:
        from diagnostics_ui import DiagnosticsWindow
        DiagnosticsWindow().show()
        return

    if '--launch-amazon-devtools' in sys.argv:
        if _signal_primary_launch_amazon():
            return
        result = launch_amazon_music_devtools()
        if not result.get("ok"):
            try:
                ctypes.windll.user32.MessageBoxW(
                    0,
                    result.get("error") or "Could not launch Amazon Music for metadata.",
                    "Amazon Music RPC",
                    0x10 | 0x40000,
                )
            except Exception:
                pass
        return

    if '--picker' in sys.argv:
        idx = sys.argv.index('--picker')
        if idx + 1 < len(sys.argv):
            from track_picker import run_from_file
            run_from_file(sys.argv[idx + 1])
        return

    if '--console' in sys.argv:
        from diagnostics_ui import DiagnosticsWindow
        DiagnosticsWindow().show()
        return

    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == 183:
        event = kernel32.OpenEventW(0x2, False, EVENT_NAME)
        if event:
            kernel32.SetEvent(event)
            kernel32.CloseHandle(event)
        kernel32.CloseHandle(mutex)
        sys.exit(0)

    settings_event = kernel32.CreateEventW(None, False, False, EVENT_NAME)
    launch_amazon_event = kernel32.CreateEventW(None, False, False, EVENT_NAME_LAUNCH_AMAZON)

    def _watch_for_settings_signal():
        while rpc_running or tray_icon:
            result = kernel32.WaitForSingleObject(settings_event, 1000)
            if result == 0:
                open_settings()
    threading.Thread(target=_watch_for_settings_signal, daemon=True).start()

    def _watch_for_launch_amazon_signal():
        while rpc_running or tray_icon:
            result = kernel32.WaitForSingleObject(launch_amazon_event, 1000)
            if result == 0:
                launch_amazon_devtools_from_tray()
    threading.Thread(target=_watch_for_launch_amazon_signal, daemon=True).start()

    _rotate_logs()
    sys.stdout = _LogTee(sys.__stdout__, LOG_PATH)
    sys.stderr = _LogTee(sys.__stderr__, LOG_PATH)

    is_startup_launch = '--startup' in sys.argv

    config_exists = os.path.exists(CONFIG_PATH)
    current_config = load_config()

    if os.path.exists(ICON_PATH):
        icon_image = Image.open(ICON_PATH)
    else:
        icon_image = Image.new("RGB", (64, 64), (0, 168, 150))

    tray_icon = pystray.Icon(
        "AmazonMusicRPC",
        icon_image,
        "Amazon Music RPC",
        menu=build_menu(),
    )

    start_rpc()
    _sync_status_overlay(current_config)

    def _check_update():
        _check_for_update_and_prompt()
    threading.Thread(target=_check_update, daemon=True).start()

    should_open_settings = not is_startup_launch and (
        not current_config.get("start_minimized", True)
        or not config_exists
        or not current_config.get("enhanced_metadata_prompt_seen", False)
    )
    if should_open_settings:
        open_settings()

    tray_icon.run()

    stop_rpc()
    _sync_status_overlay({"amazon_devtools_enabled": False})
    if rpc_thread:
        rpc_thread.join(timeout=5)
    print("Goodbye.")


if __name__ == "__main__":
    main()
