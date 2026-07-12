param(
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$Summary,
    [Parameter(Mandatory = $true)][AllowEmptyString()][string[]]$GeneratedNotes,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [Parameter(Mandatory = $true)][bool]$Signed
)

$generatedText = $GeneratedNotes -join [Environment]::NewLine

$signingText = if ($Signed) {
    "The Windows executable and installer were code-signed and verified during the release workflow."
} else {
    "This draft is unsigned because no Windows code-signing certificate was configured. Windows SmartScreen may display a warning."
}

$body = @"
Discord Rich Presence integration for Amazon Music.
Displays your currently playing track, artist, album name, album art, and elapsed
time directly on your Discord profile.

**$Summary**

## Enhanced Metadata Compatibility

Enhanced metadata on Windows is built and tested for the Microsoft Store version of Amazon Music. The website installer may reject the metadata launch flag. If that happens, install Amazon Music from the Microsoft Store or disable **Enhanced Amazon metadata** and use fallback mode.

## Changes

$generatedText

## Installation

Download `AmazonMusicRPC_Setup.exe` and `AmazonMusicRPC_Setup.exe.sha256` from the assets below, verify the checksum, then run the installer. No Python installation is required.

$signingText

## Build Provenance

This draft was built from the current `master` commit by the manually triggered GitHub release workflow. Verify the installer with `gh attestation verify AmazonMusicRPC_Setup.exe -R eripum9/Amazon-Music-Discord-RPC`.

## Requirements

- Windows 10 or 11 (64-bit)
- Discord desktop app running
- Amazon Music for Windows; the Microsoft Store version is recommended for enhanced metadata
"@

Set-Content -LiteralPath $OutputPath -Value $body -Encoding utf8NoBOM
