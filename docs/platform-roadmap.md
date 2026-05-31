# Platform Roadmap

Amazon Music RPC targets platforms where Amazon Music has an official app surface that can be supported responsibly. Windows is the stable desktop target, and Android is the mobile target under active testing.

## Current Platform Status

| Platform | Status | Branch | Notes |
| --- | --- | --- | --- |
| Windows | Stable | `master` | Main supported release target. |
| Android | Beta | `master` | Active test target in `Android/` with a fake Amazon test app and emulator path. |

## Out Of Scope

Linux and macOS are out of scope because Amazon Music does not provide official desktop apps for those platforms. Browser, PWA, or unofficial-wrapper approaches should not be treated as supported targets for this project.

If Amazon releases official Linux or macOS desktop apps later, platform support can be reconsidered with a fresh metadata and Discord presence proof-of-concept.

## Android Readiness

- Repeatable debug builds for the RPC app and fake Amazon test app
- Emulator test instructions that a second person can follow
- Working Discord presence with title, artist, album, duration, and elapsed time
- Pause, resume, seek, stop, and clear-presence behavior tested
- Known background-service limitations documented
- At least one real-device test or a clear reason why emulator-only testing is acceptable for that milestone

Android status and test steps are tracked in [docs/android-beta.md](android-beta.md).
