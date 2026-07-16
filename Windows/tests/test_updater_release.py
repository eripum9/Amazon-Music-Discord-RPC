# MIT License - Copyright (c) 2026 eripum9

import hashlib
import os

import pytest

import updater


class FakeResponse:
    def __init__(self, data=None, content=b"", status_code=200, headers=None, chunks=None):
        self._data = data
        self.content = content
        self.text = content.decode("utf-8", errors="replace")
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks

    def raise_for_status(self):
        if self.status_code >= 400:
            raise updater.requests.HTTPError(str(self.status_code))

    def json(self):
        return self._data

    def iter_content(self, chunk_size=65536):
        if self._chunks is not None:
            yield from self._chunks
        elif self.content:
            yield self.content

    def close(self):
        return None


def release_asset_url(name):
    return f"https://github.com/{updater.REPO}/releases/download/v4.0.2/{name}"


def test_version_changelog_and_hash_parsing(tmp_path):
    payload = b"amazon music rpc installer test"
    digest = hashlib.sha256(payload).hexdigest()
    installer = tmp_path / updater.INSTALLER_NAME
    installer.write_bytes(payload)
    body = f"Intro\n\n## What's New\n\n- Added diagnostics\n- Fixed privacy\n\n## Installation\n\n{updater.INSTALLER_NAME} SHA256: {digest}"
    assert updater._parse_version("v2.1.0") == (2, 1, 0)
    assert updater._parse_version("bad") == (0,)
    assert updater._parse_version("1.2") == (0,)
    assert "Added diagnostics" in updater._format_changelog(body)
    assert "Installation" not in updater._format_changelog(body)
    assert updater._extract_sha256(body, updater.INSTALLER_NAME) == digest
    assert updater.verify_file_sha256(installer, digest) == digest
    with pytest.raises(ValueError):
        updater.verify_file_sha256(installer, "0" * 64)


def test_updater_cleans_pyinstaller_environment_and_uses_native_helper():
    cleaned = updater._clean_launch_env(
        {
            "_PYI_APPLICATION_HOME_DIR": r"C:\Users\erikp\AppData\Local\Temp\_MEI166362",
            "_PYI_PARENT_PROCESS_LEVEL": "1",
            "_MEIPASS2": r"C:\Users\erikp\AppData\Local\Temp\_MEI166362",
            "PYINSTALLER_RESET_ENVIRONMENT": "1",
            "SAFE_KEY": "value",
        }
    )
    assert cleaned == {"SAFE_KEY": "value"}
    assert "_helper_command" in updater.launch_installer.__code__.co_names
    assert not hasattr(updater, "_powershell_executable")
    assert updater.run_update_helper(["app", "--other"]) is None


def test_update_prefers_trusted_installer_checksum_asset(monkeypatch):
    digest = "a" * 64
    notes_digest = "b" * 64
    installer_url = release_asset_url(updater.INSTALLER_NAME)
    checksum_url = release_asset_url(updater.CHECKSUM_NAME)
    release = {
        "tag_name": "v4.0.2",
        "html_url": f"https://github.com/{updater.REPO}/releases/tag/v4.0.2",
        "body": f"{updater.INSTALLER_NAME} SHA256: {notes_digest}",
        "assets": [
            {"name": updater.INSTALLER_NAME, "browser_download_url": installer_url, "size": 1024},
            {"name": updater.CHECKSUM_NAME, "browser_download_url": checksum_url, "size": 96},
        ],
    }

    def fake_get(url, **kwargs):
        if url == updater.RELEASES_URL:
            return FakeResponse(data=release)
        if url == checksum_url:
            return FakeResponse(content=f"{digest}  {updater.INSTALLER_NAME}\n".encode())
        raise AssertionError(url)

    monkeypatch.setattr(updater.requests, "get", fake_get)
    monkeypatch.setattr(updater, "APP_VERSION", "4.0.1")
    monkeypatch.setattr(updater, "_network_event", lambda *args: None)
    result = updater.check_for_update()
    assert isinstance(result, updater.UpdateInfo)
    assert result.available is True
    assert result.installer_url == installer_url
    assert result.expected_sha256 == digest


def test_update_falls_back_to_release_notes_hash(monkeypatch):
    digest = "c" * 64
    installer_url = release_asset_url(updater.INSTALLER_NAME)
    release = {
        "tag_name": "v4.0.2",
        "body": f"{updater.INSTALLER_NAME} SHA256: {digest}",
        "assets": [{"name": updater.INSTALLER_NAME, "browser_download_url": installer_url, "size": 1024}],
    }
    monkeypatch.setattr(updater.requests, "get", lambda *args, **kwargs: FakeResponse(data=release))
    monkeypatch.setattr(updater, "APP_VERSION", "4.0.1")
    monkeypatch.setattr(updater, "_network_event", lambda *args: None)
    assert updater.check_for_update().expected_sha256 == digest


def test_update_rejects_untrusted_assets_and_redirects(monkeypatch):
    release = {
        "tag_name": "v4.0.2",
        "assets": [{"name": updater.INSTALLER_NAME, "browser_download_url": "https://example.test/setup.exe", "size": 1024}],
    }
    monkeypatch.setattr(updater.requests, "get", lambda *args, **kwargs: FakeResponse(data=release))
    monkeypatch.setattr(updater, "APP_VERSION", "4.0.1")
    monkeypatch.setattr(updater, "_network_event", lambda *args: None)
    result = updater.check_for_update()
    assert result.available is True
    assert result.installer_url == ""
    with pytest.raises(ValueError):
        updater.download_installer("https://example.test/setup.exe", "a" * 64)


def test_download_enforces_redirect_and_size_boundaries(monkeypatch):
    payload = b"trusted installer"
    digest = hashlib.sha256(payload).hexdigest()
    initial = release_asset_url(updater.INSTALLER_NAME)
    redirected = "https://release-assets.githubusercontent.com/github-production-release-asset/test"
    responses = {
        initial: FakeResponse(status_code=302, headers={"Location": redirected}),
        redirected: FakeResponse(content=payload),
    }
    monkeypatch.setattr(updater.requests, "get", lambda url, **kwargs: responses[url])
    monkeypatch.setattr(updater, "_network_event", lambda *args: None)
    downloaded = updater.download_installer(initial, digest)
    try:
        assert isinstance(downloaded, updater.DownloadedInstaller)
        assert downloaded.size == len(payload)
        assert updater._download_path_is_trusted(downloaded.path)
    finally:
        os.remove(downloaded.path)
        os.rmdir(os.path.dirname(downloaded.path))

    oversized = FakeResponse(headers={"Content-Length": str(updater.MAX_INSTALLER_BYTES + 1)})
    monkeypatch.setattr(updater.requests, "get", lambda *args, **kwargs: oversized)
    with pytest.raises(ValueError):
        updater.download_installer(initial, digest)
