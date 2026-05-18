# Troubleshooting

## Discord Status Does Not Show

- Make sure the Discord desktop app is running.
- Make sure Amazon Music RPC is running in the tray.
- Check Settings and confirm private session is off.
- Check keyword filters if only some tracks are hidden.
- Open Diagnostics from the tray and check the Discord and RPC cards.

## Amazon Music Metadata Is Not Attached

- Open Settings and confirm **Enhanced Amazon metadata** is enabled.
- Launch Amazon Music from the app tray or the metadata launcher.
- If Amazon Music is already open without metadata access, enable automatic metadata repair or restart Amazon Music from the app.
- Open Diagnostics and check the Amazon Metadata card for the current state.

## Fallback Mode

If enhanced metadata is disabled or unavailable, the app falls back to Windows media metadata. This can still show the current song, but artwork, album, and timing may be less complete.

Notification fallback can improve fallback metadata, but it is optional and disabled by default.

## Notification Fallback Requirements

- Enable notification fallback in Settings.
- Allow Windows notification access if Windows asks.
- Enable notifications in Amazon Music.
- Minimize Amazon Music so notifications appear.

Notification fallback reads Windows notifications locally and only uses Amazon Music notification text.

## Last.fm Or ListenBrainz Issues

- Reauthenticate Last.fm from Settings if it shows as not authenticated.
- For ListenBrainz, paste a fresh user token and validate it.
- Use **Clear Scrobbling Tokens** if you want to disconnect both services and start again.
- Private session can pause scrobbling while it is enabled.

## Updater Or Installer Warnings

Windows SmartScreen can warn because the installer is unsigned. Use the GitHub release page and SHA256 hash in the release notes to verify the installer.

Manual PowerShell check:

```powershell
Get-FileHash .\AmazonMusicRPC_Setup.exe -Algorithm SHA256
```

Compare the result with the SHA256 value on the GitHub release page.
