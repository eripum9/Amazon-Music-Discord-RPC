# Platform Roadmap

Amazon Music RPC targets platforms with an official Amazon Music desktop surface that can be integrated without scraping account storage or requiring broad OS permissions. Windows is the published stable platform; macOS is an active beta development target and is no longer out of scope.

## Current Platform Status

| Platform | Status | Branch | Notes |
| --- | --- | --- | --- |
| Windows | Stable | `master` | Main supported release target and source of the published installer. |
| macOS | Active beta | `master` | Uses Amazon's official macOS app, validated DevTools metadata, and a read-only Now Playing fallback. Covered by macOS CI, but not yet a published stable or notarized release. |

The macOS beta implements the menu-bar UI, Discord/scrobbler runtime paths, privacy controls, diagnostics, Keychain-backed secrets, optional login item, `.app`, and drag-install DMG. Its automated tests do not replace live service testing: Discord was not installed on the first development Mac, and live Discord, Last.fm, and ListenBrainz behavior remains a manual beta gate.

Initial work was performed on Intel macOS 15.7.7. The bundle declares macOS 12.0 as its deployment target, but Apple-silicon, older-system, clean-account permission, signing, notarization, and Gatekeeper testing must be completed before stable support is considered.

## Shared Product Behavior

Windows and macOS intentionally share track normalization, privacy matching, game-mode process matching, remembered corrections, custom-art matching, and scrobble eligibility through `Shared/playback.py`. Fundamental user-visible behavior must be implemented and tested for both platforms; only native metadata, OS integration, and packaging should diverge by default.

## Out Of Scope

Android support is discontinued because its media-session, background-service, and Discord integration were too unstable to maintain as a supported product.

Linux remains out of scope because Amazon does not provide an official desktop app surface suitable for the same validated integration. Browser, PWA, and unofficial-wrapper approaches are not supported substitutes.
