# Amazon Music RPC

Spotify-style Discord Rich Presence for Amazon Music on Windows.

Show your Amazon Music songs, album art, pause state, and live timer on Discord.

![Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-yellow)

[Download for Windows](https://github.com/eripum9/Amazon-Music-Discord-RPC/releases/latest) · [View Demo](https://eripum9.github.io/Amazon-Music-Discord-RPC/#demo) · [Troubleshooting](https://eripum9.github.io/Amazon-Music-Discord-RPC/wiki/troubleshooting/) · [Privacy & Security](https://eripum9.github.io/Amazon-Music-Discord-RPC/wiki/privacy/)

- ✅ Shows current song, artist, album art, and timer on Discord
- ✅ Lets you display the artist, album, track, or app name after Discord's “Listening to” label
- ✅ Works with Amazon Music for Windows
- ✅ Includes Last.fm and ListenBrainz scrobbling
- ✅ Privacy mode and keyword filters
- ✅ No Python needed — download the installer

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
- **Listen button** — adds an Amazon Music link by default, with Deezer as an optional source
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

**Enhanced metadata compatibility:** enhanced Amazon metadata is currently built and tested for the Microsoft Store version of Amazon Music. The website/desktop installer version of Amazon Music may not accept the metadata launch flag and can show errors such as `--remote-debugging-port` being unavailable. If that happens, install the Microsoft Store version for enhanced metadata, or disable enhanced metadata and use fallback mode.

If enhanced Amazon metadata is unavailable, the app falls back to Windows' System Media Transport Controls (SMTC). Notification fallback can optionally enrich that fallback path with artist and album metadata from Amazon Music's Windows notifications.

## Security & Privacy

Amazon Music RPC is not affiliated with Amazon, Discord, Last.fm, ListenBrainz, Deezer, or Apple.

Enhanced metadata is optional for new installs. When enabled, the app launches or repairs the Microsoft Store version of Amazon Music with a local debugging interface so it can read the current Amazon Music page directly. This gives better title, album, artwork, pause state, and timing data than Windows fallback metadata. The debug port is picked randomly from a high local port range for each app session, kept in memory, and the app only attaches to Amazon Music targets on `music.amazon.*`.

Fallback-only mode is available in Settings by turning off **Enhanced Amazon metadata**. In fallback-only mode, the app uses Windows media metadata and optional notification enrichment instead of the Amazon Music debug interface.

Notification enrichment is off by default. If enabled, Windows may ask for notification access. The app reads notifications locally and only uses Amazon Music notifications to improve fallback metadata.

Private session mode clears Discord presence and can stop scrobbling while it is enabled. Keyword privacy rules can also block specific tracks from being shared.

Settings are stored in `%APPDATA%\AmazonMusicRPC\config.json` for installed builds, or the `Windows/` directory when running from source. Last.fm and ListenBrainz tokens are stored in Windows Credential Manager. If Credential Manager is unavailable, the app keeps a DPAPI-protected fallback file and verifies it before removing any previous copy. Diagnostics and log views redact known token values, and Settings includes a clear-token action.

### Data Flow

| Data | Used for | Sent where |
| --- | --- | --- |
| Song title, artist, album, playback time | Discord Rich Presence | Discord IPC |
| Album art URL | Discord Rich Presence artwork | Discord IPC |
| Amazon Music page metadata | Enhanced metadata | Local only |
| Windows SMTC metadata | Fallback metadata | Local only until shown in Discord |
| Amazon Music notifications | Optional fallback enrichment | Local only until shown in Discord |
| Last.fm session key | Optional scrobbling | Last.fm |
| ListenBrainz token | Optional scrobbling | ListenBrainz |
| Track and artist search terms | Fallback artwork or track matching | Deezer or iTunes |
| GitHub release metadata | Update checks | GitHub |

### Fallback-Only Mode

To run without enhanced metadata:

1. Open **Settings** from the tray icon.
2. Turn off **Enhanced Amazon metadata**.
3. Leave **Notification enrichment** off if you also want to avoid Windows notification access.
4. Turn off Last.fm and ListenBrainz if you do not want scrobbling.

### Uninstall

The installer removes the app startup entry, installed files, app config directory, logs, and Amazon Music metadata launcher shortcuts during uninstall. If you ran from source, delete the project folder, the `Windows/config.json` source config if present, and `%APPDATA%\AmazonMusicRPC` manually.

For vulnerability reporting and supported version details, see [SECURITY.md](SECURITY.md).

## Installation

### Installer (recommended)

Download `AmazonMusicRPC_Setup.exe` from [Releases](../../releases), run it, and you're done. The installer:

- Installs to `Program Files`
- Optionally creates a desktop shortcut
- Optionally adds a startup entry
- Shows up in **Settings > Apps** for clean uninstall

### Release Verification

Releases include `AmazonMusicRPC_Setup.exe.sha256` beside the installer. The built-in updater opens the GitHub release page before running an installer and verifies the installer against that checksum asset. Older releases with a SHA256 value in their release notes remain supported.

To check a downloaded installer manually in PowerShell:

```powershell
Get-FileHash .\AmazonMusicRPC_Setup.exe -Algorithm SHA256
```

Compare the output with the value in `AmazonMusicRPC_Setup.exe.sha256` on the GitHub release page. If a release does not include a checksum, review the release page before installing.

Official installers are created only by the manually triggered **Build Draft Release** GitHub Actions workflow from the current `master` commit. The workflow runs tests, audits dependencies, builds from a hash-locked environment, creates provenance attestations, and leaves the release as a draft for maintainer review. Maintainer steps are documented in [docs/release-process.md](docs/release-process.md) and [docs/release-checklist.md](docs/release-checklist.md).

### From Source

```bash
git clone https://github.com/eripum9/Amazon-Music-Discord-RPC.git
cd Amazon-Music-Discord-RPC
pip install -r Windows/requirements.txt
python Windows/main.py
```

## Requirements

- **Windows 10/11** (64-bit)
- **Amazon Music for Windows**. The Microsoft Store version is recommended for enhanced metadata.
- **Discord** desktop app (running)

No Python installation needed if using the Installer.

## Platform Status

- Windows is the stable supported platform.
- Android support has been discontinued because the mobile integration was too unstable to support responsibly.
- Linux and macOS are out of scope because Amazon Music does not provide official desktop apps for those platforms. Supported platform scope is tracked in [docs/platform-roadmap.md](docs/platform-roadmap.md).

## Building

Windows app source, dependencies, icons, and packaging files live in `Windows/`.

The commands below create local development builds. They are not official release artifacts. Official releases must use the manual GitHub Actions workflow described in [docs/release-process.md](docs/release-process.md).

### Build the executable

```bash
pip install -r Windows/requirements-build.txt
pyinstaller Windows/AmazonMusicRPC.spec --noconfirm --workpath Windows/build --distpath Windows/dist
```

The output goes to `Windows/dist/AmazonMusicRPC.exe`.

### Build the installer

Requires [Inno Setup 6](https://jrsoftware.org/isdl.php).

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" Windows\installer.iss
```

Or if installed via winget:

```bash
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" Windows\installer.iss
```

Output: `Windows/installer_output/AmazonMusicRPC_Setup.exe`

You can also run the Windows build script:

```bat
Windows\build.bat
```

## Configuration

Settings are stored in `%APPDATA%\AmazonMusicRPC\config.json` (or the `Windows/` directory when running from source).

Right-click the tray icon and select **Settings** to open the configuration window.

Under **Startup & Presence**, the **Discord status display** setting controls what follows Discord's "Listening to" label. Choose Artist (the default), Album, Track, or Amazon Music. Album mode falls back to the artist when album metadata is unavailable.

## Support And Contributions

- Use the [troubleshooting guide](https://eripum9.github.io/Amazon-Music-Discord-RPC/wiki/troubleshooting/) for common setup issues.
- Use GitHub issues for bugs, enhanced metadata problems, and feature requests.
- Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## Credits

- [pypresence](https://github.com/qwertyquerty/pypresence) — Discord RPC library
- [winsdk](https://pypi.org/project/winsdk/) — Windows SDK bindings for SMTC and notifications
- [pywebview](https://pywebview.flowrl.com/) — Native webview for the settings UI
- [pylast](https://github.com/pylast/pylast) — Last.fm API library
- [Deezer API](https://developers.deezer.com/) — Album art search
- [iTunes Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/) — Album art fallback
- [ListenBrainz API](https://listenbrainz.readthedocs.io/) — ListenBrainz scrobbling

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
