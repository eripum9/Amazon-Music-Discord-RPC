# Platform Roadmap

Amazon Music RPC targets platforms where Amazon Music has an official app surface that can be supported responsibly. Windows is the sole supported target.

## Current Platform Status

| Platform | Status | Branch | Notes |
| --- | --- | --- | --- |
| Windows | Stable | `master` | Main supported release target. |

## Out Of Scope

Android support is discontinued because its media-session, background-service, and Discord integration were too unstable to maintain as a supported product.

Linux and macOS are out of scope because Amazon Music does not provide official desktop apps for those platforms. Browser, PWA, or unofficial-wrapper approaches should not be treated as supported targets for this project.

If platform conditions change later, support can be reconsidered with a fresh metadata and Discord presence proof-of-concept.
