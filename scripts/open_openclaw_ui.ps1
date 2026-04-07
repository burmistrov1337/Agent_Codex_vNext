param(
    [string]$ServerHost = "135.136.186.133",
    [string]$User = "agentcodex",
    [string]$KeyPath = "$HOME\.ssh\id_ed25519_agentcodex_vps",
    [int]$LocalPort = 18789
)

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$tunnelScript = Join-Path $scriptRoot "start_openclaw_ui_tunnel.ps1"

$tunnelOutput = powershell -ExecutionPolicy Bypass -File $tunnelScript `
    -ServerHost $ServerHost `
    -User $User `
    -KeyPath $KeyPath `
    -LocalPort $LocalPort

$tunnelOutput | ForEach-Object { Write-Host $_ }

Start-Process -FilePath "http://127.0.0.1:$LocalPort"
