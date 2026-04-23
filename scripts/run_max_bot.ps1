param(
    [switch]$DebugUpdates,
    [switch]$ServerMode
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".\\.venv\\Scripts\\python.exe")) {
    python -m venv .venv
}

.\\.venv\\Scripts\\pip.exe install -r max_bot/requirements.txt | Out-Host

if ($DebugUpdates) {
    $env:MAX_DEBUG_UPDATES = "1"
}

if ($ServerMode) {
    $env:MAX_APP_ENV = "server"
    Write-Host "MAX_APP_ENV=server"
} else {
    $env:MAX_APP_ENV = "local"
    Write-Host "MAX_APP_ENV=local"
}

$old = Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'max_bot.main' }
foreach ($p in $old) {
    try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {}
}

.\\.venv\\Scripts\\python.exe -m max_bot.main
