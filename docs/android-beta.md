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

## Repeatable Emulator Test Path

Build both debug APKs from the `beta/androidbuild` branch:

```powershell
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
$env:ANDROID_HOME="$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT=$env:ANDROID_HOME
gradle -p Android assembleDebug --no-daemon
```

Install:

- `Android/app/build/outputs/apk/debug/app-debug.apk`
- `Android/fakeamazon/build/outputs/apk/debug/fakeamazon-debug.apk`

Minimum emulator test:

1. Start the Android RPC app.
2. Start the fake Amazon test app.
3. Send the WOLF, Rusty, and Noid test tracks.
4. Confirm Discord shows title, artist, album, elapsed time, and duration.
5. Test pause, resume, seek forward, seek backward, artwork toggle, and duration toggle.
6. Stop playback and confirm Discord clears or returns to the expected idle state.
7. Let the emulator idle long enough to confirm Android service behavior is documented.

## Beta Exit Criteria

Android should stay on `beta/androidbuild` until:

- A second tester can follow the emulator test path without extra setup notes.
- The fake Amazon app can test metadata, time bar, pause, seek, artwork, duration, and stop behavior.
- Real Amazon Music notification behavior is tested on at least one physical Android device or clearly documented as not yet tested.
- Known service lifetime limits are documented.
- The beta can produce APKs from a clean checkout.

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
