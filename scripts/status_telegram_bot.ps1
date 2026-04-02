$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$stateRoot = Join-Path $repoRoot '.agent_codex\telegram\state'
$pidPath = Join-Path $stateRoot 'bot.pid'
$stdoutLog = Join-Path $stateRoot 'bot_stdout.log'
$stderrLog = Join-Path $stateRoot 'bot_stderr.log'

if (-not (Test-Path $pidPath)) {
    Write-Host 'Telegram bot is not running right now.'
    if (Test-Path $stdoutLog) {
        Write-Host "Last stdout log: $stdoutLog"
    }
    if (Test-Path $stderrLog) {
        Write-Host "Last stderr log: $stderrLog"
    }
    exit 0
}

$pidValue = (Get-Content $pidPath -Raw).Trim()
$process = if ($pidValue) { Get-Process -Id $pidValue -ErrorAction SilentlyContinue } else { $null }

if (-not $process) {
    Write-Host "PID file exists, but process $pidValue is not active."
    Write-Host 'Restart the bot with start_telegram_bot.ps1.'
    exit 1
}

Write-Host "Telegram bot is active. PID: $pidValue"
Write-Host "STDOUT: $stdoutLog"
Write-Host "STDERR: $stderrLog"
Write-Host ''
Write-Host 'Last stdout lines:'
if (Test-Path $stdoutLog) {
    Get-Content $stdoutLog -Tail 10
} else {
    Write-Host '(stdout log has not been created yet)'
}

Write-Host ''
Write-Host 'Last stderr lines:'
if (Test-Path $stderrLog) {
    Get-Content $stderrLog -Tail 10
} else {
    Write-Host '(stderr log has not been created yet)'
}
