# macOS Integration Research

Status: bundle research and a read-only Now Playing proof of concept are complete. A native beta runtime, validated DevTools transport, settings/diagnostics UI, shared playback behavior, `.app`, and drag-install DMG pipeline are implemented on `beta/MacOS`. Live Discord Rich Presence and live Last.fm/ListenBrainz submissions have not yet been tested end to end.

## Scope And Safety

Amazon now provides an official macOS desktop app. The installed application was found at `/Applications/Amazon Music.app`. A read-only working copy was made in a uniquely named directory under `/tmp` for bundle and binary inspection; neither that copy nor extracted Amazon binaries are stored in this repository.

The research avoided retaining current-track values, account data, cookies, tokens, browser storage, or authenticated application files. The prototype does not modify or inject code into Amazon Music.

## Verified Bundle Findings

The inspected application reported:

- Bundle identifier: `com.amazon.music`
- Version: `9.5.2` (`9.5.2.2478`)
- Executable architecture: Intel `x86_64`
- Signature identity: `Developer ID Application: AMZN Mobile LLC (94KV3E626L)`
- Custom URL scheme: `amazoncloudplayer`
- Approximate copied bundle size: 459 MB

Relevant linked components included Qt 4.8 (`QtCore`, `QtGui`, and `QtNetwork`), Chromium Embedded Framework compatibility version `791.0.31`, a weak link to Apple's `MediaPlayer.framework`, and separate renderer/GPU helper applications.

The signature metadata includes hardened-runtime allowances appropriate to Amazon's embedded Chromium/JIT code. Amazon Music RPC does not copy those entitlements, embed Chromium, inject code, or attach a debugger. The copied research bundle contained an updater-generated `update.ini` outside the sealed resources, so deep verification of that copy reported an extra file; that observation alone did not establish that the installed application was modified.

## Selected Metadata Architecture

### 1. Chromium DevTools Protocol (Primary)

Launching the embedded CEF runtime with a loopback debugging flag exposed a DevTools target, confirming that CDP can provide the richer Amazon-native metadata needed for album artwork, exact timing, links, and playback state. A normal Amazon Music launch has no listener.

The beta therefore uses DevTools first when enhanced metadata is enabled. If Amazon Music is already open normally, the application reports `restart_required`; the user must explicitly choose a one-time restart for that running session. No persistent shortcut, preference, browser profile, or Amazon application file is changed. A normal relaunch removes the listener.

The implementation narrows CDP's inherently sensitive authenticated-renderer access:

- It accepts only the official bundle at `/Applications/Amazon Music.app`, exact identifier/executable, Amazon Team ID, and signing authority.
- It chooses an in-memory port in `49152–60999`, passes `--remote-debugging-address=127.0.0.1`, and never binds Amazon Music RPC itself to a TCP listener.
- It identifies all listener PIDs with `lsof` and accepts only executables resolving inside the validated Amazon bundle. Ownership is checked before discovery and again before evaluation.
- Discovery requests are limited to `/json`, `/json/list`, and `/json/version`; HTTP, WebSocket handshake, frame, and JSON sizes are bounded.
- Page URLs must be exact supported HTTPS `music.amazon.<region>` hosts or the exact legacy Amazon Morpho webapp path. Credentials, non-default HTTPS ports, lookalike hosts, untrusted WebSocket paths, query-bearing WebSocket URLs, and mismatched target IDs are rejected.
- Only a bounded `Runtime.evaluate` expression reads visible transport metadata. The code does not request cookies, browser storage, request headers/bodies, downloads, or debugging primitives.
- Track links and artwork pass independent exact-host/scheme validation. Failed launches are terminated, and restart/stop actions signal only revalidated Amazon executable paths.

Loopback blocks remote-network connections, but the CEF listener has no application-level authentication. Another local process running as the same user could potentially discover it while enhanced metadata is active. Turning off the RPC setting stops this app from connecting but does not reconfigure the already-running Amazon process. Users who do not accept that local exposure can use the explicitly confirmed **Disable listener & reopen normally** action, or close/relaunch Amazon Music normally, then remain in Now Playing fallback mode. See [macos-beta.md](macos-beta.md) for the user-facing boundary.

### 2. macOS Now Playing (Verified Fallback)

Live testing on Intel macOS 15.7.7 confirmed that the active Now Playing owner identifies itself as `com.amazon.music`. The fallback can provide:

- Track title, artist, and album
- Duration and calculated elapsed playback time
- Playback rate, which distinguishes playing from paused
- Artwork descriptors when exposed by the active Now Playing client
- The owning bundle identifier, which is required to equal `com.amazon.music`

On recent macOS versions, direct use of the private `MediaRemote` C API is entitlement restricted. The fallback loads local `MediaRemote.framework` classes through JavaScript for Automation and `/usr/bin/osascript`, then reads `MRNowPlayingRequest`. It does not send Apple Events to Amazon Music or control playback.

The live probe verified exact owner validation, title/artist/album availability, duration, playing/paused state, and `MRContentItemMetadata.calculatedPlaybackPosition`. Position advanced by approximately 2.02 seconds during a two-second sample. Artwork MIME type, dimensions, identifier, and local/remote descriptors were present, but the synchronous object did not expose bounded image bytes or a directly usable HTTPS URL. The implementation therefore leaves fallback artwork empty so the existing optional Deezer/iTunes lookup can fill it.

The fallback consists of:

- `MacOS/amazon_music_now_playing.js`, which serializes the local Now Playing state without playback controls
- `MacOS/media_reader.py`, which invokes `/usr/bin/osascript` without a shell, enforces time/output limits, validates `com.amazon.music`, sanitizes every field, and returns the common track shape

Three consecutive live reads completed in approximately 1.83–2.56 seconds, retained track identity, and reported non-decreasing positions. A four-second timeout leaves margin for this polling fallback.

### Deferred Persistent Adapter Research

The BSD-3-Clause [mediaremote-adapter](https://github.com/ungive/mediaremote-adapter) was built from source in a temporary directory and returned a read-only Amazon-owned event stream, including playback and artwork metadata. It uses an entitled system host and private-framework/dynamic-loading behavior that would require license notices, a separate security review, compatibility testing, and bounded artwork handling.

It is not bundled in the beta. The current hierarchy is validated DevTools first and the zero-install JXA Now Playing reader second. Adapter adoption should be reconsidered only if polling reliability justifies the additional private-framework and supply-chain surface.

## Rejected Interfaces

### Accessibility Or Window Scraping

Accessibility is fragile, exposes a broader UI surface, and requires a TCC permission that the selected metadata paths do not need. The beta does not request Accessibility, Automation, Screen Recording, Input Monitoring, Full Disk Access, or Media & Apple Music permission.

### Amazon Internal IPC And Account Storage

`/tmp/AmazonMusic.ipc` uses a proprietary Boost.Asio/CEF protocol, while the per-instance Qt local-peer socket is an internal single-instance channel. Neither is a supported metadata API.

Amazon Music's Application Support directory can contain cookies, LevelDB/IndexedDB, local storage, offline state, player configuration, and logs. Those authenticated/account-linked files are explicitly outside the integration boundary and must not be read for metadata.

## Implemented Prototype Boundaries

- Non-secret config, diagnostics, and logs: `~/Library/Application Support/AmazonMusicRPC/`
- Last.fm/ListenBrainz secret service in login Keychain: `io.github.eripum9.amazon-music-rpc`
- Optional login item: `~/Library/LaunchAgents/io.github.eripum9.amazon-music-rpc.plist`
- No expected Accessibility, Automation, Screen Recording, Input Monitoring, Full Disk Access, Media & Apple Music, or Local Network prompt
- Conditional Keychain access, background-item notification, and user-selected file access only
- Platform-neutral privacy, corrections, process matching, custom art, track normalization, and scrobble threshold in `Shared/playback.py`

## Remaining Manual Tests

1. Install Discord and verify presence creation, pause/resume timers, track changes, buttons/artwork, Discord restart/reconnect, and presence clearing.
2. Verify live Last.fm authentication/now-playing/scrobbling and live ListenBrainz token validation/now-playing/scrobbling without exposing credentials.
3. Exercise the explicit Amazon restart flow, fallback-only mode, normal relaunch cleanup, and listener-owner rejection.
4. Test Keychain approval and denial, login-item enable/disable, selected-file import/export, and unexpected TCC prompts on a clean macOS account.
5. Mount the DMG, drag to Applications, eject, launch the installed copy, verify menu-bar visuals, and test clean uninstall.
6. Repeat on Apple silicon and older supported macOS versions; the first development host was Intel macOS 15.7.7.
7. Complete Developer ID signing, notarization, stapling, and clean-machine Gatekeeper validation before describing any public DMG as a distributable release.

## Research References

- [Apple MPNowPlayingInfoCenter documentation](https://developer.apple.com/documentation/mediaplayer/mpnowplayinginfocenter)
- [mediaremote-adapter](https://github.com/ungive/mediaremote-adapter)
- [nowplaying-cli](https://github.com/kirtan-shah/nowplaying-cli)

External projects remain research references unless their code, license obligations, and private-framework tradeoffs are explicitly adopted and reviewed.
