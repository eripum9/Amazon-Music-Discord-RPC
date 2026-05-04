# Contributing to Amazon Music RPC

Thanks for your interest in contributing! Here's everything you need to get started.

## Development setup

**Requirements:** Python 3.11+, Windows 10/11 (the app uses Windows-only APIs).

```bash
git clone https://github.com/eripum9/Amazon-Music-Discord-RPC.git
cd Amazon-Music-Discord-RPC
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pytest flake8
```

Run the app from source:

```bash
python main.py
```

## Running tests

```bash
pytest tests/ -v
```

Unit tests cover pure Python logic (version parsing, changelog formatting, title cleanup, privacy matching, config load/save) and run on any platform.

## Linting

```bash
# Hard errors (syntax errors, undefined names)
flake8 . --select=E9,F63,F7,F82 --show-source

# Style warnings (max line length 120)
flake8 . --max-line-length=120
```

## Building the executable

```bash
pip install pyinstaller
pyinstaller AmazonMusicRPC.spec --noconfirm
```

Output: `dist/AmazonMusicRPC.exe`

## Building the installer

Requires [Inno Setup 6](https://jrsoftware.org/isdl.php).

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
# or, if installed via winget:
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

Output: `installer_output/AmazonMusicRPC_Setup.exe`

## Module responsibilities

| File | Responsibility |
|---|---|
| `main.py` | App entry point, tray icon, RPC loop orchestration |
| `config.py` | Load/save config from `%APPDATA%\AmazonMusicRPC\config.json` |
| `privacy.py` | Privacy keyword and private-session filtering helpers |
| `media_reader.py` | Read currently playing track from SMTC |
| `notification_reader.py` | Read track metadata from Windows notifications |
| `album_art.py` | Fetch album art and track links from Deezer/iTunes |
| `discord_rpc.py` | Manage the Discord Rich Presence IPC connection |
| `lastfm.py` | Last.fm scrobbling |
| `listenbrainz_scrobbler.py` | ListenBrainz scrobbling |
| `updater.py` | Check for and download GitHub releases |
| `settings_ui.py` | Settings window (WebView2, runs as subprocess) |
| `diagnostics_ui.py` | Diagnostics and log viewer window (runs as subprocess) |
| `track_picker.py` | Interactive dialog for resolving missing track metadata |
| `self_tests.py` | Runtime diagnostic self-tests (invoked from Diagnostics window) |

## Pull requests

Please open a PR against the `master` branch. Fill in the PR template, make sure `pytest tests/` passes, and describe how you tested the change on Windows.

## Reporting issues

Use the [GitHub issue tracker](https://github.com/eripum9/Amazon-Music-Discord-RPC/issues). For bugs, attach the relevant log from the Diagnostics window (right-click tray icon → Diagnostics → Log History).
