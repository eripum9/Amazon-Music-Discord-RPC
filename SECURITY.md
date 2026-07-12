# Security Policy

## Supported Versions

Only the latest public release is supported for security fixes. If you are running an older version, update before reporting a bug unless the issue also reproduces on the latest release.

## Reporting a Vulnerability

Please do not post tokens, config files, logs, screenshots with secrets, or exploit details in a public issue.

For non-sensitive security hardening suggestions, open a GitHub issue at:

https://github.com/eripum9/Amazon-Music-Discord-RPC/issues

For sensitive reports, use [GitHub private vulnerability reporting](https://github.com/eripum9/Amazon-Music-Discord-RPC/security/advisories/new). It is enabled for this repository. Do not include exploit details in a public issue.

Useful report details:

- Amazon Music RPC version
- Windows version
- Whether the installed build or source build is used
- Whether enhanced metadata is enabled
- Whether notification enrichment or scrobbling is enabled
- A short reproduction path
- Redacted logs only

## What The App Reads

Amazon Music RPC can read:

- Amazon Music playback metadata from the local Amazon Music app when enhanced metadata is enabled
- Windows media metadata through SMTC fallback
- Amazon Music Windows notifications when notification enrichment is enabled
- Settings from the local config file
- Local logs for the diagnostics window

Enhanced metadata uses a local debugging interface on a random high port for the current app session. The selected port is kept in memory, shared only with child settings windows, and target validation is limited to Amazon Music pages on `music.amazon.*`.

Notification enrichment is disabled by default. If enabled, it reads Windows notifications locally and filters them for Amazon Music metadata.

## What The App Sends

Amazon Music RPC can send:

- Song title, artist, album, playback time, and artwork URL to Discord through local Discord IPC for Rich Presence
- Scrobbles to Last.fm if Last.fm is enabled
- Scrobbles to ListenBrainz if ListenBrainz is enabled
- Track lookup requests to Deezer or iTunes when fallback matching or artwork lookup is enabled and needs them
- Release check requests to GitHub when update checks run

The app does not upload raw logs or config files automatically.

Automatic update checks, Deezer lookup, and iTunes artwork fallback can each be disabled under **Network & Updates**. Diagnostics keeps only a bounded redacted request history; it does not retain lookup queries or token values. The full endpoint inventory is documented in [docs/network-endpoints.md](docs/network-endpoints.md).

## Tokens And Secrets

Last.fm session keys and ListenBrainz tokens are stored locally when those features are enabled. Sensitive config values are migrated out of `%APPDATA%\AmazonMusicRPC\config.json` into Windows Credential Manager. Migration verifies each stored value before removing its previous copy. If Credential Manager is unavailable, a DPAPI-wrapped local secret file remains as fallback. Diagnostics and log views redact known token values, Settings exports omit tokens unless explicitly requested, and Settings includes a clear-token action. Local app data should still be treated as private because a running app needs decrypted values in memory.

Do not paste config files, diagnostics, or logs publicly unless you have checked that tokens and private data are removed.

The bundled Last.fm API key and API secret are public application credentials for this open-source app. They are not your Last.fm account password or session token.

## Enhanced Metadata

Enhanced metadata is optional for new installs. It improves track names, album art, playback state, and timing by launching or repairing Amazon Music with a local debugging interface.

Security behavior:

- The debug port is randomly selected from a high local port range.
- The selected port is stored in memory for the app session.
- The app refuses non-Amazon Music targets.
- The selected target WebSocket must use the selected loopback port and exact target identifier.
- A listener that cannot be validated as an Amazon Music process is rejected.
- The common DevTools port `9222` is not used for launching Amazon Music.
- Diagnostics warns if the common DevTools port is reachable unexpectedly.

When Amazify integration is present, its localhost bridge requires a per-user random token and accepts browser requests only from exact supported Amazon Music origins. Uninstall removes only the Amazon Music RPC integration files and token.

To disable enhanced metadata, open Settings and turn off **Enhanced Amazon metadata**. To avoid Windows notification access too, leave **Notification enrichment** turned off.

## Private Session

Private session mode clears Discord Rich Presence and can stop scrobbling while it is enabled. Keyword privacy rules can also block specific tracks from being shared.

## Updates

The updater checks GitHub releases and can download the latest installer. It opens the GitHub release page before running the installer, requires an `AmazonMusicRPC_Setup.exe.sha256` release asset or a legacy SHA256 hash in the release notes, downloads to a unique temporary directory, and verifies the installer before launching it. If no hash is available, automatic install is disabled and the app only opens the release page.

Official release drafts are built only from the current `master` commit by a manually triggered GitHub Actions workflow. The workflow installs hash-locked dependencies, runs tests and dependency auditing, creates an SBOM and build evidence, scans the installer with Microsoft Defender when available, and generates GitHub artifact attestations. Each release includes `AmazonMusicRPC_Setup.exe`, its matching `AmazonMusicRPC_Setup.exe.sha256`, a clear changelog, and an enhanced metadata compatibility note.

Windows code signing is applied when the repository signing certificate is configured. Unsigned drafts are explicitly labeled as unsigned and must be reviewed before publication.

## Uninstall

The installer removes installed files, startup entries, logs, config data, and Amazon Music metadata launcher shortcuts during uninstall. If you ran from source, delete the project folder, the `Windows/config.json` source config if present, and `%APPDATA%\AmazonMusicRPC` manually.

The repository threat model and trust boundaries are maintained in [docs/threat-model.md](docs/threat-model.md).
