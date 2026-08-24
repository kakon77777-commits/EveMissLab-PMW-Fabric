param(
    [string]$PackageRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Python = 'python',
    [Parameter(Mandatory = $true)][string]$ConfigPath,
    [Parameter(Mandatory = $true)][string]$WakeRoot,
    [string]$PidPath = '',
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'

function Write-JsonAndExit([object]$Value, [int]$Code) {
    $Value | ConvertTo-Json -Depth 8 -Compress
    exit $Code
}

$package = [IO.Path]::GetFullPath($PackageRoot)
$config = [IO.Path]::GetFullPath($ConfigPath)
$wake = [IO.Path]::GetFullPath($WakeRoot)
$src = Join-Path $package 'src'
if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
    Write-JsonAndExit @{ error = @{ code = 'config_missing'; message = "config not found: $config" } } 2
}
if (-not (Test-Path -LiteralPath (Join-Path $src 'eml_wake') -PathType Container)) {
    Write-JsonAndExit @{ error = @{ code = 'package_missing'; message = "eml_wake source not found: $src" } } 2
}
if (-not $PidPath) {
    $PidPath = Join-Path (Split-Path -Parent $config) 'watchdog.pid.json'
}
$pidFile = [IO.Path]::GetFullPath($PidPath)

if (Test-Path -LiteralPath $pidFile -PathType Leaf) {
    try {
        $old = Get-Content -LiteralPath $pidFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($old.pid)" -ErrorAction SilentlyContinue
    } catch {
        Write-JsonAndExit @{ error = @{ code = 'pid_record_invalid'; message = $_.Exception.Message } } 2
    }
    if ($process -and $process.CommandLine -match 'eml_wake' -and $process.CommandLine -like "*$wake*") {
        Write-JsonAndExit @{ error = @{ code = 'watchdog_already_running'; pid = [int]$old.pid } } 3
    }
    if (-not $ValidateOnly) {
        $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
        Move-Item -LiteralPath $pidFile -Destination "$pidFile.stale.$stamp" -Force
    }
}

$arguments = @('-m', 'eml_wake', '--root', $wake, '--config', $config, 'watch')
$launchArguments = @($arguments | ForEach-Object {
    if ($_ -match '[\s"]') {
        '"' + ($_ -replace '"', '\"') + '"'
    } else {
        $_
    }
})
$ready = [ordered]@{
    status = 'ready'
    package_root = $package
    python = $Python
    module = 'eml_wake'
    config_path = $config
    wake_root = $wake
    pid_path = $pidFile
    window_style = 'Hidden'
    arguments = $arguments
}
if ($ValidateOnly) {
    Write-JsonAndExit $ready 0
}

$oldPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = if ($oldPythonPath) { "$src$([IO.Path]::PathSeparator)$oldPythonPath" } else { $src }
try {
    $process = Start-Process -FilePath $Python -ArgumentList $launchArguments -WorkingDirectory $package -WindowStyle Hidden -PassThru
} finally {
    $env:PYTHONPATH = $oldPythonPath
}
$record = [ordered]@{
    schema_version = 'eml-wake/pid-0.1'
    pid = $process.Id
    started_at = [DateTime]::UtcNow.ToString('o')
    python = $Python
    package_root = $package
    config_path = $config
    wake_root = $wake
    arguments = $arguments
}
$pidParent = Split-Path -Parent $pidFile
New-Item -ItemType Directory -Path $pidParent -Force | Out-Null
$record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $pidFile -Encoding UTF8
Write-JsonAndExit (@{ status = 'started'; pid = $process.Id; pid_path = $pidFile }) 0
