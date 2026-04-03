param(
    [string]$ServerHost = "135.136.186.133",
    [string]$User = "agentcodex",
    [string]$KeyPath = "$HOME\.ssh\id_ed25519_agentcodex_vps",
    [int]$LocalPort = 3390
)

$resolvedKey = [Environment]::ExpandEnvironmentVariables($KeyPath)
if (-not (Test-Path $resolvedKey)) {
    throw "SSH key not found: $resolvedKey"
}

$sshArgs = @(
    "-i", $resolvedKey,
    "-L", "${LocalPort}:127.0.0.1:3389",
    "${User}@${ServerHost}",
    "-N"
)

Start-Process -FilePath "ssh.exe" -ArgumentList $sshArgs -WindowStyle Normal
Write-Host "SSH tunnel started. Keep the opened ssh window running."
Write-Host "RDP endpoint: 127.0.0.1:$LocalPort"
