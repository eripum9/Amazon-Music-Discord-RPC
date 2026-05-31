$ErrorActionPreference = "Stop"

$studioJbr = "C:\Program Files\Android\Android Studio\jbr"
if (Test-Path $studioJbr) {
    $env:JAVA_HOME = $studioJbr
}

if (-not $env:ANDROID_HOME) {
    $env:ANDROID_HOME = Join-Path $env:LOCALAPPDATA "Android\Sdk"
}

$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
gradle -p $PSScriptRoot hostCheck --no-daemon
