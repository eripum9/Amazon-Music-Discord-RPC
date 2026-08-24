# -*- mode: python ; coding: utf-8 -*-

import os
import plistlib
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


MACOS_DIR = Path(SPECPATH).resolve()
PROJECT_DIR = MACOS_DIR.parent
APP_NAME = "Amazon Music RPC"
APP_VERSION = os.environ.get("APP_VERSION", "0.1.0")
APP_BUILD = os.environ.get("APP_BUILD", "1")
CODESIGN_IDENTITY = os.environ.get("MACOS_CODESIGN_IDENTITY") or None
ICON_PATH = MACOS_DIR / "build" / "assets" / "AmazonMusicRPC.icns"
ENTITLEMENTS_PATH = MACOS_DIR / "entitlements.plist"
SHARED_HIDDEN_IMPORTS = collect_submodules("Shared")
SHARED_DATA = collect_data_files("Shared")

with (MACOS_DIR / "Info.plist").open("rb") as plist_file:
    info_plist = plistlib.load(plist_file)

info_plist.update(
    {
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_BUILD,
        "LSMinimumSystemVersion": os.environ.get("MACOSX_DEPLOYMENT_TARGET", "12.0"),
    }
)

analysis = Analysis(
    [str(MACOS_DIR / "main.py")],
    pathex=[str(PROJECT_DIR), str(MACOS_DIR), str(PROJECT_DIR / "Windows")],
    binaries=[],
    datas=[
        (str(PROJECT_DIR / "Windows" / "icon.png"), "."),
        (str(MACOS_DIR / "amazon_music_now_playing.js"), "MacOS"),
        *SHARED_DATA,
    ],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtNetwork",
        "PySide6.QtWidgets",
        "Windows.album_art",
        "Windows.discord_rpc",
        "Windows.lastfm",
        "Windows.listenbrainz_scrobbler",
        "Windows.network_audit",
        "Windows.task_supervisor",
        "liblistenbrainz",
        "pylast",
        "pypresence",
        "pypresence.types",
        "requests",
        *SHARED_HIDDEN_IMPORTS,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "clr",
        "msvcrt",
        "pythonnet",
        "winreg",
        "winsdk",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=CODESIGN_IDENTITY,
    entitlements_file=str(ENTITLEMENTS_PATH),
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

app = BUNDLE(
    collection,
    name=f"{APP_NAME}.app",
    icon=str(ICON_PATH),
    bundle_identifier="io.github.eripum9.amazon-music-rpc",
    version=APP_VERSION,
    info_plist=info_plist,
)
