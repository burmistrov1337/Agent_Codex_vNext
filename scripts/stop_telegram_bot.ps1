$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pidPath = Join-Path $repoRoot '.agent_codex\telegram\state\bot.pid'

$botProcesses = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and (
        $_.CommandLine -like "*$repoRoot*telegram-bot*" -or
        $_.CommandLine -like "*run_telegram_bot_foreground.ps1*"
    )
}

if ((-not (Test-Path $pidPath)) -and (-not $botProcesses)) {
    Write-Host 'Telegram bot is not running.'
    exit 0
}

$processIds = @()
if (Test-Path $pidPath) {
    $pidValue = (Get-Content $pidPath -Raw).Trim()
    if ($pidValue) {
        $processIds += [int]$pidValue
    }
}
$processIds += $botProcesses.ProcessId
$processIds = $processIds | Sort-Object -Unique

foreach ($processId in $processIds) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $processId -Force
        Write-Host "Stopped process PID: $processId"
    }
}

Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
