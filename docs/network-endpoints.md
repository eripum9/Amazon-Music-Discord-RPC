# Network Endpoints

Amazon Music RPC does not send logs or config files automatically. This inventory describes runtime network destinations. Exact availability can vary by enabled feature and provider SDK.

| Destination | Purpose | Data | Control |
| --- | --- | --- | --- |
| `api.github.com` | Release metadata and automatic update checks | Current app version and standard HTTPS request metadata | **Automatic update checks** |
| GitHub release asset hosts | Installer and detached SHA256 download after user approval | Requested release asset | Update action; automatic install requires checksum verification |
| `api.deezer.com` | Track matching, artwork, duration, optional Deezer link | Track and artist search text | **Deezer lookup** |
| `itunes.apple.com` | Artwork and track fallback | Track and artist search text | **iTunes artwork fallback** |
| Last.fm API endpoints used by `pylast` | Authentication, now-playing, and scrobbling | Enabled account token and track metadata | **Last.fm scrobbling** |
| ListenBrainz API endpoints used by `liblistenbrainz` | Token validation, now-playing, and scrobbling | Enabled account token and track metadata | **ListenBrainz scrobbling** |
| Amazon Music regional sites | User-facing track/search links and artwork already supplied by Amazon Music | Browser navigation or Discord artwork URL | Song link and enhanced metadata settings |
| Remote artwork hosts returned by Amazon, Deezer, or iTunes | Discord artwork rendering | Artwork URL | Metadata/artwork provider controls |

Discord Rich Presence uses the local Discord IPC connection. Discord may then process the presence and remote artwork URLs under Discord’s own service behavior.

## Local-Only Interfaces

- Enhanced metadata uses `127.0.0.1` on a random high port selected for the current Amazon Music session.
- Amazify integration uses a token-authenticated loopback HTTP bridge on its configured local port.
- Neither local interface is intended to listen on a non-loopback address.

## Diagnostics History

Diagnostics retains at most 50 recent outbound operation records. Each record contains the provider, operation name, result, short non-sensitive detail, and timestamp. Query text, response bodies, and authentication tokens are not stored in this history.
