# Amazon Music RPC

Spotify-style Discord Rich Presence for Amazon Music on Windows, with a macOS beta prototype.

Show your Amazon Music songs, album art, pause state, and live timer on Discord.

![Windows stable](https://img.shields.io/badge/Windows-stable-blue)
![macOS beta](https://img.shields.io/badge/macOS-beta-orange)
![Python](https://img.shields.io/badge/python-3.11%2B-yellow)

[Download stable Windows release](https://github.com/eripum9/Amazon-Music-Discord-RPC/releases/latest) · [macOS beta guide](docs/macos-beta.md) · [View Demo](https://eripum9.github.io/Amazon-Music-Discord-RPC/#demo) · [Troubleshooting](https://eripum9.github.io/Amazon-Music-Discord-RPC/wiki/troubleshooting/) · [Privacy & Security](https://eripum9.github.io/Amazon-Music-Discord-RPC/wiki/privacy/)

- ✅ Shows current song, artist, album art, and timer on Discord
- ✅ Lets you display the artist, album, track, or app name after Discord's “Listening to” label
- ✅ Stable on Amazon Music for Windows; beta prototype for the official Amazon Music macOS app
- ✅ Includes Last.fm and ListenBrainz scrobbling
- ✅ Privacy mode and keyword filters
- ✅ No Python needed for the stable Windows installer

## Preview

### Discord Rich Presence

![Discord Rich Presence](Images/example1.png)

### Settings UI

![Settings UI](Images/example2.png)

## Features

- **Live track display** — title, artist, album name, and progress bar with elapsed/total time
- **Album art** — uses Amazon Music artwork first, with external artwork lookup as fallback
- **Fallback metadata** — uses Windows SMTC/optional notifications or the macOS Now Playing state when enhanced metadata is unavailable
- **Pause state** — keeps your presence visible when paused, with a frozen progress bar and pause icon
- **Last.fm scrobbling** — authenticate with one click and scrobble tracks automatically
- **ListenBrainz scrobbling** — paste your user token, validate it in Settings, and scrobble tracks
- **Listen button** — adds an Amazon Music link by default, with Deezer as an optional source
- **Privacy controls** — private session mode and keyword filters for tracks you do not want to share
- **Diagnostics window** — overview health checks, development tests, log history, and live console output in one resizable window
- **Report issue shortcut** — opens the GitHub issue page from Settings or Diagnostics
- **Auto-updater** — checks for updates on startup and via the Settings window
- **System tray app** — runs quietly in the background
- **Modern settings UI** — WebView2 on Windows and a native PySide menu-bar/settings prototype on macOS
- **Start at login** — optional Windows startup entry or per-user macOS LaunchAgent
- **Custom Discord Application ID** — use your own if you want custom assets
- **Network controls** — independently control automatic update checks, Deezer lookup, and iTunes artwork fallback
- **Request transparency** — review recent redacted outbound request status in Diagnostics

## How It Works

### Windows stable

Amazon Music metadata is read from the local Amazon Music desktop app when enhanced metadata is enabled. This provides the current title, artist, album, artwork, playback state, and progress timing for Discord Rich Presence.

**Enhanced metadata compatibility:** enhanced Amazon metadata is currently built and tested for the Microsoft Store version of Amazon Music. The website/desktop installer version of Amazon Music may not accept the metadata launch flag and can show errors such as `--remote-debugging-port` being unavailable. If that happens, install the Microsoft Store version for enhanced metadata, or disable enhanced metadata and use fallback mode.

If enhanced Amazon metadata is unavailable, the app falls back to Windows' System Media Transport Controls (SMTC). Notification fallback can optionally enrich that fallback path with artist and album metadata from Amazon Music's Windows notifications.

### macOS beta

The official Amazon Music app is available on macOS. The beta uses a validated Chromium DevTools target as its primary metadata source because it provides the richest title, artist, album, artwork, playback-state, link, and timing data. If Amazon Music is already running normally when enhanced metadata is first enabled, the user must explicitly approve a one-time restart so Amazon Music can reopen with its loopback debugging flag. The beta does not modify the Amazon Music bundle or its account files.

When DevTools metadata is disabled or unavailable, the beta falls back to the local macOS Now Playing state and accepts data only when the owning bundle identifier is `com.amazon.music`. The fallback is read-only and does not control playback. See [the macOS beta guide](docs/macos-beta.md) and [the integration research](docs/macos-integration-research.md).

## Security & Privacy

Amazon Music RPC is not affiliated with Amazon, Discord, Last.fm, ListenBrainz, Deezer, or Apple.

On Windows, enhanced metadata is optional for new installs. When enabled, the app launches or repairs the Microsoft Store version of Amazon Music with a local debugging interface so it can read the current Amazon Music page directly. This gives better title, album, artwork, pause state, and timing data than Windows fallback metadata. The debug port is picked randomly from a high local port range for each app session, kept in memory, and the app only attaches to Amazon Music targets on `music.amazon.*`.

On macOS, the beta accepts only the official `/Applications/Amazon Music.app` bundle with identifier `com.amazon.music` and Amazon's signing identity. It connects to a random port in `49152–60999` on `127.0.0.1`, verifies that every listener belongs to that installation, and evaluates only a bounded read-only transport-metadata script in an exact Amazon Music HTTPS page target. It does not request cookies, browser storage, network headers, account files, or debugger attachment. The CEF debugging endpoint itself has no application-level authentication, so another process running as the same local user could potentially connect while it is enabled; closing Amazon Music or relaunching it normally removes that endpoint.

Fallback-only mode is available in Settings by turning off **Enhanced Amazon metadata**. Windows then uses SMTC and optional notification enrichment; macOS uses the owner-validated Now Playing reader. Turning off the macOS checkbox stops Amazon Music RPC from connecting, but it cannot remove a listener already owned by the running Amazon app. Use **Disable listener & reopen normally** (with explicit confirmation), or close and reopen Amazon Music normally, to remove that listener.

Notification enrichment is off by default. If enabled, Windows may ask for notification access. The app reads notifications locally and only uses Amazon Music notifications to improve fallback metadata.

Private session mode clears Discord presence and can stop scrobbling while it is enabled. Keyword privacy rules can also block specific tracks from being shared.

Settings are stored in `%APPDATA%\AmazonMusicRPC\config.json` for installed builds, or the `Windows/` directory when running from source. Last.fm and ListenBrainz tokens are stored in Windows Credential Manager. If Credential Manager is unavailable, the app keeps a DPAPI-protected fallback file and verifies it before removing any previous copy. Diagnostics and log views redact known token values, and Settings includes a clear-token action.

The macOS beta stores non-secret settings and redacted diagnostics under `~/Library/Application Support/AmazonMusicRPC/`. Last.fm and ListenBrainz secrets are generic-password items in the login Keychain under service `io.github.eripum9.amazon-music-rpc`; they are not written to `config.json`. An optional start-at-login setting writes `~/Library/LaunchAgents/io.github.eripum9.amazon-music-rpc.plist`.

Normal macOS operation is not expected to require Accessibility, Automation, Screen Recording, Input Monitoring, Full Disk Access, Media & Apple Music, or Local Network permission. Keychain access, a background-item notice after enabling start at login, and access to a location explicitly selected in an import/export file picker are conditional. See [MacOS/PERMISSIONS.md](MacOS/PERMISSIONS.md) for the complete permission boundary.

Optional outbound services are individually configurable under **Network & Updates**. Automatic update checks contact GitHub, Deezer lookups can receive track and artist search text, and iTunes can receive the same search text when used as an artwork fallback. Diagnostics records a bounded, redacted history containing the service, operation, result, and time, but not the search query or token value. See [docs/network-endpoints.md](docs/network-endpoints.md) for the complete endpoint inventory.

### Data Flow

| Data | Used for | Sent where |
| --- | --- | --- |
| Song title, artist, album, playback time | Discord Rich Presence | Discord IPC |
| Album art URL | Discord Rich Presence artwork | Discord IPC |
| Amazon Music page metadata | Enhanced metadata | Local only |
| Windows SMTC metadata | Fallback metadata | Local only until shown in Discord |
| macOS Now Playing metadata | macOS fallback metadata | Local only until shown in Discord |
| Amazon Music notifications | Optional fallback enrichment | Local only until shown in Discord |
| Last.fm session key | Optional scrobbling | Last.fm |
| ListenBrainz token | Optional scrobbling | ListenBrainz |
| Track and artist search terms | Fallback artwork or track matching | Deezer or iTunes |
| GitHub release metadata | Update checks | GitHub |

### Fallback-Only Mode

To run without enhanced metadata:

1. Open **Settings** from the tray icon.
2. Turn off **Enhanced Amazon metadata**.
3. On Windows, leave **Notification enrichment** off if you also want to avoid Windows notification access. macOS does not use notification enrichment.
4. Turn off Last.fm and ListenBrainz if you do not want scrobbling.

### Uninstall

The installer removes the app startup entry, installed files, app config directory, logs, and Amazon Music metadata launcher shortcuts during uninstall. If you ran from source, delete the project folder, the `Windows/config.json` source config if present, and `%APPDATA%\AmazonMusicRPC` manually.

For the macOS beta, quit the menu-bar app, remove `Amazon Music RPC.app` from Applications, and remove `~/Library/Application Support/AmazonMusicRPC` if you also want to delete settings and logs. Remove `~/Library/LaunchAgents/io.github.eripum9.amazon-music-rpc.plist` if start at login was enabled. Scrobbler credentials can be removed from Keychain Access by deleting generic-password items for service `io.github.eripum9.amazon-music-rpc`.

For vulnerability reporting and supported version details, see [SECURITY.md](SECURITY.md).

For implementation boundaries and maintainability details, see [docs/architecture.md](docs/architecture.md) and [docs/threat-model.md](docs/threat-model.md).

## Installation

### Windows installer (recommended stable release)

Download `AmazonMusicRPC_Setup.exe` from [Releases](../../releases), run it, and you're done. The installer:

- Installs to `Program Files`
- Optionally creates a desktop shortcut
- Optionally adds a startup entry
- Shows up in **Settings > Apps** for clean uninstall

### Windows release verification

Releases include `AmazonMusicRPC_Setup.exe.sha256` beside the installer. The built-in updater opens the GitHub release page before running an installer and verifies the installer against that checksum asset. Older releases with a SHA256 value in their release notes remain supported.

To check a downloaded installer manually in PowerShell:

```powershell
Get-FileHash .\AmazonMusicRPC_Setup.exe -Algorithm SHA256
```

Compare the output with the value in `AmazonMusicRPC_Setup.exe.sha256` on the GitHub release page. If a release does not include a checksum, review the release page before installing.

Official installers are created only by the manually triggered **Build Draft Release** GitHub Actions workflow from the current `master` commit. The workflow runs tests, audits dependencies, builds from a hash-locked environment, creates provenance attestations, and leaves the release as a draft for maintainer review. Maintainer steps are documented in [docs/release-process.md](docs/release-process.md) and [docs/release-checklist.md](docs/release-checklist.md).

### macOS beta DMG

The macOS prototype produces `Amazon-Music-RPC.dmg` with `Amazon Music RPC.app` and an Applications shortcut. Mount the DMG, drag the app onto **Applications**, eject the DMG, and launch the installed copy. This is currently a beta development artifact, not the stable release linked above. This repository does not claim that a published macOS artifact has been Developer ID signed or notarized; verify the provenance of any DMG before opening it.

### Windows from source

```bash
git clone https://github.com/eripum9/Amazon-Music-Discord-RPC.git
cd Amazon-Music-Discord-RPC
pip install -r Windows/requirements.txt
python Windows/main.py
```

### macOS beta from source

```bash
git clone https://github.com/eripum9/Amazon-Music-Discord-RPC.git
cd Amazon-Music-Discord-RPC
git checkout beta/MacOS
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r MacOS/requirements.txt
python -m MacOS.main
```

The macOS runtime and automated tests are implemented, but live Discord Rich Presence and live Last.fm/ListenBrainz scrobbling still require manual verification. Discord was not installed on the first development machine, so passing mocked connectivity tests must not be treated as an end-to-end result.

## Requirements

- **Windows stable:** Windows 10/11 (64-bit) and Amazon Music for Windows. The Microsoft Store version is recommended for enhanced metadata.
- **macOS beta:** macOS 12 or later is the declared build target, the official Amazon Music app installed at `/Applications/Amazon Music.app`, and a build matching the Mac's processor architecture. Initial development was on Intel macOS 15.7.7; broader OS and Apple-silicon testing is still required.
- **Discord** desktop app (running)

No Python installation is needed when using the stable Windows installer.

## Platform Status

- Windows is the stable supported platform on `master`.
- macOS is an experimental beta prototype on `beta/MacOS`, enabled by Amazon's official macOS desktop app. It is not yet a stable release.
- Android support has been discontinued because the mobile integration was too unstable to support responsibly.
- Linux remains out of scope because it has no official Amazon Music desktop app surface suitable for this integration. Supported platform scope is tracked in [docs/platform-roadmap.md](docs/platform-roadmap.md).

## Building

Windows app source, dependencies, icons, and packaging files live in `Windows/`. The macOS beta lives in `MacOS/`; platform-neutral playback rules live in `Shared/` and must remain behaviorally identical across both builds.

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

### Build the macOS beta app and DMG

On macOS with Python 3.12 and Xcode command-line tools:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r MacOS/requirements-build.txt
MacOS/scripts/build_app.sh
MacOS/scripts/create_dmg.sh
```

Outputs are `MacOS/dist/Amazon Music RPC.app`, `MacOS/dist/Amazon-Music-RPC.dmg`, and its `.sha256` file. The build architecture follows the selected Python environment. Without a configured Developer ID identity the script creates an ad-hoc-signed local prototype; it is not a notarized distribution. See [MacOS/PERMISSIONS.md](MacOS/PERMISSIONS.md) for the separate release-signing workflow and limitations.

## Configuration

Settings are stored in `%APPDATA%\AmazonMusicRPC\config.json` (or the `Windows/` directory when running from source).

On macOS, non-secret settings are stored in `~/Library/Application Support/AmazonMusicRPC/config.json`, while scrobbler secrets use the login Keychain service described above.

On Windows, right-click the tray icon and select **Settings**. On macOS, use **Settings** from the menu-bar item.

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
