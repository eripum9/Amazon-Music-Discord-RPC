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
- **Album art** — uses Amazon Music artwork first, with external artwork lookup as fallback
- **Fallback metadata** — uses SMTC and Windows notifications only when enhanced Amazon metadata is unavailable
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

Amazon Music metadata is read from the local Amazon Music desktop app when enhanced metadata is enabled. This provides the current title, artist, album, artwork, playback state, and progress timing for Discord Rich Presence.

If enhanced Amazon metadata is unavailable, the app falls back to Windows' System Media Transport Controls (SMTC). Notification fallback can optionally enrich that fallback path with artist and album metadata from Amazon Music's Windows notifications.

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

## Building

### Build the executable

```bash
pip install pyinstaller
pyinstaller AmazonMusicRPC.spec --noconfirm
```

The output goes to `dist/AmazonMusicRPC.exe`.

### Build the installer

Requires [Inno Setup 6](https://jrsoftware.org/isdl.php).

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

Or if installed via winget:

```bash
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

Output: `installer_output/AmazonMusicRPC_Setup.exe`

## Configuration

Settings are stored in `%APPDATA%\AmazonMusicRPC\config.json` (or the project directory when running from source).

Right-click the tray icon and select **Settings** to open the configuration window.

## Credits

- [pypresence](https://github.com/qwertyquerty/pypresence) — Discord RPC library
- [winsdk](https://pypi.org/project/winsdk/) — Windows SDK bindings for SMTC and notifications
- [pywebview](https://pywebview.flowrl.com/) — Native webview for the settings UI
- [pylast](https://github.com/pylast/pylast) — Last.fm API library
- [Deezer API](https://developers.deezer.com/) — Album art search
- [iTunes Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/) — Album art fallback
- [ListenBrainz API](https://listenbrainz.readthedocs.io/) — ListenBrainz scrobbling
