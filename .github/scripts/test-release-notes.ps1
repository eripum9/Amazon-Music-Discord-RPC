$outputPath = [IO.Path]::GetTempFileName()

try {
    $generatedNotes = @(
        "## What's Changed"
        "* First change"
        "* Second change"
    )
    & "$PSScriptRoot/new-release-notes.ps1" -Version "5.0.0" -Summary "Release notes smoke test." -GeneratedNotes $generatedNotes -OutputPath $outputPath
    $notes = Get-Content -LiteralPath $outputPath -Raw
    $generatedBlock = $generatedNotes -join [Environment]::NewLine
    foreach ($required in @("**Release notes smoke test.**", $generatedBlock, "This release publishes the Windows installer only", "This installer is not Authenticode signed", '`AmazonMusicRPC_Setup.exe`', '`AmazonMusicRPC_Setup.exe.sha256`', '`master`', '`gh attestation verify AmazonMusicRPC_Setup.exe -R eripum9/Amazon-Music-Discord-RPC`')) {
        if (-not $notes.Contains($required)) {
            throw "Release notes output is missing: $required"
        }
    }
    $summary = 'It''s literal $(throw "must not execute")' + "`n" + 'Second line $env:PATH'
    & "$PSScriptRoot/new-release-notes.ps1" -Version '5.0.0' -Summary $summary -GeneratedNotes $generatedNotes -OutputPath $outputPath
    $notes = Get-Content -LiteralPath $outputPath -Raw
    if (-not $notes.Contains($summary)) { throw 'Multiline literal summary was not preserved.' }
} finally {
    Remove-Item -LiteralPath $outputPath -Force -ErrorAction SilentlyContinue
}
