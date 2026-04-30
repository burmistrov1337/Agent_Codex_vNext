param(
    [switch]$ServerMode
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
}

.\.venv\Scripts\pip.exe install -r max_bot/requirements.txt | Out-Host

if ($ServerMode) {
    $env:MAX_APP_ENV = "server"
} else {
    $env:MAX_APP_ENV = "local"
}

.\.venv\Scripts\python.exe -m max_bot.register_webhook
