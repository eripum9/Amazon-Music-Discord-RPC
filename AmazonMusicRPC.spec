import os

block_cipher = None
project_dir = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(project_dir, 'main.py')],
    pathex=[project_dir],
    binaries=[],
    datas=[
        (os.path.join(project_dir, 'icon.png'), '.'),
    ],
    hiddenimports=[
        'pystray._win32',
        'winsdk',
        'winsdk.windows.media.control',
        'webview',
        'clr',
        'pythonnet',
        'track_picker',
        'updater',
        'lastfm',
        'pylast',
        'listenbrainz_scrobbler',
        'liblistenbrainz',
        'notification_reader',
        'winsdk.windows.ui.notifications',
        'winsdk.windows.ui.notifications.management',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AmazonMusicRPC',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_dir, 'icon.ico'),
)
