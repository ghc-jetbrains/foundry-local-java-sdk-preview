# Copyright (c) Microsoft Corporation. Licensed under the MIT License.
param(
    [Parameter(Mandatory = $true)]
    [string]$Repository,
    [Parameter(Mandatory = $true)]
    [string]$Failed,
    [Parameter(Mandatory = $true)]
    [string]$IssueBody,
    [Parameter(Mandatory = $true)]
    [string]$CommentBody
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$title = '[Dictation integration] Java native qualification failed'
$label = 'dictation-native-integration'

& gh label create $label --repo $Repository --color '5319e7' `
    --description 'Tracks failures in the five-platform Java native integration workflow' --force
if ($LASTEXITCODE -ne 0) {
    throw "Could not create or update the integration label."
}

$open = & gh issue list --repo $Repository --state open --label $label --limit 100 --json number,title
if ($LASTEXITCODE -ne 0) {
    throw "Could not list integration issues."
}
$matches = @($open | ConvertFrom-Json | Where-Object { $_.title -eq $title })
if ($matches.Count -gt 1) {
    throw "Multiple open integration issues have the stable title."
}
$existing = if ($matches.Count -eq 1) { $matches[0] } else { $null }
$isFailed = $Failed -eq 'true'

if ($isFailed) {
    if ($null -eq $existing) {
        $payload = @{
            title = $title
            body = Get-Content -LiteralPath $IssueBody -Raw
            labels = @($label)
            type = 'Bug'
        } | ConvertTo-Json -Depth 4
        $payload | & gh api --method POST "repos/$Repository/issues" `
            -H 'X-GitHub-Api-Version: 2026-03-10' --input -
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create the integration issue."
        }
    }
    else {
        $payload = @{
            body = Get-Content -LiteralPath $CommentBody -Raw
        } | ConvertTo-Json
        $payload | & gh api --method POST "repos/$Repository/issues/$($existing.number)/comments" --input -
        if ($LASTEXITCODE -ne 0) {
            throw "Could not comment on the integration issue."
        }
    }
}
elseif ($null -ne $existing) {
    $payload = @{
        body = (Get-Content -LiteralPath $CommentBody -Raw) +
            "`nThe complete five-platform qualification recovered, so this issue is closing automatically.`n"
    } | ConvertTo-Json
    $payload | & gh api --method POST "repos/$Repository/issues/$($existing.number)/comments" --input -
    if ($LASTEXITCODE -ne 0) {
        throw "Could not add the recovery comment."
    }
    '{"state":"closed","state_reason":"completed"}' |
        & gh api --method PATCH "repos/$Repository/issues/$($existing.number)" --input -
    if ($LASTEXITCODE -ne 0) {
        throw "Could not close the recovered integration issue."
    }
}
