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
