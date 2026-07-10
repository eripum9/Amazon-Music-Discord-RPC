import hashlib

import pytest

import updater


def test_version_changelog_and_hash_parsing(tmp_path):
    payload = b"amazon music rpc installer test"
    digest = hashlib.sha256(payload).hexdigest()
    installer = tmp_path / "AmazonMusicRPC_Setup.exe"
    installer.write_bytes(payload)
    body = f"Intro\n\n## What's New\n\n- Added diagnostics\n- Fixed privacy\n\n## Installation\n\nAmazonMusicRPC_Setup.exe SHA256: {digest}"
    assert updater._parse_version("v2.1.0") == (2, 1, 0)
    assert updater._parse_version("bad") == (0,)
    assert "Added diagnostics" in updater._format_changelog(body)
    assert "Installation" not in updater._format_changelog(body)
    assert updater._extract_sha256(body, "AmazonMusicRPC_Setup.exe") == digest
    assert updater.verify_file_sha256(installer, digest) == digest
    with pytest.raises(ValueError):
        updater.verify_file_sha256(installer, "0" * 64)


def test_updater_cleans_pyinstaller_environment():
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
    assert updater._ps_literal("a'b") == "'a''b'"


def test_update_prefers_installer_checksum_asset(monkeypatch):
    digest = "a" * 64
    notes_digest = "b" * 64
    release_url = updater.RELEASES_URL
    checksum_url = "https://example.test/AmazonMusicRPC_Setup.exe.sha256"
    release = {
        "tag_name": "v4.0.2",
        "html_url": "https://example.test/release",
        "body": f"AmazonMusicRPC_Setup.exe SHA256: {notes_digest}",
        "assets": [
            {"name": "AmazonMusicRPC_Setup.exe", "browser_download_url": "https://example.test/setup.exe"},
            {"name": "AmazonMusicRPC_Setup.exe.sha256", "browser_download_url": checksum_url},
        ],
    }

    class FakeResponse:
        def __init__(self, data=None, text=""):
            self._data = data
            self.text = text

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    def fake_get(url, **kwargs):
        if url == release_url:
            return FakeResponse(data=release)
        if url == checksum_url:
            return FakeResponse(text=f"{digest}  AmazonMusicRPC_Setup.exe\n")
        raise AssertionError(url)

    monkeypatch.setattr(updater.requests, "get", fake_get)
    monkeypatch.setattr(updater, "APP_VERSION", "4.0.1")
    result = updater.check_for_update()
    assert result[0] is True
    assert result[-1] == digest


def test_update_falls_back_to_release_notes_hash(monkeypatch):
    digest = "c" * 64
    release = {
        "tag_name": "v4.0.2",
        "body": f"AmazonMusicRPC_Setup.exe SHA256: {digest}",
        "assets": [
            {"name": "AmazonMusicRPC_Setup.exe", "browser_download_url": "https://example.test/setup.exe"},
        ],
    }

    class FakeResponse:
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return release

    monkeypatch.setattr(updater.requests, "get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(updater, "APP_VERSION", "4.0.1")
    assert updater.check_for_update()[-1] == digest
