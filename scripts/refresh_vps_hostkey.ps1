param(
    [string]$ConfigPath = "$HOME\.agent-codex-vps\server.env",
    [string]$KnownHostsPath = "$HOME\.ssh\known_hosts"
)

$ErrorActionPreference = "Stop"

function Read-EnvFile {
    param([string]$Path)

    $map = @{}
    foreach ($line in Get-Content -Path $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $parts = $trimmed.Split("=", 2)
        if ($parts.Count -ne 2) { continue }
        $map[$parts[0].Trim()] = [Environment]::ExpandEnvironmentVariables($parts[1].Trim())
    }
    return $map
}

if (-not (Get-Command ssh-keygen -ErrorAction SilentlyContinue)) {
    throw "ssh-keygen.exe was not found in PATH."
}

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    throw "ssh.exe was not found in PATH."
}

$cfg = Read-EnvFile -Path $ConfigPath
$serverHost = $cfg["HOST"]
$port = [int]$cfg["PORT"]

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $KnownHostsPath) | Out-Null
if (-not (Test-Path $KnownHostsPath)) {
    New-Item -ItemType File -Force -Path $KnownHostsPath | Out-Null
}

& ssh-keygen -R $serverHost | Out-Null
& ssh-keygen -R "[$serverHost]:$port" | Out-Null
& ssh `
    -o "UserKnownHostsFile=$KnownHostsPath" `
    -o "StrictHostKeyChecking=accept-new" `
    -o "BatchMode=yes" `
    -o "PreferredAuthentications=none" `
    -o "PubkeyAuthentication=no" `
    -o "PasswordAuthentication=no" `
    -p $port `
    "root@$serverHost" `
    "exit" | Out-Null

if (-not (Test-Path $KnownHostsPath) -or -not (Get-Content $KnownHostsPath | Select-String -SimpleMatch $serverHost)) {
    throw "Failed to refresh known_hosts for ${serverHost}:$port"
}
Write-Host "Updated known_hosts for ${serverHost}:$port"
