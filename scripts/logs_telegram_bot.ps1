param(
    [switch]$Follow
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$stateRoot = Join-Path $repoRoot '.agent_codex\telegram\state'
$stdoutLog = Join-Path $stateRoot 'bot_stdout.log'
$stderrLog = Join-Path $stateRoot 'bot_stderr.log'

Write-Host "STDOUT log: $stdoutLog"
if (Test-Path $stdoutLog) {
    if ($Follow) {
        Get-Content $stdoutLog -Tail 20 -Wait
    } else {
        Get-Content $stdoutLog -Tail 20
    }
} else {
    Write-Host '(stdout log has not been created yet)'
}

Write-Host ''
Write-Host "STDERR log: $stderrLog"
if (Test-Path $stderrLog) {
    if ($Follow) {
        Get-Content $stderrLog -Tail 20 -Wait
    } else {
        Get-Content $stderrLog -Tail 20
    }
} else {
    Write-Host '(stderr log has not been created yet)'
}
