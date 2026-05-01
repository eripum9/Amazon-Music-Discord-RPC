# MIT License - Copyright (c) 2026 eripum9

import os
import ctypes
import subprocess
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


def _format_changelog(body):
    if not body:
        return ""
    lines = []
    body_lines = body.replace("\r", "\n").split("\n")
    start_at = 0
    for index, raw in enumerate(body_lines):
        heading = raw.strip().strip("#").strip().lower()
        if heading in {"what's new", "whats new", "new features", "improvements"}:
            start_at = index + 1
            break
    skip_headings = {
        "changelog",
        "changes",
        "release notes",
        "what's changed",
        "whats changed",
        "new features",
        "improvements",
        "reliability",
        "settings ui",
        "diagnostics",
        "privacy",
    }
    stop_headings = {"installation", "requirements"}
    for raw in body_lines[start_at:]:
        line = raw.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith(("<!--", "<details", "</details", "<summary", "</summary")):
            continue
        line = line.strip("#").strip()
        if line.lower() in stop_headings:
            break
        if line.lower() in skip_headings:
            continue
        if line.startswith(("-", "*", "•")):
            line = "- " + line.lstrip("-*• ").strip()
        if line:
            lines.append(line)
        if len(lines) >= 5:
            break
    text = "\n".join(lines)
    if len(text) > 600:
        text = text[:597].rstrip() + "..."
    return text


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
            return True, latest_tag.lstrip("v"), download_url, _format_changelog(data.get("body", ""))
    except Exception:
        pass
    return False, None, None, ""


def prompt_for_update(latest_ver, download_url, changelog=""):
    MB_YESNO = 0x04
    MB_ICONQUESTION = 0x20
    MB_TOPMOST = 0x40000
    IDYES = 6
    message = f"A new version (v{latest_ver}) is available."
    if changelog:
        message += f"\n\nWhat's new:\n{changelog}"
    message += "\n\nWould you like to update now?"
    result = ctypes.windll.user32.MessageBoxW(
        0,
        message,
        "Amazon Music RPC — Update Available",
        MB_YESNO | MB_ICONQUESTION | MB_TOPMOST,
    )
    if result != IDYES:
        return None
    installer_path = download_installer(download_url)
    subprocess.Popen([installer_path], creationflags=0x08000000)
    return installer_path


def download_installer(url):
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    tmp_dir = tempfile.gettempdir()
    installer_path = os.path.join(tmp_dir, "AmazonMusicRPC_Setup.exe")
    with open(installer_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
    return installer_path
