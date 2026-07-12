# Privacy

Amazon Music RPC is built to show Amazon Music playback on Discord while keeping the sensitive parts visible and controllable.

## What Stays Local

- Enhanced metadata reads the Amazon Music desktop app locally.
- Windows SMTC metadata is read locally as the fallback path.
- Notification fallback reads Windows notifications locally and only uses Amazon Music notification text.
- Settings, logs, and diagnostics are stored on your Windows device.

## What Can Be Sent Out

- Discord Rich Presence receives the song title, artist, album, artwork URL, playback state, and timer through local Discord IPC.
- Last.fm receives scrobbles only if Last.fm scrobbling is enabled.
- ListenBrainz receives scrobbles only if ListenBrainz scrobbling is enabled.
- Deezer and iTunes can receive track search terms when fallback artwork or track matching needs them.
- GitHub is contacted for update checks.

## Enhanced Metadata

Enhanced metadata is optional for new installs. It gives the best track names, album art, pause state, and timing by launching or repairing Amazon Music with a local metadata interface.

The metadata port is randomly selected from a high local port range for each app session, kept in memory, and the app only attaches to Amazon Music pages on `music.amazon.*`.

To run without enhanced metadata, open Settings and turn off **Enhanced Amazon metadata**.

## Tokens

Last.fm session keys and ListenBrainz tokens are migrated out of the normal config and stored in Windows Credential Manager. The app verifies migration before deleting the old config value. If Credential Manager is unavailable, a DPAPI-protected local fallback is used.

Diagnostics and log views redact known token values, Settings exports omit tokens unless explicitly requested, and Settings includes a clear-token action. Treat the entire `%APPDATA%\AmazonMusicRPC` directory as private because decrypted values must exist briefly in app memory while a service is used.

## Network Controls

Settings provides separate controls for automatic update checks, Deezer lookup, and iTunes artwork fallback. Disabling a lookup prevents that provider from receiving track search terms. Last.fm and ListenBrainz are contacted only when their scrobbling options are enabled.

Diagnostics shows a bounded redacted history of recent outbound operations. It stores service, operation, result, and time, not the query text or authentication token. See [network-endpoints.md](network-endpoints.md) for the endpoint inventory.

## Private Session

Private session clears Discord presence and can stop scrobbling while it is enabled. Keyword filters can also hide matching tracks.

## Uninstall

The installer removes installed files, startup entries, logs, config data, and Amazon Music metadata launcher shortcuts during uninstall. If you ran from source, delete the project folder, the `Windows/config.json` source config if present, and `%APPDATA%\AmazonMusicRPC` manually.
