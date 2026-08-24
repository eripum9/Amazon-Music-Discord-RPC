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
    foreach ($required in @("**Release notes smoke test.**", $generatedBlock, "This release publishes the Windows installer only", "This installer is not Authenticode signed")) {
        if (-not $notes.Contains($required)) {
            throw "Release notes output is missing: $required"
        }
    }
} finally {
    Remove-Item -LiteralPath $outputPath -Force -ErrorAction SilentlyContinue
}
