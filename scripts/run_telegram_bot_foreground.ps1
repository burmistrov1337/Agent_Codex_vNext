$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

$pythonCandidates = @(
    $env:AGENT_CODEX_PYTHON,
    (Join-Path $repoRoot '.venv\Scripts\python.exe'),
    (Join-Path $repoRoot 'venv\Scripts\python.exe'),
    (Join-Path $env:USERPROFILE 'AppData\Local\Programs\Python\Python312\python.exe'),
    'py'
)

$python = $null
foreach ($candidate in $pythonCandidates) {
    if (-not $candidate) {
        continue
    }
    if ($candidate -eq 'py') {
        $python = $candidate
        break
    }
    if (Test-Path $candidate) {
        $python = $candidate
        break
    }
}

if (-not $python) {
    $python = 'python'
}

$env:PYTHONPATH = Join-Path $repoRoot 'src'
Set-Location $repoRoot

Write-Host "Starting Agent_Codex vNext Telegram bot in foreground mode..."
if ($python -eq 'py') {
    & py -3.12 -m agent_codex.apps.cli.main telegram-bot --project-root $repoRoot
} else {
    & $python -m agent_codex.apps.cli.main telegram-bot --project-root $repoRoot
}
if ($LASTEXITCODE -ne 0) {
    throw "Telegram bot process finished with exit code $LASTEXITCODE"
}
