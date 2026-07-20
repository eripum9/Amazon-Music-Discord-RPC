# MIT License - Copyright (c) 2026 eripum9

import hashlib
import os
from types import SimpleNamespace

import pytest

from MacOS import updater


class Response:
    def __init__(self, *, data=None, content=b"", status=200, headers=None, chunks=None):
        self._data = data
        self.content = content
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks if chunks is not None else [content]
        self.closed = False

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def close(self):
        self.closed = True

    def iter_content(self, chunk_size):
        yield from self._chunks


def asset_url(name):
    return f"https://github.com/{updater.REPO}/releases/download/v5.1.0/{name}"


def release_data(checksum):
    return {
        "tag_name": "v5.1.0",
        "html_url": f"https://github.com/{updater.REPO}/releases/tag/v5.1.0",
        "body": "## What's new\n- macOS beta",
        "assets": [
            {
                "name": updater.DMG_NAME,
                "size": 12345,
                "browser_download_url": asset_url(updater.DMG_NAME),
            },
            {
                "name": updater.CHECKSUM_NAME,
                "size": 90,
                "browser_download_url": asset_url(updater.CHECKSUM_NAME),
            },
        ],
        "checksum": checksum,
    }


def test_check_for_update_requires_exact_dmg_and_reads_checksum(monkeypatch):
    checksum = "a" * 64
    responses = [
        Response(data=release_data(checksum), content=b"{}"),
        Response(content=f"{checksum}  {updater.DMG_NAME}\n".encode()),
    ]

    def request_get(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(updater, "_network_event", lambda *args: None)
    update = updater.check_for_update(request_get=request_get)
    assert update.available is True
    assert update.version == "5.1.0"
    assert update.dmg_url.endswith(updater.DMG_NAME)
    assert update.expected_sha256 == checksum
    assert "macOS beta" in update.changelog


def test_check_for_update_reports_up_to_date(monkeypatch):
    response = Response(
        data={
            "tag_name": "v5.0.0",
            "html_url": f"https://github.com/{updater.REPO}/releases/tag/v5.0.0",
            "assets": [],
        },
        content=b"{}",
    )
    monkeypatch.setattr(updater, "_network_event", lambda *args: None)
    update = updater.check_for_update(request_get=lambda *args, **kwargs: response)
    assert update.available is False
    assert update.error == ""


def test_check_for_update_rejects_untrusted_release_metadata(monkeypatch):
    monkeypatch.setattr(updater, "_network_event", lambda *args: None)
    update = updater.check_for_update(
        request_get=lambda *args, **kwargs: Response(data=[], content=b"[]")
    )
    assert update.available is False
    assert "invalid" in update.error.lower()


def test_download_dmg_verifies_sha256_and_opens_verified_path(monkeypatch):
    payload = b"verified dmg bytes"
    checksum = hashlib.sha256(payload).hexdigest()
    update = updater.UpdateInfo(
        available=True,
        version="5.1.0",
        dmg_url=asset_url(updater.DMG_NAME),
        expected_sha256=checksum,
    )
    response = Response(chunks=[payload[:5], payload[5:]])
    monkeypatch.setattr(updater, "_network_event", lambda *args: None)
    downloaded = updater.download_dmg(
        update, request_get=lambda *args, **kwargs: response
    )
    assert downloaded.sha256 == checksum
    calls = []
    updater.open_dmg(
        downloaded,
        runner=lambda command, **kwargs: calls.append((command, kwargs)) or SimpleNamespace(pid=1),
    )
    assert calls[0][0] == ["/usr/bin/open", os.path.realpath(downloaded.path)]


def test_download_dmg_rejects_missing_checksum():
    update = updater.UpdateInfo(
        available=True,
        version="5.1.0",
        dmg_url=asset_url(updater.DMG_NAME),
    )
    with pytest.raises(ValueError, match="SHA256"):
        updater.download_dmg(update)


def test_asset_validation_rejects_lookalike_hosts_and_names():
    assert updater._valid_asset(asset_url(updater.DMG_NAME), updater.DMG_NAME)
    assert not updater._valid_asset(
        f"https://github.example/{updater.REPO}/releases/download/v5.1.0/{updater.DMG_NAME}",
        updater.DMG_NAME,
    )
    assert not updater._valid_asset(
        asset_url("Not-The-App.dmg"), updater.DMG_NAME
    )
