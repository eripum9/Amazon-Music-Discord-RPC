# Android Beta

This is the experimental Android build for Amazon Music RPC.

## Method

Android does not expose Discord desktop IPC. The beta uses a Discord Gateway WebSocket connection and sends presence updates through Gateway presence update payloads. This matches the general approach used by Kizzy, but the implementation here is new and does not copy Kizzy source.

The app does not scrape Discord login pages or extract tokens from WebView/localStorage. The beta requires manual token input and stores it locally in private app preferences.

## Metadata Source

The app reads Android media sessions through a notification listener service. Enable notification access for Amazon Music RPC from the app before starting RPC.

Default media package filters:

```text
com.amazon.mp3,com.amazon.music,com.pumpgunstudios.amazonmusicrpc.fakeamazon
```

The foreground services are explicit-start only. If Android kills them under emulator memory pressure, Android should not restart fake playback or RPC on its own.

## Build

From the repository root:

```powershell
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
$env:ANDROID_HOME="$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT=$env:ANDROID_HOME
gradle -p Android assembleDebug --no-daemon
```

Use Android Studio's bundled JBR/JDK. The current Kotlin/Gradle setup does not run under Java 26.

Debug APK:

```text
Android/app/build/outputs/apk/debug/app-debug.apk
```

Companion test APK:

```text
Android/fakeamazon/build/outputs/apk/debug/fakeamazon-debug.apk
```

## Local Metadata Test

Install both debug APKs on the emulator:

```powershell
$adb="$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
& $adb install -r Android\fakeamazon\build\outputs\apk\debug\fakeamazon-debug.apk
& $adb install -r Android\app\build\outputs\apk\debug\app-debug.apk
```

Install or update the companion app first so Android knows its signature-only test control permission.

Open Fake Amazon Music once and allow notifications. Then open Amazon Music RPC, open notification access, enable Amazon Music RPC, leave the Discord token empty, and press Start RPC. The status should show metadata-only mode.

The Amazon Music RPC app can control the companion test source from the Test metadata card:

- WOLF - Tyler, The Creator - Wolf
- Rusty - Tyler, The Creator - Wolf
- Noid - Tyler, The Creator - Chromakopia+

Use Clear Discord activity to clear stale Rich Presence when a local Discord token is saved. Stop RPC also attempts to clear the activity before shutting down.

## Album Art Lookup

The app first uses HTTP artwork exposed by the media session when available. If the session only exposes local bitmap artwork or no usable URL, it looks up album art through Deezer, then iTunes, then MusicBrainz/Cover Art Archive. Lookup prefers title, artist, and album matches but keeps the media-session album name in Discord text.

For Discord Rich Presence, arbitrary artwork URLs are proxied through Discord's application external-assets endpoint when a token is configured. If proxying fails, the raw public URL is sent as a fallback. Diagnostics show the image source and host without logging the token.
