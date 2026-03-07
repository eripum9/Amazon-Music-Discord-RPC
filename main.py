import time
import sys
import os
import subprocess
import threading

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

# --- Global state ---
rpc_thread = None
rpc_running = False
tray_icon = None
current_config = {}


def rpc_loop():
    """Main RPC polling loop — runs in a background thread."""
    global rpc_running

    config = current_config
    if config.get("use_custom_client_id") and config.get("discord_client_id"):
        client_id = config["discord_client_id"]
    else:
        client_id = DEFAULT_CLIENT_ID
    poll_interval = config.get("poll_interval_seconds", 5)
    show_paused = config.get("show_when_paused", False)

    rpc = DiscordRPC(client_id)
    last_track_key = None
    last_art_url = None
    last_album_name = None
    last_start_ts = None
    last_status = None
    presence_visible = False

    print(f"[RPC] Started. Polling every {poll_interval}s | Show paused: {show_paused}")

    while rpc_running:
        try:
            track = get_track_sync()

            if track is None or not track["title"]:
                if presence_visible:
                    rpc.clear()
                    presence_visible = False
                last_track_key = None
                last_art_url = None
                last_album_name = None
                last_start_ts = None
                last_status = None
                time.sleep(poll_interval)
                continue

            is_paused = track["status"] == "paused"
            track_key = f"{track['title']}|{track['artist']}"

            # Fetch album art on track change
            if track_key != last_track_key:
                last_art_url, last_album_name = get_album_art(track["title"], track["artist"])
                if not last_album_name and track["album"]:
                    last_album_name = track["album"]
                if last_art_url:
                    print(f"[Art] Found: '{last_album_name}' for '{track['title']}'")
                else:
                    print(f"[Art] No album art found for '{track['title']}'")

            # Always recalculate start_ts from SMTC position so resume is accurate
            if not is_paused and track["position"] is not None:
                last_start_ts = int(time.time() - track["position"])
            elif track_key != last_track_key and track["position"] is not None:
                last_start_ts = int(time.time() - track["position"])

            last_track_key = track_key

            # Handle paused state
            if is_paused and not show_paused:
                if presence_visible:
                    rpc.clear()
                    presence_visible = False
                last_status = "paused"
                time.sleep(poll_interval)
                continue

            # Update presence
            rpc.update(
                title=track["title"],
                artist=track["artist"],
                album_art_url=last_art_url,
                album_name=last_album_name,
                start_ts=last_start_ts if not is_paused else None,
                duration=track["duration"] if not is_paused else 0,
                is_paused=is_paused,
                position=track["position"] if is_paused else None,
            )
            presence_visible = True
            last_status = track["status"]
            time.sleep(poll_interval)

        except Exception as e:
            print(f"[RPC] Loop error: {e}")
            time.sleep(poll_interval)

    # Cleanup on stop
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
    """Open settings UI as a subprocess (pywebview requires main-thread control)."""
    global current_config
    if getattr(sys, 'frozen', False):
        subprocess.Popen([sys.executable, '--settings'], creationflags=0x08000000)
    else:
        subprocess.Popen(
            [sys.executable, os.path.join(SCRIPT_DIR, 'settings_ui.py')],
            creationflags=0x08000000
        )
    # Reload config after a delay to pick up changes
    def _reload_after_delay():
        time.sleep(2)
        # Keep checking for config changes
        old_config = dict(current_config)
        for _ in range(120):  # Check for up to 2 minutes
            time.sleep(1)
            new_config = load_config()
            if new_config != old_config:
                current_config = new_config
                restart_rpc()
                print("[Settings] Config updated, RPC restarted.")
                break
    threading.Thread(target=_reload_after_delay, daemon=True).start()


def on_quit(icon, item):
    global rpc_running
    rpc_running = False
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

    # Handle --settings flag (for frozen exe to open settings UI)
    if '--settings' in sys.argv:
        from settings_ui import SettingsWindow
        SettingsWindow().show()
        return

    is_startup_launch = '--startup' in sys.argv

    current_config = load_config()

    # Load tray icon
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

    # Auto-start RPC
    start_rpc()

    # Show settings on normal launch (not startup)
    if not is_startup_launch:
        open_settings()

    # This blocks — runs the tray icon event loop
    tray_icon.run()

    # After tray exits, clean up
    stop_rpc()
    if rpc_thread:
        rpc_thread.join(timeout=5)
    print("Goodbye.")


if __name__ == "__main__":
    main()
