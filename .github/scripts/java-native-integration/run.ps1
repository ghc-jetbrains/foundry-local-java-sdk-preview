# Copyright (c) Microsoft Corporation. Licensed under the MIT License.
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('win-x64', 'win-arm64', 'linux-x64', 'linux-arm64', 'osx-arm64')]
    [string]$Target,
    [Parameter(Mandatory = $true)]
    [string]$SourceDirectory,
    [Parameter(Mandatory = $true)]
    [string]$SourceRef,
    [Parameter(Mandatory = $true)]
    [string]$ResultDirectory
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command exited with code $LASTEXITCODE."
    }
}

$started = [Diagnostics.Stopwatch]::StartNew()
$result = [ordered]@{
    target = $Target
    status = 'failed'
    sourceRef = $SourceRef
    sourceSha = $null
    sdkJarSha256 = $null
    runtime = $null
    model = $null
    test = 'not-run'
    durationSeconds = 0
    error = $null
}
$scriptRoot = $PSScriptRoot
$source = (Resolve-Path -LiteralPath $SourceDirectory).Path
$pom = Join-Path $source 'sdk_v2/java/pom.xml'
$javaTarget = Join-Path $source 'sdk_v2/java/target'
$build = Join-Path $javaTarget "native-integration/$Target"
$runtime = Join-Path $build 'runtime'
$downloads = Join-Path $build 'downloads'
$modelCache = Join-Path $build 'model-cache'
$appData = Join-Path $build 'app-data'
$classes = Join-Path $build 'classes'
$dependencyClasspathFile = Join-Path $build 'runtime-classpath.txt'
$runtimeEvidence = Join-Path $build 'runtime.json'
$modelEvidence = Join-Path $build 'model.json'
$resultPath = Join-Path $ResultDirectory "$Target.json"

try {
    if (-not (Test-Path -LiteralPath $pom -PathType Leaf)) {
        throw "Java SDK POM is missing from the selected source ref."
    }
    $sourceSha = (& git -C $source rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $sourceSha -notmatch '^[0-9a-f]{40}$') {
        throw "Could not resolve the selected Java SDK source SHA."
    }
    $result.sourceSha = $sourceSha

    if (Test-Path -LiteralPath $build) {
        Remove-Item -LiteralPath $build -Recurse -Force
    }
    New-Item -ItemType Directory -Path $ResultDirectory -Force | Out-Null

    Invoke-Checked mvn @(
        '--batch-mode',
        '--no-transfer-progress',
        '-f', $pom,
        '-Drevision=0.1.0-integration',
        '-DskipTests',
        'clean', 'package'
    )
    $jars = @(Get-ChildItem -LiteralPath $javaTarget -Filter 'foundry-local-sdk-*.jar' |
        Where-Object { $_.Name -notlike '*-sources.jar' })
    if ($jars.Count -ne 1) {
        throw "Expected exactly one Java SDK JAR, found $($jars.Count)."
    }
    $jar = $jars[0].FullName
    $result.sdkJarSha256 = (Get-FileHash -LiteralPath $jar -Algorithm SHA256).Hash.ToLowerInvariant()
    New-Item -ItemType Directory -Path $classes -Force | Out-Null

    Invoke-Checked python @(
        (Join-Path $scriptRoot 'prepare_runtime.py'),
        '--target', $Target,
        '--runtime-dir', $runtime,
        '--download-dir', $downloads,
        '--output', $runtimeEvidence
    )

    Invoke-Checked mvn @(
        '--batch-mode',
        '--no-transfer-progress',
        '-f', $pom,
        '-DincludeScope=runtime',
        "-Dmdep.outputFile=$dependencyClasspathFile",
        'org.apache.maven.plugins:maven-dependency-plugin:3.8.1:build-classpath'
    )
    if (-not (Test-Path -LiteralPath $dependencyClasspathFile -PathType Leaf)) {
        throw "Maven did not produce the SDK runtime classpath."
    }
    $dependencies = (Get-Content -LiteralPath $dependencyClasspathFile -Raw).Trim()
    if (-not $dependencies) {
        throw "The SDK runtime classpath is empty."
    }
    $separator = [IO.Path]::PathSeparator
    $classpath = "$jar$separator$dependencies"
    Invoke-Checked javac @(
        '-encoding', 'UTF-8',
        '-cp', $classpath,
        '-d', $classes,
        (Join-Path $scriptRoot 'ModelPreparer.java')
    )

    $prepareClasspath = "$classes$separator$classpath"
    $modelId = (Get-Content (Join-Path $scriptRoot 'model-lock.json') -Raw |
        ConvertFrom-Json).id
    $delays = @(0, 15, 45)
    $prepared = $false
    for ($attempt = 0; $attempt -lt $delays.Count; $attempt++) {
        if ($delays[$attempt] -gt 0) {
            Start-Sleep -Seconds $delays[$attempt]
        }
        & java -cp $prepareClasspath ModelPreparer $runtime $modelCache $appData $modelId
        if ($LASTEXITCODE -eq 0) {
            $prepared = $true
            break
        }
        Write-Warning "Model preparation attempt $($attempt + 1) failed."
    }
    if (-not $prepared) {
        throw "Model preparation failed after three attempts."
    }

    Invoke-Checked python @(
        (Join-Path $scriptRoot 'verify_model.py'),
        '--cache', $modelCache,
        '--target', $Target,
        '--output', $modelEvidence
    )

    $wav = Join-Path $source 'sdk_v2/testdata/Recording.wav'
    Invoke-Checked mvn @(
        '--batch-mode',
        '--no-transfer-progress',
        '-f', $pom,
        '-Drevision=0.1.0-integration',
        '-Dtest=NativeAsrTest',
        "-Dfoundry.test.runtime=$runtime",
        "-Dfoundry.test.cache=$modelCache",
        "-Dfoundry.test.wav=$wav",
        "-Dfoundry.test.model=$modelId",
        'test'
    )

    $result.runtime = Get-Content -LiteralPath $runtimeEvidence -Raw | ConvertFrom-Json
    $result.model = Get-Content -LiteralPath $modelEvidence -Raw | ConvertFrom-Json
    $result.test = 'NativeAsrTest'
    $result.status = 'passed'
}
catch {
    $result.error = $_.Exception.Message
    Write-Host "::error::$($result.error)"
}
finally {
    $started.Stop()
    $result.durationSeconds = [Math]::Round($started.Elapsed.TotalSeconds, 1)
    New-Item -ItemType Directory -Path $ResultDirectory -Force | Out-Null
    [IO.File]::WriteAllText(
        $resultPath,
        (($result | ConvertTo-Json -Depth 8) + "`n"),
        [Text.UTF8Encoding]::new($false)
    )
}

if ($result.status -ne 'passed') {
    exit 1
}
