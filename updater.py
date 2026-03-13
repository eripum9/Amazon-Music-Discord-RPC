# MIT License - Copyright (c) 2026 eripum9

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
        resp = requests.get(RELEASES_URL, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        latest_tag = data.get("tag_name", "")
        latest = _parse_version(latest_tag)
        current = _parse_version(APP_VERSION)
        if latest > current:
            return True, latest_tag.lstrip("v"), RELEASES_PAGE
    except Exception:
        pass
    return False, None, None
