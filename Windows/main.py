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

from media_reader import get_track_sync
from notification_reader import get_notification_track_sync, is_new_notification
from album_art import get_album_art, search_tracks, find_custom_album_art
from amazon_devtools import get_devtools_track_sync, apply_devtools_to_track, launch_amazon_music_devtools, restart_amazon_music_devtools, amazon_music_is_running, devtools_environment, amazon_music_search_link
from amazon_status_overlay import AmazonStatusOverlay
from discord_rpc import DiscordRPC
from config import load_config, load_config_for_update, save_config, get_exe_path, DEFAULT_CLIENT_ID, CONFIG_PATH, APP_VERSION, redact_data
from amazify_compat import amazify_compat_state, ensure_amazify_compat, push_rpc_state_to_amazify
from amazify_rpc_bridge import start_amazify_rpc_bridge
from metadata_pipeline import apply_art_result, apply_devtools_source, base_track_for_devtools, diagnostics_track_link, link_buttons, merge_notification_metadata, should_lookup_deezer_button
from rpc_state import GameModeState, ResolvedTrackStore, TrackTimingState, configured_game_mode_processes, devtools_no_track_state, duration_value, game_mode_matches_processes, hidden_privacy_track, normalise_process_name, normalised_text, privacy_keywords, privacy_match, running_process_names, same_track_field, track_info_payload, track_position
from status_summary import metadata_source_summary
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
EVENT_NAME_COMMAND = "AmazonMusicRPC_TrayCommand"

if getattr(sys, 'frozen', False):
    LOG_DIR = os.path.join(os.environ.get("APPDATA", ""), "AmazonMusicRPC")
else:
    LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(LOG_DIR, "console.log")
DIAGNOSTICS_PATH = os.path.join(LOG_DIR, "diagnostics.json")
COMMAND_PATH = os.path.join(LOG_DIR, "tray_command.json")
MAX_OLD_LOGS = 5
DEVTOOLS_REPAIR_GRACE_SECONDS = 7

rpc_thread = None
rpc_running = False
tray_icon = None
current_config = {}
settings_proc = None
diagnostics_proc = None
status_overlay = None
amazify_bridge = None
_picker_lock = threading.Lock()
_picker_pending_key = None
_resolved_store = ResolvedTrackStore()
_resolved_cache = _resolved_store.cache
_resolved_track_info = _resolved_store.track_info
_skipped_keys = _resolved_store.skipped_keys
_wrong_song_prompted_keys = set()
_current_track_raw = None
active_rpc = None
_timing_state = TrackTimingState()
_track_timing_cache = _timing_state.cache
_privacy_restart_lock = threading.Lock()
_game_mode_state = GameModeState()
_game_mode_process_cache = _game_mode_state.process_cache
_game_mode_suppressed_keys = _game_mode_state.suppressed_keys
_last_tray_state = {}
_last_tray_signature = ""
_amazify_compat_cache = {"expires": 0, "value": {}}
_amazify_push_cache = {"signature": "", "at": 0}

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
    "game_mode_enabled",
    "game_mode_processes",
}


def _rpc_config_snapshot(config):
    return {key: config.get(key) for key in RPC_CONFIG_KEYS}


def _write_diagnostics_state(**state):
    global _last_tray_state
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
        _last_tray_state = payload
        update_tray_state(payload)
        _push_amazify_plugin_state()
    except Exception:
        pass


def _amazify_compat_snapshot(force=False):
    now = time.time()
    if not force and now < _amazify_compat_cache.get("expires", 0):
        return _amazify_compat_cache.get("value") or {}
    try:
        value = amazify_compat_state(APP_VERSION)
    except Exception as e:
        value = {"installed": False, "running": False, "error": str(e)}
    _amazify_compat_cache["value"] = value
    _amazify_compat_cache["expires"] = now + 15
    return value


def _amazify_metadata_owner(force=False):
    compat = _amazify_compat_snapshot(force)
    if compat.get("plugin_enabled") and compat.get("devtools_port"):
        return compat
    return {}


def _amazify_bridge_payload():
    state = _last_tray_state if isinstance(_last_tray_state, dict) else _read_diagnostics_state()
    return {
        "snapshot": _tray_menu_snapshot(state),
        "compat": _amazify_compat_snapshot(),
    }


def _push_amazify_plugin_state():
    compat = _amazify_metadata_owner()
    port = compat.get("devtools_port") if compat else 0
    if not port:
        return
    payload = _amazify_bridge_payload()
    signature = json.dumps(payload.get("snapshot", {}), sort_keys=True) + "|" + str(port)
    now = time.time()
    if signature == _amazify_push_cache.get("signature") and now - _amazify_push_cache.get("at", 0) < 2:
        return
    _amazify_push_cache["signature"] = signature
    _amazify_push_cache["at"] = now

    def _push():
        push_rpc_state_to_amazify(port, {"ok": True, "app": "AmazonMusicRPC", "version": APP_VERSION, **payload})

    threading.Thread(target=_push, daemon=True).start()


def _start_amazify_compat():
    global amazify_bridge
    amazify_bridge = start_amazify_rpc_bridge(_amazify_bridge_payload, _handle_tray_command)
    if amazify_bridge:
        print(f"[Amazify] RPC bridge listening on 127.0.0.1:{amazify_bridge.port}.")
    else:
        print("[Amazify] RPC bridge port is already in use.")

    def _install():
        result = ensure_amazify_compat(APP_VERSION)
        _amazify_compat_cache["value"] = result
        _amazify_compat_cache["expires"] = time.time() + 15
        if result.get("installed"):
            state = "enabled" if result.get("plugin_enabled") else "installed"
            print(f"[Amazify] Compatibility plugin {state}.")
        else:
            print("[Amazify] Not installed; compatibility plugin skipped.")
        try:
            _sync_status_overlay(current_config)
        except Exception:
            pass

    threading.Thread(target=_install, daemon=True).start()


def _read_diagnostics_state():
    try:
        with open(DIAGNOSTICS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_tray_command(command):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        payload = {"command": command, "created_at": time.time()}
        tmp_path = COMMAND_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp_path, COMMAND_PATH)
        return True
    except Exception as e:
        print(f"[Tray] Could not write command: {e}")
        return False


def _signal_primary_command(command):
    if not _write_tray_command(command):
        return False
    kernel32 = ctypes.windll.kernel32
    event = kernel32.OpenEventW(0x2, False, EVENT_NAME_COMMAND)
    if event:
        kernel32.SetEvent(event)
        kernel32.CloseHandle(event)
        return True
    return False


def _read_tray_command():
    try:
        with open(COMMAND_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return str(payload.get("command") or "")
    except Exception:
        return ""


def _set_private_session_enabled(enabled):
    global current_config
    enabled = bool(enabled)
    config = load_config_for_update()
    if bool(config.get("privacy_private_session")) == enabled:
        current_config = config
        update_tray_state()
        return
    config["privacy_private_session"] = enabled
    save_config(config)
    current_config = config
    update_tray_state()
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
        if _amazify_metadata_owner(force=True):
            if status_overlay is not None:
                status_overlay.stop()
                status_overlay = None
            return
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


_privacy_keywords = privacy_keywords
_privacy_match = privacy_match
_normalised_text = normalised_text
_same_track_field = same_track_field
_duration_value = duration_value
_track_info_payload = track_info_payload
_normalise_process_name = normalise_process_name
_configured_game_mode_processes = configured_game_mode_processes
_game_mode_matches_processes = game_mode_matches_processes
_running_process_names = running_process_names


def _store_resolved_track(raw_key, track):
    _resolved_store.store_track(raw_key, track)


def _apply_custom_album_override(config, art_url, album_name, *album_names):
    custom = find_custom_album_art(config, album_name, *album_names)
    if custom:
        return custom.get("art_url", art_url), custom.get("album", album_name) or album_name
    return art_url, album_name


def _apply_resolved_cache(raw_key, title, artist):
    return _resolved_store.apply_cache(raw_key, title, artist)


def _resolved_art(raw_key, title, artist, fallback_album=""):
    return _resolved_store.resolved_art(raw_key, title, artist, fallback_album)


def _apply_wrong_song_choice(choice, raw_key, title, artist, config):
    if not choice:
        return
    _resolved_store.clear_choice(raw_key)
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


def _game_mode_active(config):
    return _game_mode_state.active(config, _running_process_names)


def _should_prompt_wrong_song(raw_key, title, artist, config):
    return _game_mode_state.should_prompt_wrong_song(
        raw_key,
        title,
        artist,
        config,
        _running_process_names,
        lambda: print("[GameMode] Wrong-song picker suppressed."),
    )


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
                env = _frozen_child_env()
            else:
                cmd = [sys.executable, os.path.join(SCRIPT_DIR, "track_picker.py"), tmp.name]
                env = None

            subprocess.run(cmd, timeout=60, env=env)

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
    return _timing_state.cached_start_ts(raw_key)


def _track_start_ts(track, raw_key, use_cache=True):
    return _timing_state.track_start_ts(track, raw_key, use_cache)


_track_position = track_position


def _playing_start_ts(track, raw_key, last_start_ts, paused_position, resumed_from_pause):
    return _timing_state.playing_start_ts(track, raw_key, last_start_ts, paused_position, resumed_from_pause)


_devtools_no_track_state = devtools_no_track_state


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


def _frozen_child_env(base_env=None):
    env = dict(base_env or os.environ)
    if getattr(sys, 'frozen', False):
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


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
                env = _frozen_child_env()
            else:
                cmd = [sys.executable, os.path.join(SCRIPT_DIR, "track_picker.py"), tmp.name]
                env = None

            subprocess.run(cmd, timeout=120, env=env)

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

    def _link_buttons(title="", artist=""):
        return link_buttons(
            song_link_enabled,
            song_link_provider,
            amazon_music_link_region,
            last_amazon_track_link,
            last_deezer_track_link,
            title,
            artist,
            amazon_music_search_link,
        )

    def _diagnostics_track_link(track=None):
        return diagnostics_track_link(
            track,
            song_link_provider,
            amazon_music_link_region,
            last_amazon_track_link,
            last_deezer_track_link,
            amazon_music_search_link,
        )

    def _ensure_deezer_button_link(title, artist):
        nonlocal last_deezer_track_link, last_deezer_duration
        if not should_lookup_deezer_button(song_link_provider, last_deezer_track_link, title, artist):
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
            track_link=_diagnostics_track_link(track),
            notification_enabled=notification_enrichment_enabled,
            notification=_current_notif_data,
            amazon_devtools=_current_amazon_devtools,
            amazify=_amazify_compat_snapshot(),
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
            amazon_running_hint = None
            if amazon_devtools_enabled:
                try:
                    amazify_metadata = _amazify_metadata_owner(force=True)
                    amazify_port = amazify_metadata.get("devtools_port") if amazify_metadata else None
                    devtools = get_devtools_track_sync(
                        amazon_music_link_region,
                        port=amazify_port,
                        method="amazify" if amazify_port else "",
                    )
                    _current_amazon_devtools = {"enabled": True, **devtools}
                    if amazify_port:
                        _current_amazon_devtools["owner"] = "amazify"
                    if devtools.get("status") == "found":
                        devtools_unavailable_since = None
                        devtools_restart_attempted = False
                        _current_notif_data = None
                        _notif_art_fetched_for = None
                        track, devtools_changed, devtools_found = apply_devtools_source(
                            base_track_for_devtools(),
                            devtools,
                            apply_devtools_to_track,
                        )
                        amazon_metadata_key = f"{track.get('title', '')}|{track.get('artist', '')}|{track.get('album', '')}|{track.get('status', '')}"
                        if devtools_changed and amazon_metadata_key != last_amazon_metadata_key:
                            last_amazon_metadata_key = amazon_metadata_key
                            print(f"[Amazon] Metadata: '{track.get('title', '')}' by '{track.get('artist', '')}'")
                    elif amazify_port and devtools.get("status") == "unavailable":
                        devtools_unavailable_since = None
                        devtools_restart_attempted = False
                        _current_amazon_devtools = {
                            "enabled": True,
                            **devtools,
                            "status": "waiting",
                            "detail": "Amazify is connected; waiting for Amazon Music metadata",
                            "source": "amazon_devtools",
                            "owner": "amazify",
                        }
                    elif devtools.get("status") == "unavailable" and amazon_devtools_auto_launch:
                        now = time.time()
                        amazon_running_hint = amazon_music_is_running()
                        if not amazon_running_hint:
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
                                        "method": restart_result.get("method", ""),
                                    }
                                    method = f" ({restart_result.get('method')})" if restart_result.get("method") else ""
                                    print(f"[Amazon] Restarted Amazon Music for metadata{method}.")
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
                track = None if amazon_running_hint is False else get_track_sync()

            if notification_enrichment_enabled and not devtools_found and track and track["status"] == "playing":
                try:
                    notif = get_notification_track_sync()
                except Exception:
                    notif = None
                if notif and is_new_notification(notif):
                    _current_notif_data = notif
                    print(f"[Notif] New notification: '{notif['title']}' by '{notif['artist']}' — {notif['album']}")
                if _current_notif_data:
                    track, _notif_album, keep_notification = merge_notification_metadata(track, _current_notif_data)
                    if not keep_notification:
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
                    hidden_track = hidden_privacy_track(track)
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
                    title_parts = last_track_key.split("|", 1)
                    paused_title = title_parts[0]
                    paused_artist = title_parts[1] if len(title_parts) > 1 else ""
                    buttons = _link_buttons(paused_title, paused_artist)
                    pause_start_ts = None
                    pause_duration = 0
                    if paused_position is not None:
                        pause_start_ts = int(time.time() - paused_position)
                        pause_duration = last_deezer_duration or (track["duration"] if track["duration"] else 0)
                    rpc.update(
                        title=paused_title,
                        artist=paused_artist,
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
                    paused_track["title"] = paused_title
                    paused_track["artist"] = paused_artist
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
            if not resolved_applied and _should_prompt_wrong_song(raw_key, title, artist, config):
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
                    hidden_track = hidden_privacy_track(track)
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
                fetched = None if resolved or track.get("_amazon_art_url") else get_album_art(title, artist)
                art_state = apply_art_result(track, resolved, fetched, _notif_album, last_album_name)
                last_art_url = art_state["art_url"]
                last_album_name = art_state["album"]
                last_deezer_track_link = art_state["deezer_link"]
                last_deezer_duration = art_state["duration"]
                last_amazon_track_link = art_state["amazon_link"]
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
                fetched = None if resolved or track.get("_amazon_art_url") else get_album_art(title, artist)
                art_state = apply_art_result(track, resolved, fetched, _notif_album, last_album_name)
                last_art_url = art_state["art_url"]
                last_album_name = art_state["album"]
                last_deezer_track_link = art_state["deezer_link"]
                last_deezer_duration = art_state["duration"]
                last_amazon_track_link = art_state["amazon_link"]
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
                if resumed_from_pause:
                    print(f"[RPC] Resumed, refreshed playback time for: {title}")
                else:
                    print(f"[RPC] Playback position changed, refreshed timer for: {title}")

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
            if track.get("_amazon_track_link"):
                last_amazon_track_link = track.get("_amazon_track_link")

            buttons = _link_buttons(title, artist)

            state_track = dict(track)
            state_track["title"] = title
            state_track["artist"] = artist
            state_track["album"] = last_album_name or track.get("album", "")
            state_track.pop("_amazon_art_url", None)
            state_track.pop("_amazon_track_link", None)
            if privacy_reason:
                hidden_track = hidden_privacy_track(track)
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
    config = current_config if isinstance(current_config, dict) else {}
    client_id = config.get("discord_client_id") if config.get("use_custom_client_id") and config.get("discord_client_id") else DEFAULT_CLIENT_ID
    amazon_devtools_enabled = bool(config.get("amazon_devtools_enabled"))
    _write_diagnostics_state(
        rpc_status="starting",
        discord_status="unknown",
        client_id=client_id,
        track=None,
        presence_visible=False,
        album_art_url="",
        album_name="",
        track_link="",
        notification_enabled=bool(config.get("notification_enrichment_enabled")),
        notification=None,
        amazon_devtools={
            "enabled": amazon_devtools_enabled,
            "status": "waiting" if amazon_devtools_enabled else "off",
            "detail": "RPC is starting",
        },
        scrobbling={
            "lastfm": "starting" if config.get("lastfm_enabled") else "disabled",
            "listenbrainz": "starting" if config.get("listenbrainz_enabled") else "disabled",
        },
        privacy={
            "private_session": bool(config.get("privacy_private_session")),
            "blocked_keywords": config.get("privacy_blocked_keywords", ""),
            "hidden": False,
            "reason": "",
        },
        last_error="",
    )
    rpc_thread = threading.Thread(target=rpc_loop, daemon=True)
    rpc_thread.start()
    update_tray_state()


def stop_rpc():
    global rpc_running
    rpc_running = False
    update_tray_state()


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


def toggle_game_mode(icon=None, item=None):
    global current_config
    config = load_config_for_update()
    config["game_mode_enabled"] = not bool(config.get("game_mode_enabled"))
    save_config(config)
    current_config = config
    restart_rpc()
    update_tray_state()
    print(f"[GameMode] {'Enabled' if config['game_mode_enabled'] else 'Disabled'}.")


def open_settings(icon=None, item=None):
    global current_config, settings_proc
    if settings_proc and settings_proc.poll() is None:
        return
    env = _frozen_child_env(devtools_environment())
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
    env = _frozen_child_env()
    if getattr(sys, 'frozen', False):
        diagnostics_proc = subprocess.Popen([sys.executable, '--diagnostics'], creationflags=0x08000000, env=env)
    else:
        diagnostics_proc = subprocess.Popen(
            [sys.executable, os.path.join(SCRIPT_DIR, 'diagnostics_ui.py')],
            creationflags=0x08000000,
            env=env,
        )


def launch_amazon_devtools_from_tray(icon=None, item=None):
    def _worker():
        result = launch_amazon_music_devtools()
        if result.get("ok"):
            method = f" ({result.get('method')})" if result.get("method") else ""
            print(f"[Amazon] Launched Amazon Music for metadata{method}.")
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
        installer_path = prompt_for_update(latest_ver, download_url, changelog, release_url, expected_sha256, defer_until_exit=True)
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


def toggle_rpc_from_tray(icon=None, item=None):
    if rpc_running:
        stop_rpc()
    else:
        start_rpc()


def _handle_tray_command(command):
    command = str(command or "").strip().lower()
    if command == "settings":
        open_settings()
    elif command == "diagnostics":
        open_diagnostics()
    elif command == "launch_amazon":
        launch_amazon_devtools_from_tray()
    elif command == "private":
        toggle_private_session()
    elif command == "game_mode":
        toggle_game_mode()
    elif command == "wrong_song":
        wrong_song_handler()
    elif command == "toggle_rpc":
        toggle_rpc_from_tray()
    elif command == "updates":
        threading.Thread(target=_check_for_update_and_prompt, daemon=True).start()
    elif command == "quit" and tray_icon is not None:
        on_quit(tray_icon, None)


def _tray_trim(value, limit=58):
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    while "  " in text:
        text = text.replace("  ", " ")
    if len(text) <= limit:
        return text
    return text[:max(0, limit - 3)].rstrip() + "..."


def _format_tray_seconds(value):
    try:
        total = int(float(value))
    except (TypeError, ValueError):
        return ""
    if total < 0:
        return ""
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _tray_time_label(track):
    position = _format_tray_seconds(track.get("position"))
    duration = _format_tray_seconds(track.get("duration"))
    if position and duration:
        return f"{position} / {duration}"
    return duration or position


def _tray_line(label, value, limit=64):
    text = _tray_trim(value, max(10, limit - len(label) - 2))
    return f"{label}: {text}" if text else f"{label}: -"


def _tray_menu_snapshot(state=None):
    state = state if isinstance(state, dict) else (_last_tray_state or _read_diagnostics_state())
    config = current_config if isinstance(current_config, dict) else {}
    track = state.get("track") if isinstance(state.get("track"), dict) else {}
    privacy = state.get("privacy") if isinstance(state.get("privacy"), dict) else {}
    amazon = state.get("amazon_devtools") if isinstance(state.get("amazon_devtools"), dict) else {}
    source = metadata_source_summary(state, config)
    title = track.get("title") or ""
    artist = track.get("artist") or ""
    album = track.get("album") or state.get("album_name") or ""
    track_link = state.get("track_link") or ""
    presence_visible = bool(state.get("presence_visible"))
    private = bool(config.get("privacy_private_session") or privacy.get("hidden"))
    return {
        "rpc": "On" if rpc_running else "Off",
        "discord": str(state.get("discord_status") or ("connected" if active_rpc and active_rpc.connected else "waiting")).title(),
        "presence": "Private" if private else ("Visible" if presence_visible else "Hidden"),
        "source": source.get("label") or "Waiting",
        "source_detail": source.get("detail") or "",
        "title": title,
        "artist": artist,
        "album": album,
        "time": _tray_time_label(track),
        "track_link": track_link,
        "has_track": bool(title or artist or album),
        "private": private,
        "devtools": "On" if config.get("amazon_devtools_enabled") else "Off",
        "devtools_status": str(amazon.get("status") or ("off" if not config.get("amazon_devtools_enabled") else "waiting")).title(),
        "game_mode": "On" if config.get("game_mode_enabled") else "Off",
        "link_provider": str(config.get("song_link_provider") or "amazon").title(),
    }


def _tray_signature(snapshot):
    keys = ("rpc", "discord", "presence", "source", "title", "artist", "album", "time", "track_link", "devtools", "devtools_status", "game_mode", "link_provider")
    return "|".join(str(snapshot.get(key) or "") for key in keys)


def _tray_icon_title(snapshot):
    if snapshot.get("private"):
        return "Amazon Music RPC - Private"
    if snapshot.get("title"):
        title = snapshot.get("title")
        artist = snapshot.get("artist")
        text = f"{title} - {artist}" if artist else title
        return _tray_trim(text, 120)
    return f"Amazon Music RPC - RPC {snapshot.get('rpc', 'Off')}"


def on_quit(icon, item):
    global rpc_running, settings_proc, diagnostics_proc, status_overlay, amazify_bridge
    rpc_running = False
    if amazify_bridge is not None:
        amazify_bridge.stop()
        amazify_bridge = None
    if status_overlay is not None:
        status_overlay.stop()
        status_overlay = None
    if settings_proc and settings_proc.poll() is None:
        settings_proc.terminate()
        settings_proc = None
    if diagnostics_proc and diagnostics_proc.poll() is None:
        diagnostics_proc.terminate()
        diagnostics_proc = None
    if icon is not None and hasattr(icon, "stop"):
        icon.stop()


def update_tray_state(state=None, force=False):
    global _last_tray_state, _last_tray_signature
    if tray_icon is None:
        return
    if isinstance(state, dict):
        _last_tray_state = state
    snapshot = _tray_menu_snapshot(_last_tray_state)
    signature = _tray_signature(snapshot)
    if not force and signature == _last_tray_signature:
        return
    _last_tray_signature = signature
    snapshot["tooltip"] = _tray_icon_title(snapshot)
    try:
        tray_icon.update_state(snapshot)
    except Exception:
        pass


def update_tray_menu(state=None, force=False):
    update_tray_state(state, force)


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

    if '--tray-command' in sys.argv:
        idx = sys.argv.index('--tray-command')
        command = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        _signal_primary_command(command)
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
    tray_command_event = kernel32.CreateEventW(None, False, False, EVENT_NAME_COMMAND)

    def _watch_for_settings_signal():
        while True:
            result = kernel32.WaitForSingleObject(settings_event, 1000)
            if result == 0:
                open_settings()
    threading.Thread(target=_watch_for_settings_signal, daemon=True).start()

    def _watch_for_launch_amazon_signal():
        while True:
            result = kernel32.WaitForSingleObject(launch_amazon_event, 1000)
            if result == 0:
                launch_amazon_devtools_from_tray()
    threading.Thread(target=_watch_for_launch_amazon_signal, daemon=True).start()

    def _watch_for_tray_command_signal():
        while True:
            result = kernel32.WaitForSingleObject(tray_command_event, 1000)
            if result == 0:
                _handle_tray_command(_read_tray_command())
    threading.Thread(target=_watch_for_tray_command_signal, daemon=True).start()

    _rotate_logs()
    sys.stdout = _LogTee(sys.__stdout__, LOG_PATH)
    sys.stderr = _LogTee(sys.__stderr__, LOG_PATH)

    is_startup_launch = '--startup' in sys.argv

    config_exists = os.path.exists(CONFIG_PATH)
    current_config = load_config()

    from qt_tray_ui import QtTrayController

    tray_callbacks = {
        "settings": open_settings,
        "diagnostics": open_diagnostics,
        "launch_amazon": launch_amazon_devtools_from_tray,
        "private": toggle_private_session,
        "game_mode": toggle_game_mode,
        "wrong_song": wrong_song_handler,
        "toggle_rpc": toggle_rpc_from_tray,
        "updates": lambda: threading.Thread(target=_check_for_update_and_prompt, daemon=True).start(),
        "quit": lambda: on_quit(tray_icon, None),
    }
    tray_icon = QtTrayController(ICON_PATH, tray_callbacks)
    _start_amazify_compat()

    start_rpc()
    _sync_status_overlay(current_config)

    def _check_update():
        _check_for_update_and_prompt()
    threading.Thread(target=_check_update, daemon=True).start()

    should_open_settings = not is_startup_launch and (
        not current_config.get("start_minimized", True)
        or not config_exists
        or not current_config.get("enhanced_metadata_prompt_seen", False)
        or not current_config.get("setup_wizard_seen", False)
    )
    if should_open_settings:
        open_settings()

    update_tray_state(force=True)
    tray_icon.run()

    stop_rpc()
    _sync_status_overlay({"amazon_devtools_enabled": False})
    if rpc_thread:
        rpc_thread.join(timeout=5)
    print("Goodbye.")


if __name__ == "__main__":
    main()
