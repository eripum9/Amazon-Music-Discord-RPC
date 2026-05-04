# Amazon Music RPC

Discord Rich Presence for Amazon Music on Windows. Shows what you're listening to — including track name, artist, album art, and a live timer — directly on your Discord profile.

![Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-yellow)

## Preview

### Discord Rich Presence

![Discord Rich Presence](Images/example1.png)

### Settings UI

![Settings UI](Images/example2.png)

## Features

- **Live track display** — title, artist, album name, and progress bar with elapsed/total time
- **Album art** — fetched automatically from Deezer (primary) and iTunes (fallback)
- **Notification enrichment** — reads full artist and album info from Windows notifications for more accurate metadata than SMTC alone
- **Pause state** — keeps your presence visible when paused, with a frozen progress bar and pause icon
- **Last.fm scrobbling** — authenticate with one click and scrobble tracks automatically
- **ListenBrainz scrobbling** — paste your user token, validate it in Settings, and scrobble tracks
- **Listen on Deezer button** — adds a clickable link on your Discord presence (toggleable)
- **Privacy controls** — private session mode and keyword filters for tracks you do not want to share
- **Diagnostics window** — overview health checks, development tests, log history, and live console output in one resizable window
- **Report issue shortcut** — opens the GitHub issue page from Settings or Diagnostics
- **Auto-updater** — checks for updates on startup and via the Settings window
- **System tray app** — runs quietly in the background
- **Modern settings UI** — dark theme with WebView2 (Edge), Windows 11 style, with saved window sizing
- **Start on Windows startup** — optional, launches minimized to tray
- **Custom Discord Application ID** — use your own if you want custom assets

## How It Works

Amazon Music exposes currently playing media through Windows' System Media Transport Controls (SMTC). This app reads that data and sends it to Discord via Rich Presence IPC.

Optionally, notification enrichment can be enabled to read full track metadata (artist + album) from Amazon Music's Windows notifications, which provides richer data than SMTC alone. This requires Amazon Music notifications to be enabled and the app to be minimized.

## Installation

### Installer (recommended)

Download `AmazonMusicRPC_Setup.exe` from [Releases](../../releases), run it, and you're done. The installer:

- Installs to `Program Files`
- Optionally creates a desktop shortcut
- Optionally adds a startup entry
- Shows up in **Settings > Apps** for clean uninstall

### From Source

```bash
git clone https://github.com/eripum9/Amazon-Music-Discord-RPC.git
cd Amazon-Music-Discord-RPC
pip install -r requirements.txt
python main.py
```

## Requirements

- **Windows 10/11** (64-bit)
- **Amazon Music** desktop app
- **Discord** desktop app (running)

No Python installation needed if using the Installer.

## Quick Start

1. Download and run `AmazonMusicRPC_Setup.exe` from [Releases](../../releases).
2. Launch Amazon Music and start playing a track.
3. Open Discord — your currently playing track will appear on your profile within a few seconds.
4. Right-click the tray icon to access Settings, enable scrobbling, or toggle a private session.

## Configuration

Settings are stored in `%APPDATA%\AmazonMusicRPC\config.json` (or the project directory when running from source).

Right-click the tray icon and select **Settings** to open the configuration window.

## Troubleshooting

| Problem | What to check |
|---|---|
| Discord presence does not appear | Make sure Discord is running and that **Settings > Activity Privacy > Display current activity** is enabled in Discord. |
| Track info is missing artist or album | Enable **Notification enrichment** in Settings and ensure Amazon Music notifications are turned on in Windows settings. |
| Album art is not showing | Deezer and iTunes are used for art lookups — check your internet connection. Some niche tracks may not have art. |
| Amazon Music is not detected | Make sure the Amazon Music desktop app (not the browser player) is running and currently playing a track. |
| Last.fm / ListenBrainz not scrobbling | Open Settings, verify your credentials, and confirm the scrobbler shows **Active** in the Diagnostics window. |
| App does not start at login | Open Settings and toggle **Start on Windows Startup** off and back on to re-register the startup entry. |

Open the **Diagnostics** window (right-click tray icon → Diagnostics) for live status, log history, and detailed health checks.

## Known Limitations

- Windows 10/11 only — SMTC and Windows notification APIs are not available on other platforms.
- Notification enrichment requires Amazon Music to send toast notifications; this only works when the app is minimized to the taskbar.
- Album art and Deezer listen links rely on third-party APIs and may not be available for all tracks.
- The Discord presence button ("Listen on Deezer") links to the Deezer match, which may occasionally be a different version of the track.

## Architecture Overview

```
Amazon Music (SMTC) ──► media_reader.py ──┐
                                           ├─► main.py (RPC loop) ──► discord_rpc.py ──► Discord
Windows Notifications ──► notification_reader.py ──┘         │
                                                              ├─► lastfm.py / listenbrainz_scrobbler.py
Deezer / iTunes APIs ──► album_art.py ──────────────────────┘

config.py       — loads/saves settings from %APPDATA%\AmazonMusicRPC\config.json
privacy.py      — keyword and private-session filtering helpers
updater.py      — GitHub release checks and installer download
settings_ui.py  — WebView2-backed settings window (runs as a subprocess)
diagnostics_ui.py — health-check and log viewer window (runs as a subprocess)
track_picker.py — interactive dialog for resolving missing track metadata
self_tests.py   — runtime diagnostic self-tests (invoked from the Diagnostics window)
```

## Developer Setup

```bash
git clone https://github.com/eripum9/Amazon-Music-Discord-RPC.git
cd Amazon-Music-Discord-RPC
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

**Python 3.11 or newer is required** (tested on Python 3.11 and 3.12).

### Running tests

```bash
pip install pytest
pytest tests/
```

### Building the executable

```bash
pip install pyinstaller
pyinstaller AmazonMusicRPC.spec --noconfirm
```

Output: `dist/AmazonMusicRPC.exe`.

### Building the installer

Requires [Inno Setup 6](https://jrsoftware.org/isdl.php).

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

Or if installed via winget:

```bash
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

Output: `installer_output/AmazonMusicRPC_Setup.exe`

## Credits

- [pypresence](https://github.com/qwertyquerty/pypresence) — Discord RPC library
- [winsdk](https://pypi.org/project/winsdk/) — Windows SDK bindings for SMTC and notifications
- [pywebview](https://pywebview.flowrl.com/) — Native webview for the settings UI
- [pylast](https://github.com/pylast/pylast) — Last.fm API library
- [Deezer API](https://developers.deezer.com/) — Album art search
- [iTunes Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/) — Album art fallback
- [ListenBrainz API](https://listenbrainz.readthedocs.io/) — ListenBrainz scrobbling

