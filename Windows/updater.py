# MIT License - Copyright (c) 2026 eripum9

import os
import ctypes
import hashlib
import re
import subprocess
import tempfile
import webbrowser
import requests
from config import APP_VERSION

REPO = "eripum9/Amazon-Music-Discord-RPC"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")


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


def _normalise_sha256(value):
    text = str(value or "").strip().lower()
    return text if SHA256_RE.fullmatch(text) else ""


def _extract_sha256(body, asset_name=""):
    if not body:
        return ""
    asset_name = str(asset_name or "").lower()
    found = []
    for raw in body.replace("\r", "\n").split("\n"):
        line = raw.strip()
        match = SHA256_RE.search(line)
        if not match:
            continue
        lowered = line.lower()
        score = 0
        if asset_name and asset_name in lowered:
            score += 2
        if "sha256" in lowered or "checksum" in lowered:
            score += 1
        found.append((score, match.group(0).lower()))
    if not found:
        return ""
    found.sort(key=lambda item: item[0], reverse=True)
    return found[0][1]


def _ps_literal(value):
    return "'" + str(value or "").replace("'", "''") + "'"


def _release_url(data):
    if data.get("html_url"):
        return data.get("html_url")
    if data.get("tag_name"):
        return f"https://github.com/{REPO}/releases/tag/{data.get('tag_name')}"
    return RELEASES_PAGE


def _setup_asset(data):
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if name.lower().endswith("_setup.exe") or name.lower().endswith("setup.exe"):
            return asset
    return {}


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file_sha256(path, expected_sha256):
    expected = _normalise_sha256(expected_sha256)
    if not expected:
        raise ValueError("Invalid SHA256 checksum")
    actual = file_sha256(path)
    if actual.lower() != expected:
        raise ValueError(f"Installer checksum mismatch. Expected {expected}, got {actual}.")
    return actual


def launch_installer(installer_path, wait_for_pid=None):
    if wait_for_pid:
        try:
            pid = int(wait_for_pid)
        except (TypeError, ValueError):
            pid = 0
        script = f"""
$installer = {_ps_literal(installer_path)}
$workingDir = {_ps_literal(os.path.dirname(installer_path))}
$pidToWait = {pid}
if ($pidToWait -gt 0) {{
    while (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue) {{
        Start-Sleep -Milliseconds 400
    }}
}}
Start-Process -FilePath $installer -WorkingDirectory $workingDir
"""
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-Command", script],
            creationflags=0x08000000,
        )
        return
    subprocess.Popen([installer_path], cwd=os.path.dirname(installer_path) or None, creationflags=0x08000000)


def check_for_update():
    try:
        resp = requests.get(RELEASES_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        latest_tag = data.get("tag_name", "")
        latest = _parse_version(latest_tag)
        current = _parse_version(APP_VERSION)
        if latest > current:
            asset = _setup_asset(data)
            download_url = asset.get("browser_download_url")
            body = data.get("body", "")
            return True, latest_tag.lstrip("v"), download_url, _format_changelog(body), _release_url(data), _extract_sha256(body, asset.get("name", ""))
    except Exception:
        pass
    return False, None, None, "", RELEASES_PAGE, ""


def prompt_for_update(latest_ver, download_url, changelog="", release_url=None, expected_sha256="", defer_until_exit=False):
    MB_YESNO = 0x04
    MB_ICONQUESTION = 0x20
    MB_ICONWARNING = 0x30
    MB_ICONERROR = 0x10
    MB_TOPMOST = 0x40000
    IDYES = 6
    release_url = release_url or RELEASES_PAGE
    expected_sha256 = _normalise_sha256(expected_sha256)
    message = f"A new version (v{latest_ver}) is available."
    if changelog:
        message += f"\n\nWhat's new:\n{changelog}"
    message += f"\n\nRelease page:\n{release_url}"
    if expected_sha256:
        message += "\n\nThe installer SHA256 hash will be verified after download."
    else:
        message += "\n\nNo SHA256 hash was found in the release notes. Review the release page before installing."
    message += "\n\nOpen the release page and download the update?"
    result = ctypes.windll.user32.MessageBoxW(
        0,
        message,
        "Amazon Music RPC — Update Available",
        MB_YESNO | (MB_ICONQUESTION if expected_sha256 else MB_ICONWARNING) | MB_TOPMOST,
    )
    if result != IDYES:
        return None
    try:
        webbrowser.open(release_url)
        installer_path = download_installer(download_url, expected_sha256)
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(
            0,
            f"Could not download or verify the update:\n\n{e}",
            "Amazon Music RPC — Update Failed",
            MB_ICONERROR | MB_TOPMOST,
        )
        return None
    verify_text = "SHA256 verified." if expected_sha256 else "No SHA256 hash was available in the release notes."
    run_result = ctypes.windll.user32.MessageBoxW(
        0,
        f"Installer downloaded.\n\n{verify_text}\n\nRun the installer now?",
        "Amazon Music RPC — Run Installer",
        MB_YESNO | (MB_ICONQUESTION if expected_sha256 else MB_ICONWARNING) | MB_TOPMOST,
    )
    if run_result != IDYES:
        return None
    launch_installer(installer_path, os.getpid() if defer_until_exit else None)
    return installer_path


def download_installer(url, expected_sha256=""):
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    tmp_dir = tempfile.gettempdir()
    installer_path = os.path.join(tmp_dir, "AmazonMusicRPC_Setup.exe")
    digest = hashlib.sha256()
    with open(installer_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                digest.update(chunk)
    expected = _normalise_sha256(expected_sha256)
    if expected and digest.hexdigest().lower() != expected:
        try:
            os.remove(installer_path)
        except OSError:
            pass
        raise ValueError(f"Installer checksum mismatch. Expected {expected}, got {digest.hexdigest()}.")
    return installer_path
