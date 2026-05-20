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
gradle -p Android assembleDebug --no-daemon
```

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

Open Fake Amazon Music, allow notifications, and press Start fake playback. Then open Amazon Music RPC, open notification access, enable Amazon Music RPC, leave the Discord token empty, and press Start RPC. The status should show the fake track in metadata-only mode.
