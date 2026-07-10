# Release Checklist

Use this before publishing a GitHub release.

## Required Artifacts

- `Windows/installer_output/AmazonMusicRPC_Setup.exe`
- `Windows/installer_output/AmazonMusicRPC_Setup.exe.sha256`
- Release notes with a clear changelog
- Compatibility note for enhanced metadata and fallback mode

Always upload `AmazonMusicRPC_Setup.exe` and its newly generated `AmazonMusicRPC_Setup.exe.sha256` together. Never reuse a checksum from an earlier build or publish the installer without its matching sidecar.

## Local Verification

```powershell
python -m py_compile Windows\main.py Windows\amazon_devtools.py Windows\media_reader.py Windows\discord_rpc.py Windows\config.py Windows\updater.py Windows\status_summary.py Windows\qt_tray_ui.py Windows\rpc_state.py Windows\metadata_pipeline.py Windows\launcher_diagnostics.py Windows\security_trust.py Windows\self_tests.py Windows\release_smoke.py
python -m pytest Windows\tests
python Windows\release_smoke.py --installer Windows\installer_output\AmazonMusicRPC_Setup.exe --release-notes release-notes.md
git diff --check
```

## Release Notes Requirements

Every release description should include:

- New user-facing features
- Fixes for existing behavior
- Microsoft Store enhanced metadata compatibility note
- Fallback mode note for users who cannot use enhanced metadata

## Security Checks

- Do not paste config files, diagnostics ZIPs, or logs into release notes.
- Confirm diagnostics exports use redacted config and logs.
- Confirm no Last.fm session key, ListenBrainz token, Discord token, or private config value appears in release notes, diagnostics, screenshots, or logs.
- Keep the latest installer attached to the release.
- Confirm `AmazonMusicRPC_Setup.exe.sha256` is attached beside the installer and matches the uploaded installer. v4.0.1 is the final transition release that also includes the hash in its description.
- Keep code signing and signed tags on the future hardening list until they are available.
