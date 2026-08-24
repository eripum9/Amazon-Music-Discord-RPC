# MIT License - Copyright (c) 2026 eripum9

import plistlib
import runpy
import subprocess
from pathlib import Path


MACOS_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = MACOS_DIR.parent


def _read_plist(path):
    with path.open("rb") as plist_file:
        return plistlib.load(plist_file)


def test_info_plist_has_stable_identity_and_no_unneeded_privacy_prompts():
    payload = _read_plist(MACOS_DIR / "Info.plist")

    assert payload["CFBundleDisplayName"] == "Amazon Music RPC"
    assert payload["CFBundleIdentifier"] == "io.github.eripum9.amazon-music-rpc"
    assert payload["LSMinimumSystemVersion"] == "12.0"
    assert payload["LSUIElement"] is True
    assert payload["CFBundleIconFile"] == "AmazonMusicRPC.icns"
    assert "NSAppleEventsUsageDescription" not in payload
    assert "NSLocalNetworkUsageDescription" not in payload


def test_release_entitlements_do_not_weaken_hardened_runtime():
    assert _read_plist(MACOS_DIR / "entitlements.plist") == {}


def test_packaging_scripts_are_valid_bash():
    for script_name in ("generate_icon.sh", "build_app.sh", "create_dmg.sh"):
        script = MACOS_DIR / "scripts" / script_name
        completed = subprocess.run(
            ["/bin/bash", "-n", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr


def test_dmg_layout_contains_applications_drop_target(tmp_path):
    app_path = tmp_path / "Amazon Music RPC.app"
    resources = app_path / "Contents" / "Resources"
    resources.mkdir(parents=True)
    icon_path = resources / "AmazonMusicRPC.icns"
    icon_path.write_bytes(b"test icon")
    info_path = app_path / "Contents" / "Info.plist"
    with info_path.open("wb") as plist_file:
        plistlib.dump({"CFBundleIconFile": icon_path.name}, plist_file)

    settings = runpy.run_path(
        str(MACOS_DIR / "dmg_settings.py"),
        init_globals={"defines": {"app": str(app_path)}},
    )

    assert settings["files"] == [str(app_path)]
    assert settings["symlinks"] == {"Applications": "/Applications"}
    assert settings["icon_locations"] == {
        "Amazon Music RPC.app": (150, 190),
        "Applications": (450, 190),
    }
    assert settings["background"] == "builtin-arrow"
    assert "hide_extensions" not in settings


def test_spec_packages_the_shared_application_icon_and_macos_probe():
    spec = (MACOS_DIR / "AmazonMusicRPC.spec").read_text(encoding="utf-8")

    assert 'PROJECT_DIR / "Windows" / "icon.png"' in spec
    assert 'MACOS_DIR / "amazon_music_now_playing.js"' in spec
    assert 'collect_submodules("Shared")' in spec
    assert 'collect_data_files("Shared")' in spec
    assert 'str(PROJECT_DIR / "Windows")' in spec
    assert '"Windows.discord_rpc"' in spec
    assert 'bundle_identifier="io.github.eripum9.amazon-music-rpc"' in spec
    assert 'MACOS_DIR / "main.py"' in spec


def test_dmg_script_writes_checksum_after_optional_notarization():
    script = (MACOS_DIR / "scripts" / "create_dmg.sh").read_text(encoding="utf-8")

    assert 'CHECKSUM_PATH="${OUTPUT_PATH}.sha256"' in script
    assert script.index("stapler validate") < script.index("CHECKSUM_VALUE=")
    assert "/usr/bin/shasum -a 256" in script


def test_runtime_and_build_requirements_are_pinned():
    runtime = (MACOS_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines()
    build = (MACOS_DIR / "requirements-build.txt").read_text(encoding="utf-8").splitlines()

    assert runtime == [
        "pypresence==4.6.2",
        "requests==2.34.2",
        "Pillow==12.3.0",
        "PySide6-Essentials==6.9.3",
        "pylast==7.1.0",
        "liblistenbrainz==0.7.0",
    ]
    assert build == [
        "-r requirements.txt",
        "PyInstaller==6.21.0",
        "dmgbuild==1.6.7",
    ]
