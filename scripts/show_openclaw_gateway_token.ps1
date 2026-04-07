param(
    [string]$ServerHost = "135.136.186.133",
    [string]$User = "agentcodex",
    [string]$KeyPath = "$HOME\.ssh\id_ed25519_agentcodex_vps"
)

$resolvedKey = [Environment]::ExpandEnvironmentVariables($KeyPath)
if (-not (Test-Path $resolvedKey)) {
    throw "SSH key not found: $resolvedKey"
}

$sshArgs = @(
    "-o", "StrictHostKeyChecking=accept-new",
    "-i", $resolvedKey,
    "${User}@${ServerHost}",
    "sed -n 's/^OPENCLAW_GATEWAY_TOKEN=//p' /opt/openclaw/.env | head -n 1"
)

$token = & ssh.exe @sshArgs
$token = ($token | Select-Object -Last 1).Trim()
if (-not $token) {
    throw "OpenClaw gateway token was not found on the server."
}

Write-Host $token
