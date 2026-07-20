# Network Endpoints

Amazon Music RPC does not send logs or config files automatically. This inventory describes runtime network destinations. Exact availability can vary by enabled feature and provider SDK.

| Destination | Purpose | Data | Control |
| --- | --- | --- | --- |
| `api.github.com` | Release metadata and automatic update checks | Current app version and standard HTTPS request metadata | **Automatic update checks** |
| GitHub release asset hosts (`github.com`, validated GitHub asset redirects) | Windows installer or macOS DMG plus detached SHA256 download after user approval | Requested release asset | Update action; automatic download requires checksum verification |
| `api.deezer.com` | Track matching, artwork, duration, optional Deezer link | Track and artist search text | **Deezer lookup** |
| `itunes.apple.com` | Artwork and track fallback | Track and artist search text | **iTunes artwork fallback** |
| Last.fm API endpoints used by `pylast` | Authentication, now-playing, and scrobbling | Enabled account token and track metadata | **Last.fm scrobbling** |
| ListenBrainz API endpoints used by `liblistenbrainz` | Token validation, now-playing, and scrobbling | Enabled account token and track metadata | **ListenBrainz scrobbling** |
| Exact supported Amazon Music regional HTTPS sites | User-facing track/search links and artwork already supplied by Amazon Music | Browser navigation or Discord artwork URL | Song link and enhanced metadata settings |
| Remote artwork hosts returned by Amazon, Deezer, or iTunes | Discord artwork rendering | Artwork URL | Metadata/artwork provider controls |

Discord Rich Presence uses local Discord IPC (named-pipe behavior on Windows or a Unix-domain socket on macOS). Discord may then process the presence and remote artwork URLs under Discord's own service behavior. Live macOS Discord connectivity had not been tested when the first beta was built.

## Local-Only Interfaces

- Enhanced metadata uses `127.0.0.1` on a random high port selected for the current Amazon Music session. On macOS the range is `49152–60999`; every listener executable must resolve inside the `/Applications/Amazon Music.app` bundle with the validated Amazon identity, and the target must be an exact allowlisted Amazon HTTPS page on the same port.
- Amazify integration uses a token-authenticated loopback HTTP bridge on its configured local port.
- The macOS app's single-instance channel is an owner-only Unix socket under `~/Library/Application Support/AmazonMusicRPC/` (or an owner-specific short path under the system temporary directory when required by Unix path limits). It accepts only settings, diagnostics, activate, and quit commands.
- The macOS Now Playing fallback invokes a local bounded `/usr/bin/osascript` probe and makes no network request.
- None of these local interfaces is intended to listen on a non-loopback network address. Loopback does not protect the unauthenticated Amazon CEF DevTools endpoint from other software already running as the same local user.

## Diagnostics History

Diagnostics retains at most 50 recent outbound operation records. Each record contains the provider, operation name, result, short non-sensitive detail, and timestamp. Query text, response bodies, and authentication tokens are not stored in this history.
