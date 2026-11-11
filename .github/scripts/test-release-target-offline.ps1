# MIT License - Copyright (c) 2026 eripum9
$ErrorActionPreference = 'Stop'
$global:sha = 'a' * 40
$global:other = 'b' * 40
$global:tagSha = 'c' * 40
$global:scenario = ''

function gh {
    $endpoint = $args[-1]
    $global:LASTEXITCODE = 0
    if ($endpoint -match '/commits/') {
        if ($global:scenario -eq 'bad-target-api') { $global:LASTEXITCODE = 1; return 'HTTP/2.0 500 Server Error' }
        $sha = if ($global:scenario -eq 'bad-target') { $global:other } else { $global:sha }
        return "HTTP/2.0 200 OK`nContent-Type: application/json`n`n{`"sha`":`"$sha`"}"
    }
    if ($endpoint -match '/git/ref/tags/') {
        if ($global:scenario -in @('missing', 'bad-target', 'bad-target-api')) { $global:LASTEXITCODE = 1; return 'HTTP/2.0 404 Not Found' }
        if ($global:scenario -eq 'api-error') { $global:LASTEXITCODE = 1; return 'HTTP/2.0 500 Server Error' }
        if ($global:scenario -eq 'malformed') { return 'not an HTTP response' }
        $type = if ($global:scenario -in @('annotated', 'bad-annotated')) { 'tag' } else { 'commit' }
        $sha = if ($global:scenario -in @('annotated', 'bad-annotated')) { $global:tagSha } elseif ($global:scenario -eq 'bad-tag') { $global:other } else { $global:sha }
        if ($global:scenario -eq 'crlf') { return "HTTP/2.0 200 OK`r`nContent-Type: application/json`r`n`r`n{`"object`":{`"type`":`"commit`",`"sha`":`"$sha`"}}" }
        return "HTTP/2.0 200 OK`nContent-Type: application/json`n`n{`"object`":{`"type`":`"$type`",`"sha`":`"$sha`"}}"
    }
    if ($endpoint -match '/git/tags/') {
        $sha = if ($global:scenario -eq 'bad-annotated') { $global:other } else { $global:sha }
        return "HTTP/2.0 200 OK`nContent-Type: application/json`n`n{`"object`":{`"type`":`"commit`",`"sha`":`"$sha`"}}"
    }
    throw "Unexpected endpoint: $endpoint"
}

foreach ($case in @(
    @{ Scenario = 'missing'; Target = ''; Pass = $true },
    @{ Scenario = 'missing'; Target = $global:sha; Pass = $true },
    @{ Scenario = 'matching'; Target = 'master'; Pass = $true },
    @{ Scenario = 'matching'; Target = 'v1.2.3'; Pass = $true },
    @{ Scenario = 'annotated'; Target = ''; Pass = $true },
    @{ Scenario = 'crlf'; Target = ''; Pass = $true },
    @{ Scenario = 'bad-annotated'; Target = ''; Pass = $false },
    @{ Scenario = 'malformed'; Target = ''; Pass = $false },
    @{ Scenario = 'bad-target'; Target = 'master'; Pass = $false },
    @{ Scenario = 'bad-target-api'; Target = 'master'; Pass = $false },
    @{ Scenario = 'bad-tag'; Target = ''; Pass = $false },
    @{ Scenario = 'api-error'; Target = ''; Pass = $false }
)) {
    $global:scenario = $case.Scenario
    $passed = $true
    try {
        & "$PSScriptRoot/test-release-target.ps1" -Repository 'owner/repo' -Tag 'v1.2.3' -BuiltSha $global:sha -DraftTarget $case.Target
    } catch { $passed = $false; $failure = $_.ToString() + ' ' + $_.ScriptStackTrace }
    if ($passed -ne $case.Pass) { throw "Unexpected result for $($case.Scenario), target '$($case.Target)': $failure" }
}
$global:LASTEXITCODE = 0
