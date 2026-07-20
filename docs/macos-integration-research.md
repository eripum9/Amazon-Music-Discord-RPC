# macOS Integration Research

Status: preliminary static analysis; live playback inspection is paused until an Amazon Music login is available.

## Scope And Safety

The installed application was found at `/Applications/Amazon Music.app`. A read-only working copy was made in a uniquely named directory under `/tmp` for bundle and binary inspection. The application bundle and extracted binaries are not stored in this repository.

No macOS implementation or documentation claims should be promoted to stable support until live playback behavior has been verified.

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

### 1. macOS Now Playing

This is the preferred first experiment because it does not require attaching to or modifying Amazon Music. The weak link to `MediaPlayer.framework` is evidence that the application may publish system media state.

Potentially useful fields include:

- Track title, artist, and album
- Duration and elapsed playback time
- Playback rate, which can distinguish playing from paused
- Artwork data when exposed by the active Now Playing client
- Owning application or bundle identifier, which must be checked against `com.amazon.music`

On recent macOS versions, direct use of the private `MediaRemote` C API is entitlement-restricted. A small JavaScript for Automation probe can load the local `MediaRemote.framework` classes through `osascript` and read `MRNowPlayingRequest`. The probe executed successfully on this machine, but there was no active Amazon Music metadata to validate before the login pause.

This route uses private implementation details and therefore needs a compatibility fallback and explicit testing on supported macOS releases.

### 2. Chromium DevTools Protocol

The embedded CEF runtime makes a loopback Chromium DevTools connection plausible. It could provide richer Amazon Music page state, including artwork URLs and exact timing, similar to the current Windows enhanced-metadata path.

This remains unverified. A controlled background launch with a high loopback debugging port was started, then intentionally paused before its result was collected so the account can be logged in first.

If supported, the implementation must preserve the existing security boundaries:

- Use a random high port bound to loopback only.
- Keep the port in memory rather than in shared configuration.
- Accept only page targets whose parsed HTTPS hostname is an approved `music.amazon.*` host.
- Reject credentials, unexpected ports, non-HTTPS targets, and lookalike domains.
- Stop or detach cleanly without leaving a debugging endpoint exposed.

### 3. Accessibility Or Window Metadata

macOS Accessibility could provide a limited fallback when system Now Playing and CEF metadata are unavailable. It may require user approval and is likely to be more fragile, so it should not be the primary integration.

## Next Live Tests

After login is available:

1. Play a known track and capture only the field names and owning bundle identifier exposed by macOS Now Playing.
2. Verify title, artist, album, duration, elapsed time, artwork availability, and playing/paused transitions.
3. Retry the CEF loopback launch and inspect `/json/version` and `/json/list` without retaining account data.
4. Confirm that any CEF target validation accepts Amazon Music and rejects synthetic hostile URLs.
5. Compare both paths and choose a primary source plus fallback hierarchy.
6. Only then update platform claims in `README.md`, `CONTRIBUTING.md`, and the architecture/privacy documentation.

## Research References

- [Apple MPNowPlayingInfoCenter documentation](https://developer.apple.com/documentation/mediaplayer/mpnowplayinginfocenter)
- [mediaremote-adapter](https://github.com/ungive/mediaremote-adapter), an open-source compatibility approach for newer macOS versions
- [nowplaying-cli](https://github.com/kirtan-shah/nowplaying-cli), a reference implementation that documents available Now Playing properties

These projects are research references only. Their licenses and private-framework tradeoffs must be reviewed before adopting code or a runtime dependency.
