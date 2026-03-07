import time
import sys
import os
import subprocess
import threading
import ctypes

from PIL import Image
import pystray

from media_reader import get_track_sync
from album_art import get_album_art
from discord_rpc import DiscordRPC
from config import load_config, save_config, get_exe_path, DEFAULT_CLIENT_ID

if getattr(sys, 'frozen', False):
    BUNDLE_DIR = sys._MEIPASS
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, 'frozen', False) else os.path.dirname(sys.executable)
ICON_PATH = os.path.join(BUNDLE_DIR, "icon.png")

MUTEX_NAME = "AmazonMusicRPC_SingleInstance"
EVENT_NAME = "AmazonMusicRPC_OpenSettings"

rpc_thread = None
rpc_running = False
tray_icon = None
current_config = {}
settings_proc = None


def rpc_loop():
    global rpc_running

    config = current_config
    if config.get("use_custom_client_id") and config.get("discord_client_id"):
        client_id = config["discord_client_id"]
    else:
        client_id = DEFAULT_CLIENT_ID

    rpc = DiscordRPC(client_id)
    last_track_key = None
    last_art_url = None
    last_album_name = None
    last_start_ts = None
    presence_visible = False

    print("[RPC] Started.")

    while rpc_running:
        try:
            track = get_track_sync()

            if track is None or not track["title"] or track["status"] == "paused":
                if presence_visible:
                    rpc.clear()
                    presence_visible = False
                if track is None or not track["title"]:
                    last_track_key = None
                    last_art_url = None
                    last_album_name = None
                    last_start_ts = None
                time.sleep(5)
                continue

            track_key = f"{track['title']}|{track['artist']}"

            if track_key != last_track_key:
                last_art_url, last_album_name = get_album_art(track["title"], track["artist"])
                if not last_album_name and track["album"]:
                    last_album_name = track["album"]
                last_start_ts = int(time.time() - track["position"]) if track["position"] else int(time.time())
                if last_art_url:
                    print(f"[Art] Found: '{last_album_name}' for '{track['title']}'")
                else:
                    print(f"[Art] No album art found for '{track['title']}'")

            last_track_key = track_key

            rpc.update(
                title=track["title"],
                artist=track["artist"],
                album_art_url=last_art_url,
                album_name=last_album_name,
                start_ts=last_start_ts,
                duration=track["duration"],
            )
            presence_visible = True
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
        time.sleep(2)
        old_config = dict(current_config)
        for _ in range(120):
            time.sleep(1)
            new_config = load_config()
            if new_config != old_config:
                current_config = new_config
                restart_rpc()
                print("[Settings] Config updated, RPC restarted.")
                break
    threading.Thread(target=_reload_after_delay, daemon=True).start()


def on_quit(icon, item):
    global rpc_running, settings_proc
    rpc_running = False
    if settings_proc and settings_proc.poll() is None:
        settings_proc.terminate()
        settings_proc = None
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
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Start RPC", lambda icon, item: start_rpc(),
                         visible=lambda item: not rpc_running),
        pystray.MenuItem("Stop RPC", lambda icon, item: stop_rpc(),
                         visible=lambda item: rpc_running),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )


def main():
    global tray_icon, current_config

    if '--settings' in sys.argv:
        from settings_ui import SettingsWindow
        SettingsWindow().show()
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

    if not is_startup_launch:
        open_settings()

    tray_icon.run()

    stop_rpc()
    if rpc_thread:
        rpc_thread.join(timeout=5)
    print("Goodbye.")


if __name__ == "__main__":
    main()
