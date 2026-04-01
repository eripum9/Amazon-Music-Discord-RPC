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
from album_art import get_album_art, search_tracks
from discord_rpc import DiscordRPC
from config import load_config, save_config, get_exe_path, DEFAULT_CLIENT_ID
from updater import check_for_update, RELEASES_PAGE

if getattr(sys, 'frozen', False):
    BUNDLE_DIR = sys._MEIPASS
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, 'frozen', False) else os.path.dirname(sys.executable)
ICON_PATH = os.path.join(BUNDLE_DIR, "icon.png")

MUTEX_NAME = "AmazonMusicRPC_SingleInstance"
EVENT_NAME = "AmazonMusicRPC_OpenSettings"

if getattr(sys, 'frozen', False):
    LOG_DIR = os.path.join(os.environ.get("APPDATA", ""), "AmazonMusicRPC")
else:
    LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(LOG_DIR, "console.log")

rpc_thread = None
rpc_running = False
tray_icon = None
current_config = {}
settings_proc = None
console_proc = None
_picker_lock = threading.Lock()
_picker_pending_key = None
_resolved_cache = {}
_skipped_keys = set()
_current_track_raw = None


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
            callback(response)
        except Exception as e:
            print(f"[Picker] Error: {e}")
        finally:
            with _picker_lock:
                _picker_pending_key = None

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
        return result

    with _picker_lock:
        if _picker_pending_key == raw_key:
            return title, artist

    choices = search_tracks(title, limit=5)
    if not choices:
        _skipped_keys.add(raw_key)
        return title, ""

    def _on_result(result):
        if not result or result.get("index", -1) < 0:
            _skipped_keys.add(raw_key)
            return
        chosen = choices[result["index"]]
        _resolved_cache[raw_key] = (chosen["title"], chosen["artist"])
        if result.get("remember"):
            mappings[mapping_key] = {"title": chosen["title"], "artist": chosen["artist"]}
            config["track_mappings"] = mappings
            save_config(config)

    _run_picker_async({"mode": "choice", "title": title, "choices": choices}, raw_key, _on_result)
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
        else:
            _skipped_keys.add(raw_key)

    _run_picker_async({"mode": "input", "artist": artist}, raw_key, _on_result)
    return title, artist


def rpc_loop():
    global rpc_running, _current_track_raw

    config = current_config
    if config.get("use_custom_client_id") and config.get("discord_client_id"):
        client_id = config["discord_client_id"]
    else:
        client_id = DEFAULT_CLIENT_ID

    rpc = DiscordRPC(client_id)
    last_track_key = None
    last_art_url = None
    last_album_name = None
    last_art_fetch_key = None
    last_start_ts = None
    last_track_link = None
    presence_visible = False

    song_link_enabled = config.get("song_link_enabled", False)
    show_paused = config.get("show_paused", True)

    scrobbler = None
    if config.get("lastfm_enabled") and config.get("lastfm_session_key"):
        try:
            from lastfm import LastFMScrobbler
            scrobbler = LastFMScrobbler(
                config["lastfm_api_key"],
                config["lastfm_api_secret"],
                config["lastfm_session_key"],
            )
            print("[Last.fm] Scrobbler active.")
        except Exception as e:
            print(f"[Last.fm] Init failed: {e}")

    scrobble_track_key = None
    scrobble_start_time = None
    scrobble_duration = 0
    scrobbled = False
    last_deezer_duration = 0

    print("[RPC] Started.")

    while rpc_running:
        try:
            track = get_track_sync()

            if track is None:
                if presence_visible:
                    rpc.clear()
                    presence_visible = False
                last_track_key = None
                last_art_url = None
                last_album_name = None
                last_art_fetch_key = None
                last_start_ts = None
                last_track_link = None
                time.sleep(5)
                continue

            if track["status"] == "paused":
                if show_paused and last_track_key:
                    buttons = None
                    if song_link_enabled and last_track_link:
                        buttons = [{"label": "Listen on Deezer", "url": last_track_link}]
                    title_parts = last_track_key.split("|", 1)
                    rpc.update(
                        title=title_parts[0],
                        artist=title_parts[1] if len(title_parts) > 1 else "",
                        album_art_url=last_art_url,
                        album_name=last_album_name,
                        buttons=buttons,
                        small_image="https://raw.githubusercontent.com/eripum9/Amazon-Music-Discord-RPC/master/images/pause_icon.png",
                        small_text="Paused",
                    )
                    presence_visible = True
                elif presence_visible:
                    rpc.clear()
                    presence_visible = False
                last_start_ts = None
                time.sleep(5)
                continue

            title = track["title"]
            artist = track["artist"]
            raw_key = f"{title}|{artist}"

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
                last_track_link = None
                time.sleep(5)
                continue

            _current_track_raw = raw_key

            track_art_key = f"{title}|{artist}"

            if raw_key != last_track_key:
                if scrobbler and not scrobbled and scrobble_track_key and scrobble_start_time:
                    prev_title, prev_artist = scrobble_track_key.split("|", 1)
                    if prev_title:  # only scrobble if we had a resolved title
                        elapsed = time.time() - scrobble_start_time
                        duration = scrobble_duration
                        if elapsed >= 30 and (duration > 0 and elapsed >= duration * 0.5 or elapsed >= 240):
                            try:
                                scrobbler.scrobble(prev_title, prev_artist, int(scrobble_start_time), last_album_name, duration)
                                scrobbled = True
                            except Exception as e:
                                print(f"[Last.fm] Scrobble on track change failed: {e}")
                        else:
                            print(f"[Last.fm] Previous track not eligible: {elapsed:.0f}s elapsed, {duration:.0f}s duration")

                last_art_url, last_album_name, last_track_link, last_deezer_duration = get_album_art(title, artist)
                if not last_album_name and track["album"]:
                    last_album_name = track["album"]
                last_start_ts = int(time.time() - track["position"]) if track["position"] else int(time.time())
                if last_art_url:
                    print(f"[Art] Found: '{last_album_name}' for '{title}'")
                else:
                    print(f"[Art] No album art found for '{title}'")
                last_track_key = raw_key
                last_art_fetch_key = track_art_key

                if scrobbler:
                    scrobble_track_key = track_art_key
                    scrobble_start_time = time.time()
                    scrobbled = False
                    scrobble_duration = last_deezer_duration or track["duration"] or 0
                    print(f"[Last.fm] Track duration: {scrobble_duration:.0f}s (deezer={last_deezer_duration}, smtc={track['duration']})")
                    if title:  # only send now_playing if title is resolved
                        try:
                            scrobbler.update_now_playing(title, artist, last_album_name, scrobble_duration)
                        except Exception:
                            pass
            elif raw_key in _resolved_cache and last_art_fetch_key != track_art_key:
                last_art_url, last_album_name, last_track_link, last_deezer_duration = get_album_art(title, artist)
                if not last_album_name and track["album"]:
                    last_album_name = track["album"]
                last_art_fetch_key = track_art_key
                print(f"[Art] Refreshed after resolve: '{last_album_name}' for '{title}'")
                if scrobbler and scrobble_start_time and not scrobbled:
                    scrobble_track_key = track_art_key
                    scrobble_duration = last_deezer_duration or track["duration"] or scrobble_duration
                    print(f"[Last.fm] Updated scrobble key after resolve: {title}")
                    try:
                        scrobbler.update_now_playing(title, artist, last_album_name, scrobble_duration)
                    except Exception:
                        pass

            if track["position"] is not None:
                last_start_ts = int(time.time() - track["position"])

            buttons = None
            if song_link_enabled and last_track_link:
                buttons = [{"label": "Listen on Deezer", "url": last_track_link}]

            rpc.update(
                title=title,
                artist=artist,
                album_art_url=last_art_url,
                album_name=last_album_name,
                start_ts=last_start_ts,
                duration=track["duration"],
                buttons=buttons,
            )
            presence_visible = True

            if scrobbler and not scrobbled and scrobble_track_key and scrobble_start_time:
                scrobble_title, scrobble_artist = scrobble_track_key.split("|", 1)
                if scrobble_title:  # only check if we have a resolved title
                    elapsed = time.time() - scrobble_start_time
                    duration = scrobble_duration
                    if elapsed >= 30 and (duration > 0 and elapsed >= duration * 0.5 or elapsed >= 240):
                        try:
                            scrobbler.scrobble(scrobble_title, scrobble_artist, int(scrobble_start_time), last_album_name, duration)
                            scrobbled = True
                        except Exception:
                            pass

            time.sleep(5)

        except Exception as e:
            print(f"[RPC] Loop error: {e}")
            time.sleep(5)

    try:
        rpc.clear()
        rpc.disconnect()
    except Exception:
        pass
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


def open_settings(icon=None, item=None):
    global current_config, settings_proc
    if settings_proc and settings_proc.poll() is None:
        return
    if getattr(sys, 'frozen', False):
        settings_proc = subprocess.Popen([sys.executable, '--settings'], creationflags=0x08000000)
    else:
        settings_proc = subprocess.Popen(
            [sys.executable, os.path.join(SCRIPT_DIR, 'settings_ui.py')],
            creationflags=0x08000000
        )
    def _reload_after_delay():
        global current_config
        time.sleep(2)
        old_config = dict(current_config)
        for _ in range(300):
            time.sleep(1)
            if settings_proc and settings_proc.poll() is not None:
                new_config = load_config()
                if new_config != old_config:
                    current_config = new_config
                    restart_rpc()
                    print("[Settings] Config updated, RPC restarted.")
                break
            new_config = load_config()
            if new_config != old_config:
                current_config = new_config
                old_config = dict(new_config)
                restart_rpc()
                print("[Settings] Config updated, RPC restarted.")
    threading.Thread(target=_reload_after_delay, daemon=True).start()


def open_console(icon=None, item=None):
    global console_proc
    if console_proc and console_proc.poll() is None:
        return
    if getattr(sys, 'frozen', False):
        console_proc = subprocess.Popen([sys.executable, '--console', LOG_PATH], creationflags=0x08000000)
    else:
        console_proc = subprocess.Popen(
            [sys.executable, os.path.join(SCRIPT_DIR, 'track_picker.py'), '--console', LOG_PATH],
            creationflags=0x08000000
        )


def wrong_song_handler(icon=None, item=None):
    global _current_track_raw
    raw_key = _current_track_raw
    if not raw_key:
        return

    def _worker():
        global _current_track_raw
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

            choice = response.get("choice")
            if not choice:
                return

            rk = _current_track_raw or raw_key
            _resolved_cache.pop(rk, None)
            _skipped_keys.discard(rk)

            track = get_track_sync()
            if not track:
                return

            if choice == "artist":
                title = track["title"]
                if not title:
                    return
                mappings = current_config.get("track_mappings", {})
                mappings.pop(title.lower().strip(), None)
                _resolve_missing_artist(title, "", current_config, rk)
            elif choice == "title":
                artist = track["artist"]
                if not artist:
                    return
                _resolve_missing_title("", artist, rk)
        except Exception as e:
            print(f"[WrongSong] Error: {e}")

    threading.Thread(target=_worker, daemon=True).start()


def on_quit(icon, item):
    global rpc_running, settings_proc, console_proc
    rpc_running = False
    if settings_proc and settings_proc.poll() is None:
        settings_proc.terminate()
        settings_proc = None
    if console_proc and console_proc.poll() is None:
        console_proc.terminate()
        console_proc = None
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
        pystray.MenuItem("Show Console", open_console),
        pystray.MenuItem("Wrong Song?", wrong_song_handler),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Start RPC", lambda icon, item: start_rpc(),
                         visible=lambda item: not rpc_running),
        pystray.MenuItem("Stop RPC", lambda icon, item: stop_rpc(),
                         visible=lambda item: rpc_running),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Check for Updates", lambda icon, item: __import__('webbrowser').open(RELEASES_PAGE)),
        pystray.MenuItem("Quit", on_quit),
    )


def main():
    global tray_icon, current_config

    if '--settings' in sys.argv:
        from settings_ui import SettingsWindow
        SettingsWindow().show()
        return

    if '--picker' in sys.argv:
        idx = sys.argv.index('--picker')
        if idx + 1 < len(sys.argv):
            from track_picker import run_from_file
            run_from_file(sys.argv[idx + 1])
        return

    if '--console' in sys.argv:
        idx = sys.argv.index('--console')
        if idx + 1 < len(sys.argv):
            from track_picker import show_console
            show_console(sys.argv[idx + 1])
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

    def _watch_for_settings_signal():
        while rpc_running or tray_icon:
            result = kernel32.WaitForSingleObject(settings_event, 1000)
            if result == 0:
                open_settings()
    threading.Thread(target=_watch_for_settings_signal, daemon=True).start()

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        open(LOG_PATH, 'w').close()
    except Exception:
        pass
    sys.stdout = _LogTee(sys.__stdout__, LOG_PATH)
    sys.stderr = _LogTee(sys.__stderr__, LOG_PATH)

    is_startup_launch = '--startup' in sys.argv

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

    def _check_update():
        has_update, latest_ver, _ = check_for_update()
        if has_update:
            print(f"[Update] New version {latest_ver} available!")
            try:
                tray_icon.notify(
                    f"Version {latest_ver} is available.\nRight-click tray \u2192 Check for Updates",
                    "Amazon Music RPC - Update Available",
                )
            except Exception:
                pass
    threading.Thread(target=_check_update, daemon=True).start()

    if not is_startup_launch:
        open_settings()

    tray_icon.run()

    stop_rpc()
    if rpc_thread:
        rpc_thread.join(timeout=5)
    print("Goodbye.")


if __name__ == "__main__":
    main()
