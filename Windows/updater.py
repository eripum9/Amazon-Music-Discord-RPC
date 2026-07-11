# MIT License - Copyright (c) 2026 eripum9

import ctypes
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlparse

import requests

from config import APP_VERSION
from launcher_diagnostics import pyinstaller_environment_keys


REPO = "eripum9/Amazon-Music-Discord-RPC"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
INSTALLER_NAME = "AmazonMusicRPC_Setup.exe"
CHECKSUM_NAME = f"{INSTALLER_NAME}.sha256"
UPDATE_HELPER_ARG = "--apply-downloaded-update"
MAX_INSTALLER_BYTES = 150 * 1024 * 1024
MAX_CHECKSUM_BYTES = 64 * 1024
MAX_RELEASE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")
REDIRECT_CODES = {301, 302, 303, 307, 308}
ASSET_REDIRECT_HOSTS = {"release-assets.githubusercontent.com", "objects.githubusercontent.com"}


@dataclass(frozen=True)
class UpdateInfo:
    available: bool = False
    version: str = ""
    installer_url: str = ""
    changelog: str = ""
    release_url: str = RELEASES_PAGE
    expected_sha256: str = ""
    installer_name: str = INSTALLER_NAME
    error: str = ""


@dataclass(frozen=True)
class DownloadedInstaller:
    path: str
    sha256: str
    size: int
    source_url: str


def _network_event(operation, status, detail=""):
    try:
        from network_audit import record_network_event
        record_network_event("github", operation, status, detail)
    except Exception:
        pass


def _parse_version(tag):
    tag = str(tag or "").lstrip("v")
    try:
        parts = tuple(int(x) for x in tag.split("."))
    except (ValueError, AttributeError):
        return (0,)
    return parts if len(parts) == 3 else (0,)


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
    return text[:597].rstrip() + "..." if len(text) > 600 else text


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
        score = (2 if asset_name and asset_name in lowered else 0) + (1 if "sha256" in lowered or "checksum" in lowered else 0)
        found.append((score, match.group(0).lower()))
    if not found:
        return ""
    found.sort(key=lambda item: item[0], reverse=True)
    return found[0][1]


def _clean_launch_env(base=None):
    env = dict(base or os.environ)
    for key in pyinstaller_environment_keys(env):
        env.pop(key, None)
    return env


def _https_parts(url):
    parsed = urlparse(str(url or ""))
    try:
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme.lower() != "https" or not parsed.hostname or port not in (None, 443) or parsed.username or parsed.password:
        return None
    return parsed


def _valid_release_api_url(url, redirected=False):
    parsed = _https_parts(url)
    return bool(parsed and parsed.hostname.lower() == "api.github.com" and parsed.path == f"/repos/{REPO}/releases/latest" and not parsed.query and not parsed.fragment)


def _valid_release_page_url(url):
    parsed = _https_parts(url)
    if not parsed or parsed.hostname.lower() != "github.com" or parsed.query or parsed.fragment:
        return False
    path = parsed.path.rstrip("/")
    base = f"/{REPO}/releases"
    return path == base or path.startswith(base + "/")


def _valid_asset_url(url, asset_name, redirected=False):
    parsed = _https_parts(url)
    if not parsed or parsed.fragment:
        return False
    host = parsed.hostname.lower()
    if redirected and host in ASSET_REDIRECT_HOSTS:
        return bool(parsed.path and parsed.path != "/")
    if host != "github.com" or parsed.query:
        return False
    prefix = f"/{REPO}/releases/download/"
    return parsed.path.startswith(prefix) and unquote(parsed.path.rsplit("/", 1)[-1]) == asset_name


def _response_length(response):
    try:
        return int((getattr(response, "headers", {}) or {}).get("Content-Length", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _request_following_redirects(url, validator, max_bytes, timeout, stream=False):
    current = str(url or "")
    for redirect_count in range(MAX_REDIRECTS + 1):
        if not validator(current, redirect_count > 0):
            raise ValueError("Download URL is outside the trusted GitHub release boundary")
        response = requests.get(current, timeout=timeout, stream=stream, allow_redirects=False)
        status = int(getattr(response, "status_code", 200) or 200)
        if status in REDIRECT_CODES:
            location = (getattr(response, "headers", {}) or {}).get("Location", "")
            try:
                response.close()
            except Exception:
                pass
            if not location or redirect_count >= MAX_REDIRECTS:
                raise ValueError("GitHub release download redirected too many times")
            current = urljoin(current, location)
            continue
        response.raise_for_status()
        if _response_length(response) > max_bytes:
            try:
                response.close()
            except Exception:
                pass
            raise ValueError("GitHub release response exceeds the allowed size")
        return response, current
    raise ValueError("GitHub release download redirected too many times")


def _release_url(data):
    candidate = str((data or {}).get("html_url", "") or "")
    if _valid_release_page_url(candidate):
        return candidate
    tag = str((data or {}).get("tag_name", "") or "")
    candidate = f"https://github.com/{REPO}/releases/tag/{tag}" if tag else ""
    return candidate if _valid_release_page_url(candidate) else RELEASES_PAGE


def _setup_asset(data):
    for asset in (data or {}).get("assets", []):
        if str(asset.get("name", "")) != INSTALLER_NAME:
            continue
        try:
            size = int(asset.get("size", 0) or 0)
        except (TypeError, ValueError):
            size = 0
        url = str(asset.get("browser_download_url", "") or "")
        if 0 < size <= MAX_INSTALLER_BYTES and _valid_asset_url(url, INSTALLER_NAME):
            return asset
    return {}


def _checksum_asset(data, installer_asset):
    if str((installer_asset or {}).get("name", "")) != INSTALLER_NAME:
        return {}
    for asset in (data or {}).get("assets", []):
        if str(asset.get("name", "")) != CHECKSUM_NAME:
            continue
        try:
            size = int(asset.get("size", 0) or 0)
        except (TypeError, ValueError):
            size = 0
        url = str(asset.get("browser_download_url", "") or "")
        if 0 < size <= MAX_CHECKSUM_BYTES and _valid_asset_url(url, CHECKSUM_NAME):
            return asset
    return {}


def _download_checksum_asset(asset, installer_name):
    url = str((asset or {}).get("browser_download_url", "") or "")
    response, _ = _request_following_redirects(url, lambda value, redirected: _valid_asset_url(value, CHECKSUM_NAME, redirected), MAX_CHECKSUM_BYTES, 10)
    raw = getattr(response, "content", None)
    if raw is None:
        raw = str(getattr(response, "text", "") or "").encode("utf-8")
    if len(raw) > MAX_CHECKSUM_BYTES:
        return ""
    return _extract_sha256(raw.decode("utf-8", errors="replace"), installer_name)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
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


def check_for_update():
    try:
        response, _ = _request_following_redirects(RELEASES_URL, _valid_release_api_url, MAX_RELEASE_BYTES, 10)
        raw = getattr(response, "content", b"")
        if raw and len(raw) > MAX_RELEASE_BYTES:
            raise ValueError("GitHub release metadata exceeds the allowed size")
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("GitHub release metadata is invalid")
        latest_tag = str(data.get("tag_name", "") or "")
        latest = _parse_version(latest_tag)
        if latest == (0,):
            raise ValueError("GitHub release version is invalid")
        if latest <= _parse_version(APP_VERSION):
            _network_event("update-check", "success", "up to date")
            return UpdateInfo(release_url=_release_url(data))
        asset = _setup_asset(data)
        body = str(data.get("body", "") or "")
        expected_sha256 = ""
        checksum_asset = _checksum_asset(data, asset)
        if checksum_asset:
            expected_sha256 = _download_checksum_asset(checksum_asset, INSTALLER_NAME)
        if not expected_sha256:
            expected_sha256 = _extract_sha256(body, INSTALLER_NAME)
        _network_event("update-check", "success", f"v{latest_tag.lstrip('v')} available")
        return UpdateInfo(
            available=True,
            version=latest_tag.lstrip("v"),
            installer_url=str(asset.get("browser_download_url", "") or ""),
            changelog=_format_changelog(body),
            release_url=_release_url(data),
            expected_sha256=expected_sha256,
        )
    except Exception as error:
        detail = f"{type(error).__name__}: {error}"
        _network_event("update-check", "error", detail)
        return UpdateInfo(error=detail)


def _download_path_is_trusted(path):
    candidate = os.path.realpath(os.path.abspath(str(path or "")))
    temp_root = os.path.realpath(tempfile.gettempdir())
    parent = os.path.dirname(candidate)
    return (
        os.path.basename(candidate).lower() == INSTALLER_NAME.lower()
        and os.path.dirname(parent).lower() == temp_root.lower()
        and os.path.basename(parent).startswith("AmazonMusicRPC_Update_")
    )


def download_installer(url, expected_sha256=""):
    expected = _normalise_sha256(expected_sha256)
    if not expected:
        raise ValueError("Installer SHA256 is required before download")
    response, final_url = _request_following_redirects(
        url,
        lambda value, redirected: _valid_asset_url(value, INSTALLER_NAME, redirected),
        MAX_INSTALLER_BYTES,
        (10, 60),
        stream=True,
    )
    temp_dir = tempfile.mkdtemp(prefix="AmazonMusicRPC_Update_")
    installer_path = os.path.join(temp_dir, INSTALLER_NAME)
    digest = hashlib.sha256()
    size = 0
    try:
        with open(installer_path, "wb") as handle:
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_INSTALLER_BYTES:
                    raise ValueError("Installer exceeds the 150 MiB download limit")
                handle.write(chunk)
                digest.update(chunk)
        actual = digest.hexdigest().lower()
        if actual != expected:
            raise ValueError(f"Installer checksum mismatch. Expected {expected}, got {actual}.")
        _network_event("installer-download", "success", f"{size} bytes")
        return DownloadedInstaller(installer_path, actual, size, final_url)
    except Exception as error:
        shutil.rmtree(temp_dir, ignore_errors=True)
        _network_event("installer-download", "error", type(error).__name__)
        raise
    finally:
        try:
            response.close()
        except Exception:
            pass


def _wait_for_process(pid, timeout_seconds=180):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return
    if pid <= 0 or os.name != "nt":
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x00100000, False, pid)
    if not handle:
        return
    try:
        kernel32.WaitForSingleObject(handle, int(timeout_seconds * 1000))
    finally:
        kernel32.CloseHandle(handle)


def _helper_command(downloaded, wait_for_pid):
    args = [UPDATE_HELPER_ARG, downloaded.path, downloaded.sha256, str(int(wait_for_pid or 0))]
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    entry = os.path.abspath(sys.argv[0])
    return [sys.executable, entry, *args]


def launch_installer(downloaded, wait_for_pid=None):
    if not isinstance(downloaded, DownloadedInstaller):
        raise TypeError("DownloadedInstaller is required")
    if not _download_path_is_trusted(downloaded.path):
        raise ValueError("Installer path is outside the trusted update directory")
    verify_file_sha256(downloaded.path, downloaded.sha256)
    launch_env = _clean_launch_env()
    if wait_for_pid:
        launch_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        subprocess.Popen(_helper_command(downloaded, wait_for_pid), creationflags=0x08000000 if os.name == "nt" else 0, env=launch_env)
        return
    subprocess.Popen([downloaded.path], cwd=os.path.dirname(downloaded.path), creationflags=0x08000000 if os.name == "nt" else 0, env=launch_env)


def run_update_helper(argv=None):
    args = list(argv or sys.argv)
    if UPDATE_HELPER_ARG not in args:
        return None
    index = args.index(UPDATE_HELPER_ARG)
    if len(args) <= index + 3:
        return 2
    path, expected, pid = args[index + 1:index + 4]
    if not _download_path_is_trusted(path):
        return 3
    expected = _normalise_sha256(expected)
    if not expected:
        return 4
    _wait_for_process(pid)
    try:
        actual = verify_file_sha256(path, expected)
        size = os.path.getsize(path)
        launch_installer(DownloadedInstaller(path, actual, size, "deferred-helper"))
        return 0
    except Exception:
        return 5


def prompt_for_update(update, defer_until_exit=False):
    if not isinstance(update, UpdateInfo) or not update.available:
        return None
    release_url = update.release_url if _valid_release_page_url(update.release_url) else RELEASES_PAGE
    expected_sha256 = _normalise_sha256(update.expected_sha256)
    message = f"A new version (v{update.version}) is available."
    if update.changelog:
        message += f"\n\nWhat's new:\n{update.changelog}"
    message += f"\n\nRelease page:\n{release_url}"
    if expected_sha256:
        message += "\n\nThe installer SHA256 hash will be verified after download."
    else:
        message += "\n\nNo SHA256 hash was found in the release assets or release notes. For safety, automatic download is disabled. Open the release page and review it manually."
    message += "\n\nOpen the release page?"
    result = ctypes.windll.user32.MessageBoxW(0, message, "Amazon Music RPC — Update Available", 0x04 | (0x20 if expected_sha256 else 0x30) | 0x40000)
    if result != 6:
        return None
    webbrowser.open(release_url)
    if not expected_sha256 or not update.installer_url:
        return None
    try:
        downloaded = download_installer(update.installer_url, expected_sha256)
    except Exception as error:
        ctypes.windll.user32.MessageBoxW(0, f"Could not download or verify the update:\n\n{error}", "Amazon Music RPC — Update Failed", 0x10 | 0x40000)
        return None
    run_result = ctypes.windll.user32.MessageBoxW(0, "Installer downloaded.\n\nSHA256 verified.\n\nRun the installer now?", "Amazon Music RPC — Run Installer", 0x04 | 0x20 | 0x40000)
    if run_result != 6:
        shutil.rmtree(os.path.dirname(downloaded.path), ignore_errors=True)
        return None
    launch_installer(downloaded, os.getpid() if defer_until_exit else None)
    return downloaded
