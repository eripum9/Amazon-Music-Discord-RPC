# macOS Permissions, Signing, and Distribution

This document describes the direct-download prototype on macOS 15.7.7. The
prototype is not an App Store build and is deliberately **not App Sandbox
enabled**. Its stable bundle identifier is
`io.github.eripum9.amazon-music-rpc`.

## Permission summary

The normal Discord presence and DevTools metadata path should not show a macOS
privacy (TCC) prompt. The application does not need Accessibility, Automation,
Screen Recording, Input Monitoring, Full Disk Access, Media & Apple Music,
Microphone, Camera, Contacts, or Location access.

| Capability | macOS approval | Notes |
| --- | --- | --- |
| Amazon Music metadata over DevTools | None | The app connects only to a random high port on `127.0.0.1`. It verifies that the listener belongs to the signed `com.amazon.music` app before using it. |
| Start/restart Amazon Music in DevTools mode | None expected | The explicit restart action signals only verified Amazon Music processes owned by the current user, then launches the exact signed executable with loopback-only flags. It does not use Apple Events, System Events, Accessibility, or debugger attachment. |
| Disable DevTools listener and reopen normally | None expected | This separate, confirmed action interrupts playback, signals only reverified Amazon Music processes, and relaunches the exact signed executable without debugging flags. Merely turning off the RPC checkbox does not alter an already-running Amazon process. |
| Now Playing fallback | None expected | `/usr/bin/osascript` runs JavaScript that reads the local Now Playing object. It does not send Apple Events to Amazon Music, so Automation permission is not requested. This private-framework compatibility path may stop working on a future macOS release. |
| Discord Rich Presence | None | Discord IPC uses a Unix-domain socket in the current user's runtime directories. It does not require inbound network or Local Network access. |
| Last.fm, ListenBrainz, artwork, and updates | Internet connection only | A non-sandboxed direct-download app needs no network entitlement for outbound HTTPS. The macOS application firewall should not ask because Amazon Music RPC does not accept inbound connections. |
| Last.fm and ListenBrainz secrets | Keychain access may be shown | Secrets are stored as generic passwords in the user's login Keychain. macOS can ask the user to unlock the Keychain or allow access. Denying this prevents persistent scrobbler credentials, but does not grant the app broader data access. |
| Start at login | User-controlled background item | Enabling this option installs a per-user LaunchAgent in `~/Library/LaunchAgents`. macOS may show a “Background Items Added” notification, and the user can disable it under **System Settings > General > Login Items**. This is not Accessibility or Full Disk Access. |
| Settings import/export and diagnostics export | User-selected file only | Native open/save dialogs establish the selected location. The app does not scan Desktop, Documents, Downloads, other app containers, or the full disk. |
| Notifications | Optional user approval if enabled | A future Notification Center banner may trigger the standard Notifications prompt. Denial should affect banners only, not presence or scrobbling. Tray/menu-bar state itself needs no permission. |

Loopback traffic is not traffic to a broadcast-capable Wi-Fi or Ethernet local
network. The prototype therefore does not declare `NSLocalNetworkUsageDescription`
and should not appear in **Privacy & Security > Local Network**. It also never
binds the RPC application itself to a listening TCP port; the verified Amazon
Music process owns the opt-in DevTools listener.

If a macOS release unexpectedly asks for any permission not listed above, deny
it first and file a diagnostic report. Core metadata and Discord operation must
not depend on broad privacy access.

## Entitlements

[`entitlements.plist`](entitlements.plist) is intentionally empty. The app is
distributed outside the Mac App Store, so App Sandbox is optional. Enabling it
for this prototype would require a separate design and test pass for process
inspection, child-process launch, Keychain access, login items, Discord IPC,
and the Now Playing fallback.

The build does **not** request any of these weakened hardened-runtime
entitlements:

- `com.apple.security.cs.allow-jit`
- `com.apple.security.cs.allow-unsigned-executable-memory`
- `com.apple.security.cs.disable-library-validation`
- `com.apple.security.cs.allow-dyld-environment-variables`
- `com.apple.security.cs.debugger`
- `com.apple.security.get-task-allow`

Amazon Music itself carries several Chromium/JIT entitlements, but Amazon Music
RPC does not embed Chromium, inject code, attach a debugger, or load code into
Amazon Music. Copying Amazon's entitlements would unnecessarily weaken the RPC
application and can make notarization fail.

The app also does not declare the Apple Events entitlement or an
`NSAppleEventsUsageDescription`, because no runtime path sends Apple Events to
another application. Add those only if a future feature actually automates an
application and is designed to handle explicit user consent.

## Prototype signing behavior

`scripts/build_app.sh` always asks PyInstaller to sign the complete bundle:

- With no `MACOS_CODESIGN_IDENTITY`, PyInstaller applies an ad-hoc signature.
  This is suitable for local development but not public distribution.
- With `MACOS_CODESIGN_IDENTITY` set to a valid **Developer ID Application**
  identity, PyInstaller signs nested code and the app with hardened runtime and
  a secure timestamp. The script fails if strict signature verification fails.

The resulting architecture is inherited from the build Python and all compiled
wheels. The first verified build host is Intel (`x86_64`). Build separately with
a native arm64 Python and arm64 wheels for Apple silicon, or introduce a tested
universal2 release pipeline; changing `target_arch` does not manufacture a
missing architecture in third-party binaries.

The runtime pins PySide6 Essentials 6.9.3. Direct Mach-O inspection of the
`x86_64` and `arm64` slices in `QtCore.abi3.so`, `Shiboken.abi3.so`, and
`QtCore.framework` found a deployment minimum of macOS 12.0 in all six slices.
The corresponding 6.10.3 binding modules require macOS 15.0 despite their wheel
metadata, so 6.9.3 is the newest tested Qt-for-Python line compatible with the
declared macOS 12.0 minimum.

`LSUIElement` is enabled because the prototype is a menu-bar utility. It does
not keep a Dock or Command-Tab icon running in the background; Settings and
Diagnostics remain available from the menu-bar item. The original 1024px
Windows artwork is still used for the `.app`, Finder, DMG, and menu-bar icon.

Ad-hoc builds are not notarizable and Gatekeeper can block them after download.
Do not label the prototype DMG as a generally distributable release until a
Developer ID build has passed notarization and clean-machine tests.

## Developer ID and notarization workflow

The scripts never store an Apple ID password or App Store Connect key in the
repository. A release operator should provision credentials in the login
Keychain and then run:

```bash
export MACOS_CODESIGN_IDENTITY='Developer ID Application: Your Name (TEAMID)'
MacOS/scripts/build_app.sh

xcrun notarytool store-credentials amazon-music-rpc-notary
export MACOS_NOTARYTOOL_PROFILE='amazon-music-rpc-notary'
MacOS/scripts/create_dmg.sh
```

When both variables are present, `create_dmg.sh` signs the DMG, submits it with
`notarytool --wait`, staples the accepted ticket, and validates the ticket. The
DMG build itself is noninteractive: `dmgbuild` writes the Finder icon layout and
the `/Applications` symlink without automating Finder. Every successful build
atomically produces these two exact release assets; upload both to the same
GitHub release:

- `Amazon-Music-RPC.dmg`
- `Amazon-Music-RPC.dmg.sha256`

The checksum is generated only after signing and optional ticket stapling, so
it matches the final DMG bytes consumed by the automatic updater.

Before publishing a release, also test these manually on a clean macOS account
or virtual machine:

1. `codesign --verify --deep --strict --verbose=2 "Amazon Music RPC.app"`
2. `spctl --assess --type execute --verbose=2 "Amazon Music RPC.app"`
3. `xcrun stapler validate "Amazon-Music-RPC.dmg"`
4. Mount the DMG, drag the app into Applications, eject it, and launch the
   installed copy.
5. Exercise Keychain denial/approval, start-at-login enable/disable, Amazon
   Music restart consent, Discord absence/reconnection, and both scrobblers.

Do not add `com.apple.security.get-task-allow` to a release. Apple explicitly
rejects notarization submissions that carry it.

## References

- [Apple: Notarizing macOS software before distribution](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [Apple: Customizing the notarization workflow](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow)
- [Apple: Preparing your app for distribution](https://developer.apple.com/documentation/xcode/preparing-your-app-for-distribution)
- [Apple: App Sandbox](https://developer.apple.com/documentation/security/app-sandbox)
- [Apple: Apple Events entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.automation.apple-events)
- [Apple: `NSAppleEventsUsageDescription`](https://developer.apple.com/documentation/bundleresources/information-property-list/nsappleeventsusagedescription)
- [Apple: Understanding Local Network Privacy](https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy)
- [Apple: Privacy & Security settings on Mac](https://support.apple.com/guide/mac-help/change-privacy-security-settings-on-mac-mchl211c911f/mac)
