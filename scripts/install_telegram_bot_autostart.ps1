$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$startScript = Join-Path $PSScriptRoot 'start_telegram_bot.ps1'
$taskName = 'Agent_Codex_vNext_TelegramBot'

if (-not (Test-Path $startScript)) {
    throw "Start script not found: $startScript"
}

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description 'Start Agent_Codex vNext Telegram bot at logon.' `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $taskName
Write-Host "Autostart task installed: $($task.TaskName)"
