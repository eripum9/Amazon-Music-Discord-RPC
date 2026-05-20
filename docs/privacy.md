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

Last.fm session keys and ListenBrainz tokens are stored locally in the app config today. Diagnostics and log views redact known token values, and Settings includes a clear-token action.

Treat `%APPDATA%\AmazonMusicRPC\config.json` as private.

## Private Session

Private session clears Discord presence and can stop scrobbling while it is enabled. Keyword filters can also hide matching tracks.

## Uninstall

The installer removes installed files, startup entries, logs, config data, and Amazon Music metadata launcher shortcuts during uninstall. If you ran from source, delete the project folder, the `Windows/config.json` source config if present, and `%APPDATA%\AmazonMusicRPC` manually.
