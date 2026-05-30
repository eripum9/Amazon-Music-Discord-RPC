# Android Beta Status

Android support is experimental and lives on the `beta/androidbuild` branch.

Windows releases from `master` are still the stable product. The Android beta is not included in the Windows installer and should not be treated as a finished release yet.

## Current Goal

The Android beta is testing whether Amazon Music style Discord Rich Presence can work on Android without the Windows Discord IPC path.

Current beta focus:

- Android notification metadata reading
- Discord activity publishing from Android
- Fake Amazon test app for repeatable emulator testing
- Time bar support
- Album, artwork, and duration fallback behavior
- Service lifetime behavior when Android kills or restarts background apps

## Where The Code Lives

Branch:

https://github.com/eripum9/Amazon-Music-Discord-RPC/tree/beta/androidbuild

Main folders on that branch:

- `Android/app/` for the Android RPC app
- `Android/fakeamazon/` for the fake Amazon Music test app

## Testing Status

The beta can be tested in Android Studio with an emulator. The fake Amazon app is used when a physical Android phone or real Amazon Music playback is not available.

The Android beta is expected to change quickly. Report Android issues with the Android beta issue template and include:

- Branch or commit
- Emulator or device model
- Android API level
- Whether the fake Amazon test app or real Amazon Music was used
- Steps to reproduce
- Redacted logs or screenshots

Do not post Discord tokens, account names, or unredacted notification screenshots.

## Stable Windows Users

If you only want the stable Windows app, use the latest Windows installer from Releases:

https://github.com/eripum9/Amazon-Music-Discord-RPC/releases/latest
