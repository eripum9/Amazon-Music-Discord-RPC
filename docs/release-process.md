# Release Process

Official Windows releases are built by `.github/workflows/release-draft.yml`. The workflow is manual and accepts only the current `master` commit. It creates or updates a draft GitHub release and never publishes it automatically.

## Trust Boundary

- Local builds are development artifacts only.
- The workflow verifies that its checkout still matches `origin/master` before and after the build.
- Python dependencies are installed from `Windows/requirements-release.lock` with required hashes.
- Official builds use Python 3.12.10, the final Python 3.12 release with Windows binaries, so the published WinSDK wheel is used instead of compiling WinSDK from source.
- GitHub Actions are pinned to full commit SHAs.
- UPX compression and binary stripping are disabled.
- Windows artifacts are currently unsigned and release notes state this clearly.
- The installer and checksum receive GitHub build provenance attestations.

## Workflow Inputs

- `version`: semantic version without the `v` prefix. It must match the app and installer source.
- `summary`: one sentence placed near the top of the release notes.
- `prerelease`: whether the draft should be marked as a prerelease.

## Outputs

The draft release has exactly two public assets:

- `AmazonMusicRPC_Setup.exe`
- `AmazonMusicRPC_Setup.exe.sha256`

The workflow also stores a private Actions artifact for 90 days containing:

- CycloneDX SBOM
- Build manifest with commit and installer hash
- Security check report
- Generated release notes

## Publication

Review the generated notes, evidence, installer behavior, checksum, and attestation. Publish the existing draft only after completing [the release checklist](release-checklist.md).
