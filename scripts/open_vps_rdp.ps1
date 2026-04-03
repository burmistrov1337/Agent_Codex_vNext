param(
    [string]$ServerHost = "135.136.186.133",
    [string]$User = "agentcodex",
    [string]$KeyPath = "$HOME\.ssh\id_ed25519_agentcodex_vps",
    [int]$LocalPort = 3390
)

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$tunnelScript = Join-Path $scriptRoot "start_vps_rdp_tunnel.ps1"
$profileScript = Join-Path $scriptRoot "create_vps_rdp_profile.ps1"

Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-ExecutionPolicy", "Bypass",
    "-File", $tunnelScript,
    "-ServerHost", $ServerHost,
    "-User", $User,
    "-KeyPath", $KeyPath,
    "-LocalPort", $LocalPort
) -WindowStyle Normal

Start-Sleep -Seconds 3
$rdpPath = powershell -ExecutionPolicy Bypass -File $profileScript -LocalPort $LocalPort -User $User
$rdpPath = ($rdpPath | Select-Object -Last 1).Trim()
if (-not (Test-Path $rdpPath)) {
    throw "RDP profile was not created: $rdpPath"
}
Start-Process -FilePath "mstsc.exe" -ArgumentList "`"$rdpPath`""
