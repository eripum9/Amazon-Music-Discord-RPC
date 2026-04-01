# MIT License - Copyright (c) 2026 eripum9

import os
import tempfile
import requests
from config import APP_VERSION

REPO = "eripum9/Amazon-Music-Discord-RPC"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"


def _parse_version(tag):
    tag = tag.lstrip("v")
    try:
        return tuple(int(x) for x in tag.split("."))
    except (ValueError, AttributeError):
        return (0,)


def check_for_update():
    try:
        resp = requests.get(RELEASES_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        latest_tag = data.get("tag_name", "")
        latest = _parse_version(latest_tag)
        current = _parse_version(APP_VERSION)
        if latest > current:
            download_url = None
            for asset in data.get("assets", []):
                if asset["name"].lower().endswith("_setup.exe") or asset["name"].lower().endswith("setup.exe"):
                    download_url = asset["browser_download_url"]
                    break
            return True, latest_tag.lstrip("v"), download_url
    except Exception:
        pass
    return False, None, None


def download_installer(url):
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    tmp_dir = tempfile.gettempdir()
    installer_path = os.path.join(tmp_dir, "AmazonMusicRPC_Setup.exe")
    with open(installer_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
    return installer_path
