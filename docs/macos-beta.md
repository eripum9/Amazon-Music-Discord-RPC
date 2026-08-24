# macOS Beta

macOS is an active beta development target maintained on `master`. Windows remains the only published stable release, and the release workflow does not include a macOS artifact yet. The macOS build is a menu-bar app for Amazon's official `/Applications/Amazon Music.app`; it is not a browser wrapper and does not alter the Amazon application bundle.

## Implemented Beta Features

- Discord Rich Presence payloads with title, artist, album, artwork, playback state, timer, status-display choice, and an optional song link
- Enhanced Amazon metadata through a validated local Chromium DevTools target
- Read-only macOS Now Playing fallback when DevTools is disabled or unavailable
- Last.fm and ListenBrainz configuration, now-playing submission, and the shared scrobble threshold
- Private session, keyword privacy filters, game-mode process filters, remembered track corrections, and custom album art
- Configurable Amazon/Deezer song links and optional Deezer/iTunes artwork lookup
- Menu-bar controls, Settings, Diagnostics, redacted network history, update checks, and optional start at login
- A PyInstaller `.app` and DMG containing the app plus an Applications shortcut

These code paths have automated coverage, but the first development Mac did not have Discord installed. Live Discord IPC and live Last.fm/ListenBrainz submissions have not yet been verified end to end. Visual behavior, reconnect handling, Keychain prompts, login items, and a clean-machine drag install also require manual testing before the beta can be promoted.

## Metadata Order

1. **Validated DevTools metadata** is primary when enhanced metadata is enabled. It can provide the richest Amazon-native title, artist, album, artwork, playback state, position, duration, and link data.
2. **macOS Now Playing** is the fallback. It accepts an active session only when the owner is exactly `com.amazon.music`, is read-only, and does not send playback commands.
3. **Optional Deezer/iTunes lookup** can fill artwork or other missing public metadata according to the user's network settings.

The official Amazon Music app does not expose DevTools during a normal launch. If it is already running normally when enhanced metadata is enabled, Amazon Music RPC reports that a restart is required. The user must explicitly choose **Restart Amazon Music with DevTools** once for that running session. The app then terminates only processes whose executable resolves inside the validated Amazon installation and launches its exact executable with:

```text
--remote-debugging-address=127.0.0.1
--remote-debugging-port=<random private high port>
```

No shortcut, preference, browser profile, login data, or file inside Amazon Music is changed. If Amazon Music is later started normally before Amazon Music RPC, another explicit restart can be required. Closing Amazon Music or relaunching it normally removes the debugging listener. Turning off **Enable enhanced metadata** stops RPC connections but does not change the already-running Amazon process; use the separately confirmed **Disable listener & reopen normally** action when the listener itself must be removed.

## DevTools Security Boundary

DevTools can inspect an authenticated renderer, so the beta treats it as a narrow privileged local interface:

- The Amazon app must resolve to `/Applications/Amazon Music.app`, declare bundle identifier `com.amazon.music` and executable `Amazon Music`, and match Amazon's Team ID/signing authority.
- The selected port is random, kept in memory, and restricted to `49152–60999` on `127.0.0.1`.
- Every listener PID is resolved to an executable inside that validated Amazon-identity bundle. Listener identity is checked before target discovery and rechecked before evaluation.
- HTTP discovery is limited to `/json`, `/json/list`, and `/json/version`, with bounded responses.
- The accepted target must be a page on an exact supported `https://music.amazon.<region>` host or Amazon's exact legacy `https://www.amazon.<region>/morpho/webapp` path. Credentials, unexpected ports, lookalike domains, fragments, and untrusted WebSocket paths are rejected.
- The WebSocket must return to loopback on the same selected port and match the discovered page target ID. Handshakes, frames, and JSON results are size bounded.
- The client sends a single bounded `Runtime.evaluate` script that reads visible transport metadata. It does not call the CDP cookie, storage, request-header, network-body, download, or debugger APIs.
- Returned links and artwork are independently allowlisted and sanitized before use. Failed launches are stopped, and process termination is limited to revalidated Amazon executable paths.

The CEF listener itself has no Amazon Music RPC authentication. Any other process running locally as the same user may be able to discover and connect to it while enhanced metadata is active. Loopback prevents remote-network access but does not protect against already-running local software. Use fallback-only mode, close Amazon Music, or relaunch Amazon Music normally when this local exposure is not acceptable.

The implementation never reads Amazon Music cookies, LevelDB/IndexedDB, browser storage, offline state, logs, or account files. `/tmp/AmazonMusic.ipc` and Amazon's Qt single-instance sockets are explicitly rejected integration surfaces.

## macOS Permissions

Normal presence and metadata operation is not expected to request any of these macOS privacy permissions:

- Accessibility or Input Monitoring
- Automation/Apple Events
- Screen Recording
- Full Disk Access
- Media & Apple Music
- Camera, Microphone, Contacts, or Location
- Local Network

The Now Playing fallback invokes `/usr/bin/osascript` to read a local framework object; it does not automate Amazon Music or System Events. Discord uses a local Unix-domain IPC socket, and DevTools uses loopback rather than a broadcast-capable local network.

Conditional system interaction is limited to:

- **Keychain:** macOS may ask to unlock the login Keychain or approve access when Last.fm or ListenBrainz credentials are saved or read.
- **Start at login:** enabling it writes a per-user LaunchAgent. macOS may show a Background Items notification, and the user can disable it in **System Settings > General > Login Items**.
- **File pickers:** settings import/export and diagnostics export access only the file or destination the user selects. macOS may show a Files and Folders prompt if the chosen location is TCC-protected.
- **Outbound Internet:** enabled update checks, artwork providers, and scrobblers make HTTPS requests; a non-sandboxed direct-download app does not need a separate network entitlement.

The beta requests no special entitlements and is not App Sandbox enabled. See [MacOS/PERMISSIONS.md](../MacOS/PERMISSIONS.md) for the complete signing and permission analysis.

## Local Data

Non-secret state is stored under:

```text
~/Library/Application Support/AmazonMusicRPC/
```

This includes `config.json`, diagnostics, logs, redacted network history, the single-instance lock, and an owner-only Unix command socket. Files containing app state are created with restrictive per-user permissions where supported.

Sensitive values are generic-password items in the user's login Keychain:

```text
service: io.github.eripum9.amazon-music-rpc
accounts: lastfm_api_secret, lastfm_session_key, listenbrainz_token
```

The optional login item is:

```text
~/Library/LaunchAgents/io.github.eripum9.amazon-music-rpc.plist
```

Secrets are omitted from `config.json` and redacted from diagnostics/exports.

## Run From Source

Python 3.12 is the development baseline:

```bash
git clone https://github.com/eripum9/Amazon-Music-Discord-RPC.git
cd Amazon-Music-Discord-RPC
git checkout master
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r MacOS/requirements.txt
python -m MacOS.main
```

Run automated checks from the repository root:

```bash
python -m pip install -r Windows/requirements-dev.txt
python -m pytest MacOS/tests Shared/tests
python -m compileall -q MacOS Shared
```

## Build And Drag Install

On macOS, install the build requirements and create both artifacts:

```bash
source .venv/bin/activate
python -m pip install -r MacOS/requirements-build.txt
MacOS/scripts/build_app.sh
MacOS/scripts/create_dmg.sh
```

The build writes:

```text
MacOS/dist/Amazon Music RPC.app
MacOS/dist/Amazon-Music-RPC.dmg
MacOS/dist/Amazon-Music-RPC.dmg.sha256
```

To install, open the DMG, drag **Amazon Music RPC** onto the **Applications** shortcut shown in the DMG, wait for the copy, eject the DMG, and launch `/Applications/Amazon Music RPC.app`.

The target architecture is inherited from the Python interpreter and installed binary wheels. The declared deployment target is macOS 12.0, while the first development host was Intel macOS 15.7.7; Apple-silicon and older-system compatibility require separate tests.

With no `MACOS_CODESIGN_IDENTITY`, the build is ad-hoc signed for local testing. This repository does not claim that a beta DMG has been Developer ID signed or notarized. Do not redistribute a local beta build as an official release.

## Shared Windows/macOS Behavior

Platform-native metadata, permissions, startup, and packaging stay separate. User-visible playback decisions live in `Shared/playback.py`: track normalization, privacy matching, process-name/game-mode matching, remembered corrections, custom-art matching, and the scrobble threshold of at least 30 seconds plus either 50% of a known duration or 240 seconds.

A fundamental behavior change must update the shared module or deliberately update and test both platform implementations. The macOS beta must not gain a different privacy or scrobbling interpretation from the stable Windows build merely because its native metadata source is different.
