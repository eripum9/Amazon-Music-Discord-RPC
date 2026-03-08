# MIT License - Copyright (c) 2026 eripum9

import json
import os
import sys
import winreg

APP_NAME = "AmazonMusicRPC"
DEFAULT_CLIENT_ID = "1479925587697995857"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", ""), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

if not os.environ.get("APPDATA") or getattr(sys, "frozen", False) is False:
    CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
    CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "discord_client_id": DEFAULT_CLIENT_ID,
    "use_custom_client_id": False,
    "start_on_startup": False,
    "start_minimized": True,
    "track_mappings": {},
}

STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            saved = json.load(f)
        config = {**DEFAULTS, **saved}
    else:
        config = dict(DEFAULTS)
    return config


def save_config(config):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)


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


def set_startup(enable):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE)
        if enable:
            exe = get_exe_path()
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe}" --startup')
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except OSError as e:
        print(f"[Config] Registry error: {e}")
