$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$stateRoot = Join-Path $repoRoot '.agent_codex\telegram\state'
$runScript = Join-Path $PSScriptRoot 'run_telegram_bot_foreground.ps1'
$pidPath = Join-Path $stateRoot 'bot.pid'
$stdoutLog = Join-Path $stateRoot 'bot_stdout.log'
$stderrLog = Join-Path $stateRoot 'bot_stderr.log'

New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null

if (-not (Test-Path $runScript)) {
    throw "Run script not found: $runScript"
}

$existingBotProcesses = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and (
        $_.CommandLine -like "*$repoRoot*telegram-bot*" -or
        $_.CommandLine -like "*run_telegram_bot_foreground.ps1*"
    )
}

if ($existingBotProcesses) {
    $existingIds = ($existingBotProcesses.ProcessId | Sort-Object -Unique) -join ', '
    Write-Host "Telegram bot already has active process(es): $existingIds"
    exit 0
}

if (Test-Path $pidPath) {
    Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
}

$process = Start-Process `
    -FilePath 'powershell.exe' `
    -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $runScript) `
    -WorkingDirectory $repoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

$process.Id | Set-Content -LiteralPath $pidPath -Encoding ascii
Start-Sleep -Seconds 2

$runningProcess = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
if (-not $runningProcess) {
    Write-Host 'Telegram bot did not stay alive in background.'
    Write-Host "STDOUT: $stdoutLog"
    Write-Host "STDERR: $stderrLog"
    exit 1
}

Write-Host "Telegram bot started in background. PID: $($process.Id)"
Write-Host "STDOUT: $stdoutLog"
Write-Host "STDERR: $stderrLog"
