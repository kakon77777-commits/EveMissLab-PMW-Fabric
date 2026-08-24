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

$config = [IO.Path]::GetFullPath($ConfigPath)
$wake = [IO.Path]::GetFullPath($WakeRoot)
if (-not $PidPath) {
    $PidPath = Join-Path (Split-Path -Parent $config) 'watchdog.pid.json'
}
$pidFile = [IO.Path]::GetFullPath($PidPath)
if (-not (Test-Path -LiteralPath $pidFile -PathType Leaf)) {
    Write-JsonAndExit @{ status = 'not_running'; pid_path = $pidFile } 0
}

try {
    $record = Get-Content -LiteralPath $pidFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $record.pid) { throw 'pid is missing' }
} catch {
    Write-JsonAndExit @{ error = @{ code = 'pid_record_invalid'; message = $_.Exception.Message } } 2
}
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$($record.pid)" -ErrorAction SilentlyContinue
if (-not $process) {
    if (-not $ValidateOnly) {
        $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
        Move-Item -LiteralPath $pidFile -Destination "$pidFile.stale.$stamp" -Force
    }
    Write-JsonAndExit @{ status = 'not_running'; pid = [int]$record.pid; stale_record = $true } 0
}
$command = [string]$process.CommandLine
if ($command -notmatch 'eml_wake' -or $command -notlike "*$wake*" -or $command -notlike "*$config*") {
    Write-JsonAndExit @{
        error = @{
            code = 'pid_identity_mismatch'
            message = 'PID exists but command line does not match the recorded watchdog'
            pid = [int]$record.pid
        }
    } 2
}
if ($ValidateOnly) {
    Write-JsonAndExit @{ status = 'running'; pid = [int]$record.pid; would_stop = $true } 0
}

Stop-Process -Id ([int]$record.pid) -ErrorAction Stop
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$archived = "$pidFile.stopped.$stamp"
Move-Item -LiteralPath $pidFile -Destination $archived -Force
Write-JsonAndExit @{ status = 'stopped'; pid = [int]$record.pid; archived_pid_record = $archived } 0
