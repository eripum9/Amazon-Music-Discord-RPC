# Platform Roadmap

Amazon Music RPC should expand carefully. Windows stays stable, Android stays isolated until it is usable, and Linux/macOS work should not start until the technical risks are written down and accepted.

## Current Platform Status

| Platform | Status | Branch | Notes |
| --- | --- | --- | --- |
| Windows | Stable | `master` | Main supported release target. |
| Android | Beta | `beta/androidbuild` | Active test target with a fake Amazon test app and emulator path. |
| Linux | Research only | none | No implementation until Android beta is usable. |
| macOS | Research only | none | No implementation until Android beta is usable. |

## Android First Rule

Do not start Linux or macOS implementation work until Android has:

- Repeatable debug builds for the RPC app and fake Amazon test app
- Emulator test instructions that a second person can follow
- Working Discord presence with title, artist, album, duration, and elapsed time
- Pause, resume, seek, stop, and clear-presence behavior tested
- Known background-service limitations documented
- At least one real-device test or a clear reason why emulator-only testing is acceptable for that milestone

Android status and test steps are tracked in [docs/android-beta.md](android-beta.md).

## Linux Feasibility

### Metadata Source

The likely first metadata source is MPRIS over D-Bus. MPRIS is a standard media-player control and metadata API on Linux desktops:

https://www.freedesktop.org/wiki/Specifications/mpris-spec/

Useful MPRIS fields include playback status, metadata, track identity, album art URL, and position. The risk is that Amazon Music may not expose a native Linux desktop app with MPRIS support. Browser/PWA playback may expose media controls inconsistently depending on browser and desktop environment.

### Discord Presence

Discord Rich Presence is available through Discord developer tooling:

https://docs.discord.com/developers/platform/rich-presence

The practical Linux question is whether the installed Discord client exposes a compatible local IPC socket for the Python RPC library on the user's distribution and Discord build. This needs a small proof-of-concept before any UI or packaging work.

### Packaging

Linux packaging should be researched after the metadata and Discord IPC proof-of-concept. Candidate package formats:

- AppImage for portable GitHub release artifacts
- Flatpak for sandboxed desktop distribution
- Native packages only if there is clear demand

Flatpak documentation:

https://docs.flatpak.org/

### Linux Recommendation

Linux is feasible only if a proof-of-concept can read current Amazon Music metadata without browser-specific hacks and update Discord presence through the installed Discord client. Until then, treat Linux as research-only.

## macOS Feasibility

### Metadata Source

macOS needs separate validation. Possible metadata paths:

- Amazon Music app scripting or automation support if available
- macOS Now Playing or media remote metadata if accessible to third-party apps
- App-specific notification or accessibility fallback

Apple documents cross-process distributed notifications through `NSDistributedNotificationCenter`, but that does not guarantee Amazon Music publishes useful now-playing data:

https://developer.apple.com/documentation/foundation/nsdistributednotificationcenter

If the Amazon Music desktop app is Electron-based, Electron supports remote debugging command-line switches, but this must be tested with the actual macOS app before assuming parity with Windows:

https://www.electronjs.org/docs/latest/api/command-line-switches

### Discord Presence

Discord Rich Presence needs the installed macOS Discord client and a compatible local IPC path. This should be proven with a minimal script before porting the full Windows loop.

### Packaging

PyInstaller can package Python apps on macOS, but public distribution needs a macOS trust plan. Apple documents Developer ID distribution and notarization for apps outside the Mac App Store:

https://developer.apple.com/macos/distribution/

PyInstaller platform requirements:

https://pyinstaller.org/en/v6.11.0/requirements.html

### macOS Recommendation

macOS should not be started until there is a proof-of-concept for Amazon Music metadata and Discord IPC. Packaging should be treated as a trust task, not an afterthought, because unsigned macOS apps create avoidable user friction.

## First Experiments After Android

When Android reaches beta exit criteria, create separate research branches:

- `research/linux-metadata-rpc`
- `research/macos-metadata-rpc`

Each branch should prove only:

- Current track metadata can be read
- Playback state and time can be read or estimated
- Discord presence can be updated and cleared
- The app can exit without leaving stale presence

No settings UI, installer, updater, scrobbling, or artwork matching should be ported until those basics work.
