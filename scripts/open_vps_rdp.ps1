param(
    [string]$Host = "135.136.186.133",
    [string]$User = "agentcodex",
    [string]$KeyPath = "$HOME\.ssh\id_ed25519_agentcodex_vps",
    [int]$LocalPort = 3390
)

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$tunnelScript = Join-Path $scriptRoot "start_vps_rdp_tunnel.ps1"

Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-ExecutionPolicy", "Bypass",
    "-File", $tunnelScript,
    "-Host", $Host,
    "-User", $User,
    "-KeyPath", $KeyPath,
    "-LocalPort", $LocalPort
) -WindowStyle Normal

Start-Sleep -Seconds 3
Start-Process -FilePath "mstsc.exe" -ArgumentList "/v:127.0.0.1:$LocalPort"
