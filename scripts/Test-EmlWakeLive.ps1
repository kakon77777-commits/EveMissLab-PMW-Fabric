param(
    [string]$PackageRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Python = 'python',
    [Parameter(Mandatory = $true)][string]$LiveRoot,
    [string]$ClaudeBinary = 'claude',
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'

function Write-JsonAndExit([object]$Value, [int]$Code) {
    $Value | ConvertTo-Json -Depth 8 -Compress
    exit $Code
}

$package = [IO.Path]::GetFullPath($PackageRoot)
$live = [IO.Path]::GetFullPath($LiveRoot)
$binaryLooksLikePath = [IO.Path]::IsPathRooted($ClaudeBinary) -or $ClaudeBinary.Contains('\') -or $ClaudeBinary.Contains('/')
if ($binaryLooksLikePath) {
    $claude = [IO.Path]::GetFullPath($ClaudeBinary)
} else {
    $claude = $ClaudeBinary
}
$src = Join-Path $package 'src'
if (-not (Test-Path -LiteralPath (Join-Path $src 'eml_wake') -PathType Container)) {
    Write-JsonAndExit @{ error = @{ code = 'package_missing'; message = "eml_wake source not found: $src" } } 2
}
if (-not (Test-Path -LiteralPath $live -PathType Container)) {
    Write-JsonAndExit @{ error = @{ code = 'live_root_missing'; message = "live root not found: $live" } } 2
}
if ($binaryLooksLikePath) {
    if (-not (Test-Path -LiteralPath $claude -PathType Leaf)) {
        Write-JsonAndExit @{ error = @{ code = 'claude_binary_missing'; message = "Claude binary not found: $claude" } } 2
    }
} elseif (-not (Get-Command $claude -ErrorAction SilentlyContinue)) {
    Write-JsonAndExit @{ error = @{ code = 'claude_binary_missing'; message = "Claude command not found: $claude" } } 2
}
$ready = [ordered]@{
    status = 'ready'
    package_root = $package
    live_root = $live
    claude_binary = $claude
    test = 'tests.test_wake_live_opt_in'
    provider_invoked = $false
}
if ($ValidateOnly) {
    Write-JsonAndExit $ready 0
}

$oldPythonPath = $env:PYTHONPATH
$oldLive = $env:EML_WAKE_LIVE
$oldRoot = $env:EML_WAKE_LIVE_ROOT
$oldClaude = $env:EML_WAKE_CLAUDE_BIN
$env:PYTHONPATH = if ($oldPythonPath) { "$src$([IO.Path]::PathSeparator)$oldPythonPath" } else { $src }
$env:EML_WAKE_LIVE = '1'
$env:EML_WAKE_LIVE_ROOT = $live
$env:EML_WAKE_CLAUDE_BIN = $claude
try {
    & $Python -m unittest tests.test_wake_live_opt_in -v
    $code = $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $oldPythonPath
    $env:EML_WAKE_LIVE = $oldLive
    $env:EML_WAKE_LIVE_ROOT = $oldRoot
    $env:EML_WAKE_CLAUDE_BIN = $oldClaude
}
if ($code -ne 0) {
    Write-JsonAndExit @{
        error = @{ code = 'live_probe_failed'; exit_code = $code }
        live_test_invoked = $true
        provider_invocation_status = 'unmeasured'
    } 1
}
Write-JsonAndExit @{
    status = 'passed'
    live_test_invoked = $true
    provider_invocation_status = 'verified_by_passing_live_test'
    test = 'tests.test_wake_live_opt_in'
} 0
