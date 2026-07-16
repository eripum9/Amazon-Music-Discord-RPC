# Release Checklist

Use this to review and publish a release draft created by the **Build Draft Release** workflow. Do not upload a locally built installer as an official release.

## Create The Draft

- Merge the intended release commit into `master`.
- Confirm `Windows/config.py` and `Windows/installer.iss` contain the same version.
- Open **Actions > Build Draft Release > Run workflow** on `master`.
- Enter the version without the `v` prefix and a one-sentence summary.
- Wait for every workflow step to pass.
- Do not publish a draft created from a superseded `master` commit.

## Required Artifacts

- `Windows/installer_output/AmazonMusicRPC_Setup.exe`
- `Windows/installer_output/AmazonMusicRPC_Setup.exe.sha256`
- Release notes with a clear changelog
- Compatibility note for enhanced metadata and fallback mode

Always upload `AmazonMusicRPC_Setup.exe` and its newly generated `AmazonMusicRPC_Setup.exe.sha256` together. Never reuse a checksum from an earlier build or publish the installer without its matching sidecar.

## Workflow Verification

Confirm the workflow completed all of these checks:

- Version and current `master` validation
- Hash-locked dependency installation
- Python compilation, pytest, built-in self-tests, and Ruff safety checks
- Coverage remained at or above the repository threshold
- Dependency vulnerability audit
- Clean PyInstaller and Inno Setup builds with UPX and stripping disabled
- Packaged Settings and Diagnostics smoke tests
- Silent installer and uninstaller smoke test
- Microsoft Defender scan, or an explicit unavailable result
- CycloneDX SBOM, build manifest, and security report upload
- GitHub provenance attestations for the installer and checksum

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
- Confirm the release contains only the installer and checksum as public release assets.
- Download the Actions `release-evidence-vX.Y.Z` artifact and review the SBOM, build manifest, and security report.
- Verify the attestation with `gh attestation verify AmazonMusicRPC_Setup.exe -R eripum9/Amazon-Music-Discord-RPC`.
- Confirm the release notes state that the installer is unsigned and explain checksum and provenance verification.
- Test the downloaded installer on a clean or disposable Windows environment before publishing.
- Publish the existing draft; do not rebuild or replace assets after approval.
