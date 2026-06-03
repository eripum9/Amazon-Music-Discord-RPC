# Release Checklist

Use this before publishing a Windows release.

## Required Artifacts

- `Windows/installer_output/AmazonMusicRPC_Setup.exe`
- SHA256 hash for `AmazonMusicRPC_Setup.exe`
- Release notes with a clear changelog
- Compatibility note for enhanced metadata and fallback mode

## Local Verification

```powershell
python -m py_compile Windows\main.py Windows\amazon_devtools.py Windows\media_reader.py Windows\discord_rpc.py Windows\config.py Windows\updater.py Windows\status_summary.py Windows\qt_tray_ui.py Windows\rpc_state.py Windows\metadata_pipeline.py Windows\launcher_diagnostics.py Windows\security_trust.py Windows\self_tests.py Windows\release_smoke.py
python -m pytest Windows\tests
python Windows\release_smoke.py --installer Windows\installer_output\AmazonMusicRPC_Setup.exe --release-notes release-notes.md
git diff --check
```

## Release Notes Requirements

Every release description should include:

- `AmazonMusicRPC_Setup.exe SHA256: <hash>`
- New user-facing features
- Fixes for existing behavior
- Microsoft Store enhanced metadata compatibility note
- Fallback mode note for users who cannot use enhanced metadata

## Security Checks

- Do not paste config files, diagnostics ZIPs, or logs into release notes.
- Confirm diagnostics exports use redacted config and logs.
- Confirm no Last.fm session key, ListenBrainz token, Discord token, or private config value appears in release notes, diagnostics, screenshots, or logs.
- Keep the latest installer attached to the release.
- Keep code signing and signed tags on the future hardening list until they are available.
