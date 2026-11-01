# MIT License - Copyright (c) 2026 eripum9
param(
    [Parameter(Mandatory)] [string] $Repository,
    [Parameter(Mandatory)] [string] $Tag,
    [Parameter(Mandatory)] [string] $BuiltSha,
    [string] $DraftTarget
)

$ErrorActionPreference = 'Stop'

function Get-GhJson([string] $Endpoint, [bool] $AllowMissing = $false) {
    $response = @(gh api --include $Endpoint 2>&1)
    $code = $LASTEXITCODE
    $text = $response -join "`n"
    if ($code -ne 0) {
        if ($AllowMissing -and $text -match '(?m)^HTTP/\S+ 404(?:\s|$)') { return $null }
        throw "GitHub API request failed for $Endpoint (exit $code): $text"
    }
    if ($text -notmatch '(?s)^HTTP/\S+ 2\d\d[^\n]*\n.*?\r?\n\r?\n(.*)$') {
        throw "Invalid GitHub API response for $Endpoint."
    }
    return ($Matches[1] | ConvertFrom-Json -ErrorAction Stop)
}

function Assert-Commit([string] $Sha, [string] $Description) {
    if ($Sha -notmatch '^[0-9a-fA-F]{40}$' -or $Sha -ine $BuiltSha) {
        throw "$Description does not resolve to built commit $BuiltSha (got $Sha)."
    }
}

if ($BuiltSha -notmatch '^[0-9a-fA-F]{40}$') { throw 'Built SHA must be a full commit SHA.' }
if ($DraftTarget) {
    $encodedTarget = [uri]::EscapeDataString($DraftTarget)
    $commit = Get-GhJson "repos/$Repository/commits/$encodedTarget"
    Assert-Commit $commit.sha 'Draft target'
}

$encodedTag = [uri]::EscapeDataString($Tag)
$ref = Get-GhJson "repos/$Repository/git/ref/tags/$encodedTag" $true
if ($null -ne $ref) {
    $object = $ref.object
    $seen = @{}
    while ($object.type -eq 'tag') {
        if ($object.sha -notmatch '^[0-9a-fA-F]{40}$' -or $seen.ContainsKey($object.sha) -or $seen.Count -ge 20) {
            throw 'Invalid or cyclic annotated tag.'
        }
        $seen[$object.sha] = $true
        $tagObject = Get-GhJson "repos/$Repository/git/tags/$($object.sha)"
        $object = $tagObject.object
    }
    if ($object.type -ne 'commit') { throw 'Tag does not resolve to a commit.' }
    Assert-Commit $object.sha 'Tag'
}
