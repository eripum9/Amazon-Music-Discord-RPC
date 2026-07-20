# macOS Integration Research

Status: static analysis and a read-only live playback proof of concept are complete. A full macOS application runtime has not been built yet.

## Scope And Safety

The installed application was found at `/Applications/Amazon Music.app`. A read-only working copy was made in a uniquely named directory under `/tmp` for bundle and binary inspection. The application bundle and extracted binaries are not stored in this repository.

The live checks intentionally avoided printing or persisting the current track, account data, cookies, or tokens.

## Verified Bundle Findings

The installed application reports:

- Bundle identifier: `com.amazon.music`
- Version: `9.5.2` (`9.5.2.2478`)
- Executable architecture: Intel `x86_64`
- Signature identity: `Developer ID Application: AMZN Mobile LLC (94KV3E626L)`
- Custom URL scheme: `amazoncloudplayer`
- Approximate copied bundle size: 459 MB

The main executable links the following components relevant to an RPC integration:

- Qt 4.8 (`QtCore`, `QtGui`, and `QtNetwork`)
- Chromium Embedded Framework, compatibility version `791.0.31`
- Apple's `MediaPlayer.framework` as a weak-linked framework
- Separate renderer and GPU helper applications

The signature metadata includes hardened-runtime allowances for JIT execution and debugging-related behavior, which is consistent with an embedded Chromium application. The copied bundle also contained an updater-generated `update.ini` file that was not part of the sealed resources, so deep verification of the copy reported that extra file. This result alone does not establish that the installed application was modified.

## Candidate Metadata Interfaces

### 1. macOS Now Playing (Verified)

This is the recommended primary metadata path because it does not require attaching to or modifying Amazon Music. Live testing on macOS 15.7.7 confirmed that the active Now Playing client identifies itself as `com.amazon.music`.

Potentially useful fields include:

- Track title, artist, and album
- Duration and elapsed playback time
- Playback rate, which can distinguish playing from paused
- Artwork data when exposed by the active Now Playing client
- Owning application or bundle identifier, which must be checked against `com.amazon.music`

On recent macOS versions, direct use of the private `MediaRemote` C API is entitlement-restricted. The proof of concept instead loads the local `MediaRemote.framework` classes through JavaScript for Automation and `/usr/bin/osascript`, then reads `MRNowPlayingRequest`.

The live probe verified:

- Exact ownership validation through `com.amazon.music`
- Title, artist, and album availability
- Duration and playing/paused state through playback rate
- Accurate position through `MRContentItemMetadata.calculatedPlaybackPosition`
- Position advancement of approximately 2.02 seconds during a two-second sample
- Artwork availability, MIME type, dimensions, identifier, and local/remote artwork descriptors

The synchronous artwork object did not expose image bytes, and its identifier was not a directly usable HTTPS URL. The initial implementation therefore leaves artwork empty so the existing bounded Deezer/iTunes lookup path can provide it. Artwork retrieval can be investigated separately without blocking metadata polling.

The bundled fallback proof of concept is split into:

- `MacOS/amazon_music_now_playing.js`, which reads and serializes the local Now Playing state without playback controls
- `MacOS/media_reader.py`, which invokes the probe without a shell, enforces a timeout and output-size limit, validates the Amazon bundle identifier, sanitizes fields, and returns the existing track dictionary shape

Three consecutive live reads completed in approximately 1.83 to 2.56 seconds, retained the same track identity, and reported a non-decreasing position. A four-second timeout leaves margin for this polling fallback.

#### Recommended Production Event Stream

The open-source [mediaremote-adapter](https://github.com/ungive/mediaremote-adapter) was also built from source in a temporary directory and exercised against the playing Amazon Music instance. Its read-only stream returned the `com.amazon.music` owner, playback state, text metadata, duration, timestamp, playback rate, and artwork MIME metadata. No account or track values were retained in the research output.

The adapter uses the entitled system `/usr/bin/perl` host to load a bundled helper framework, avoiding the macOS 15.4 entitlement failure that affects ordinary third-party MediaRemote clients. Its persistent JSON event stream avoids repeated `osascript` startup and can deliver artwork bytes in a later update. It is BSD-3-Clause licensed, but its private-framework dependency and dynamic-loading design still require security review, bundled license notices, and macOS compatibility tests.

The recommended hierarchy is therefore:

1. A bundled, read-only mediaremote-adapter event stream for production metadata and eventual artwork.
2. The current JXA reader as a zero-install polling fallback.
3. Existing external artwork lookup when the system does not provide artwork bytes.

This route uses private implementation details and therefore needs a compatibility fallback and explicit testing on supported macOS releases.

### 2. Chromium DevTools Protocol

The embedded CEF runtime makes a loopback Chromium DevTools connection plausible. It could provide richer Amazon Music page state, including artwork URLs and exact timing, similar to the current Windows enhanced-metadata path.

An earlier transient launch did expose CEF DevTools on loopback when the debugging flag was supplied, confirming that CDP is possible. A normal launch has no debugging listener. Because CDP exposes the authenticated renderer and is unnecessary for core metadata, it should remain an opt-in diagnostic experiment rather than the default integration.

If supported, the implementation must preserve the existing security boundaries:

- Use a random high port bound to loopback only.
- Keep the port in memory rather than in shared configuration.
- Accept only page targets whose parsed HTTPS hostname is an approved `music.amazon.*` host.
- Reject credentials, unexpected ports, non-HTTPS targets, and lookalike domains.
- Stop or detach cleanly without leaving a debugging endpoint exposed.

### 3. Accessibility Or Window Metadata

macOS Accessibility could provide a limited fallback when system Now Playing and CEF metadata are unavailable. It may require user approval and is likely to be more fragile, so it should not be the primary integration.

### Rejected Internal Interfaces

The application creates `/tmp/AmazonMusic.ipc` using a proprietary Boost.Asio/CEF message protocol and also uses a per-instance Qt local-peer socket. These are internal browser/renderer and single-instance channels rather than supported metadata APIs.

Amazon Music's Application Support directory contains cookies, LevelDB/IndexedDB data, local storage, offline state, player configuration, and logs. Those files can contain authenticated or account-linked state, are often locked while the app is running, and must not be used as a metadata integration surface.

## Remaining Tests

1. Verify a manual pause/resume transition without having the test control playback.
2. Verify track-change behavior and position reset across at least two tracks.
3. Integrate and security-review the persistent adapter stream, including clean shutdown and restart behavior.
4. Validate delayed artwork events and cap decoded artwork size before use.
5. Build the macOS runtime and connect the normalized reader to Discord RPC.
6. Update platform claims in `README.md`, `CONTRIBUTING.md`, and the architecture/privacy documentation only when that runtime is usable.

## Research References

- [Apple MPNowPlayingInfoCenter documentation](https://developer.apple.com/documentation/mediaplayer/mpnowplayinginfocenter)
- [mediaremote-adapter](https://github.com/ungive/mediaremote-adapter), an open-source compatibility approach for newer macOS versions
- [nowplaying-cli](https://github.com/kirtan-shah/nowplaying-cli), a reference implementation that documents available Now Playing properties

These projects are research references only. Their licenses and private-framework tradeoffs must be reviewed before adopting code or a runtime dependency.
