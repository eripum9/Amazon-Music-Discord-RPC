# MIT License - Copyright (c) 2026 eripum9

"""Checksum-gated GitHub DMG updater for the macOS build."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlparse

import requests

from . import config


REPO = "eripum9/Amazon-Music-Discord-RPC"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
DMG_NAME = "Amazon-Music-RPC.dmg"
CHECKSUM_NAME = f"{DMG_NAME}.sha256"
MAX_DMG_BYTES = 500 * 1024 * 1024
MAX_CHECKSUM_BYTES = 64 * 1024
MAX_RELEASE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
REDIRECT_CODES = {301, 302, 303, 307, 308}
ASSET_REDIRECT_HOSTS = {
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
    "github-releases.githubusercontent.com",
}
SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")


@dataclass(frozen=True, slots=True)
class UpdateInfo:
    available: bool = False
    version: str = ""
    dmg_url: str = ""
    expected_sha256: str = ""
    changelog: str = ""
    release_url: str = RELEASES_PAGE
    error: str = ""


@dataclass(frozen=True, slots=True)
class DownloadedDMG:
    path: str
    sha256: str
    size: int
    source_url: str


def _network_event(operation, status, detail=""):
    try:
        from Windows.network_audit import record_network_event

        record_network_event("github", operation, status, detail, config.CONFIG_DIR)
    except Exception:
        pass


def _version(value):
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", str(value or "").strip())
    return tuple(int(part) for part in match.groups()) if match else (0, 0, 0)


def _https_url(value):
    try:
        parsed = urlparse(str(value or ""))
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or port not in (None, 443)
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        return None
    return parsed


def _valid_release_api(url, redirected=False):
    parsed = _https_url(url)
    return bool(
        not redirected
        and parsed
        and parsed.hostname.lower() == "api.github.com"
        and parsed.path == f"/repos/{REPO}/releases/latest"
        and not parsed.query
    )


def _valid_release_page(url):
    parsed = _https_url(url)
    if not parsed or parsed.hostname.lower() != "github.com" or parsed.query:
        return False
    base = f"/{REPO}/releases"
    return parsed.path.rstrip("/") == base or parsed.path.startswith(base + "/")


def _valid_asset(url, name, redirected=False):
    parsed = _https_url(url)
    if not parsed:
        return False
    host = parsed.hostname.lower()
    if redirected:
        return host in ASSET_REDIRECT_HOSTS and bool(parsed.path and parsed.path != "/")
    prefix = f"/{REPO}/releases/download/"
    return bool(
        host == "github.com"
        and not parsed.query
        and parsed.path.startswith(prefix)
        and unquote(parsed.path.rsplit("/", 1)[-1]) == name
    )


def _bounded_request(url, validator, max_bytes, *, stream=False, request_get=requests.get):
    current = str(url or "")
    for redirect_count in range(MAX_REDIRECTS + 1):
        if not validator(current, redirect_count > 0):
            raise ValueError("URL is outside the trusted GitHub release boundary")
        response = request_get(
            current,
            timeout=(10, 60) if stream else 10,
            stream=stream,
            allow_redirects=False,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "AmazonMusicRPC-macOS"},
        )
        status = int(getattr(response, "status_code", 200) or 200)
        if status in REDIRECT_CODES:
            location = (getattr(response, "headers", {}) or {}).get("Location", "")
            response.close()
            if not location or redirect_count >= MAX_REDIRECTS:
                raise ValueError("GitHub release download redirected too many times")
            current = urljoin(current, location)
            continue
        response.raise_for_status()
        try:
            length = int((getattr(response, "headers", {}) or {}).get("Content-Length", 0) or 0)
        except (TypeError, ValueError):
            length = 0
        if length > max_bytes:
            response.close()
            raise ValueError("GitHub response exceeds the allowed size")
        return response, current
    raise ValueError("GitHub release download redirected too many times")


def _asset(data, name, maximum):
    for asset in (data or {}).get("assets", []):
        if not isinstance(asset, dict) or asset.get("name") != name:
            continue
        try:
            size = int(asset.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        url = str(asset.get("browser_download_url") or "")
        if 0 < size <= maximum and _valid_asset(url, name):
            return asset
    return {}


def _checksum_from_text(value, dmg_name=DMG_NAME):
    candidates = []
    for line in str(value or "").splitlines():
        match = SHA256_RE.search(line)
        if match:
            score = int(dmg_name.casefold() in line.casefold()) + int("sha256" in line.casefold())
            candidates.append((score, match.group(0).lower()))
    return max(candidates, default=(0, ""))[1]


def _release_page(data):
    candidate = str((data or {}).get("html_url") or "")
    return candidate if _valid_release_page(candidate) else RELEASES_PAGE


def _changelog(body):
    lines = []
    for raw in str(body or "").replace("\r", "\n").split("\n"):
        line = raw.strip().strip("#").strip()
        if not line or line.startswith(("<!--", "<details", "</details")):
            continue
        if line.startswith(("-", "*", "•")):
            line = "- " + line.lstrip("-*• ")
        lines.append(line)
        if len(lines) == 6:
            break
    return "\n".join(lines)[:800]


def check_for_update(*, request_get=requests.get):
    try:
        response, _ = _bounded_request(
            RELEASES_URL,
            _valid_release_api,
            MAX_RELEASE_BYTES,
            request_get=request_get,
        )
        raw = getattr(response, "content", b"") or b""
        if len(raw) > MAX_RELEASE_BYTES:
            raise ValueError("GitHub release metadata exceeds the allowed size")
        data = response.json()
        response.close()
        if not isinstance(data, dict) or _version(data.get("tag_name")) == (0, 0, 0):
            raise ValueError("GitHub release metadata is invalid")
        if _version(data.get("tag_name")) <= _version(config.APP_VERSION):
            _network_event("update-check", "success", "up to date")
            return UpdateInfo(release_url=_release_page(data))
        dmg = _asset(data, DMG_NAME, MAX_DMG_BYTES)
        checksum = _asset(data, CHECKSUM_NAME, MAX_CHECKSUM_BYTES)
        expected = ""
        if dmg and checksum:
            checksum_response, _ = _bounded_request(
                checksum["browser_download_url"],
                lambda value, redirected: _valid_asset(value, CHECKSUM_NAME, redirected),
                MAX_CHECKSUM_BYTES,
                request_get=request_get,
            )
            checksum_bytes = getattr(checksum_response, "content", b"") or b""
            checksum_response.close()
            if len(checksum_bytes) <= MAX_CHECKSUM_BYTES:
                expected = _checksum_from_text(checksum_bytes.decode("utf-8", errors="replace"))
        if not expected:
            expected = _checksum_from_text(data.get("body"))
        version = str(data.get("tag_name") or "").lstrip("v")
        _network_event("update-check", "success", f"v{version} available")
        return UpdateInfo(
            available=True,
            version=version,
            dmg_url=str(dmg.get("browser_download_url") or ""),
            expected_sha256=expected,
            changelog=_changelog(data.get("body")),
            release_url=_release_page(data),
        )
    except Exception as error:
        detail = f"{type(error).__name__}: {error}"
        _network_event("update-check", "error", detail)
        return UpdateInfo(error=detail)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_dmg(update, *, request_get=requests.get):
    if not isinstance(update, UpdateInfo) or not update.available:
        raise ValueError("An available macOS update is required")
    expected = str(update.expected_sha256 or "").lower()
    if not SHA256_RE.fullmatch(expected):
        raise ValueError("A valid SHA256 checksum is required for automatic download")
    if not _valid_asset(update.dmg_url, DMG_NAME):
        raise ValueError("The DMG URL is not a trusted release asset")
    response, source_url = _bounded_request(
        update.dmg_url,
        lambda value, redirected: _valid_asset(value, DMG_NAME, redirected),
        MAX_DMG_BYTES,
        stream=True,
        request_get=request_get,
    )
    directory = tempfile.mkdtemp(prefix="AmazonMusicRPC_Update_")
    path = os.path.join(directory, DMG_NAME)
    size = 0
    digest = hashlib.sha256()
    try:
        with open(path, "wb") as handle:
            os.chmod(path, 0o600)
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_DMG_BYTES:
                    raise ValueError("DMG exceeds the download size limit")
                handle.write(chunk)
                digest.update(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            raise ValueError(f"DMG checksum mismatch. Expected {expected}, got {actual}.")
        _network_event("dmg-download", "success", f"{size} bytes")
        return DownloadedDMG(path, actual, size, source_url)
    except Exception as error:
        shutil.rmtree(directory, ignore_errors=True)
        _network_event("dmg-download", "error", type(error).__name__)
        raise
    finally:
        response.close()


def open_dmg(downloaded, *, runner=subprocess.Popen):
    if not isinstance(downloaded, DownloadedDMG):
        raise TypeError("DownloadedDMG is required")
    real_path = os.path.realpath(downloaded.path)
    temporary_root = os.path.realpath(tempfile.gettempdir())
    parent = os.path.dirname(real_path)
    if (
        os.path.basename(real_path) != DMG_NAME
        or os.path.dirname(parent) != temporary_root
        or not os.path.basename(parent).startswith("AmazonMusicRPC_Update_")
        or file_sha256(real_path) != downloaded.sha256
    ):
        raise ValueError("DMG is outside the verified update directory")
    return runner(["/usr/bin/open", real_path], close_fds=True)


def download_and_open_dmg(update, *, request_get=requests.get, runner=subprocess.Popen):
    downloaded = download_dmg(update, request_get=request_get)
    open_dmg(downloaded, runner=runner)
    return downloaded
