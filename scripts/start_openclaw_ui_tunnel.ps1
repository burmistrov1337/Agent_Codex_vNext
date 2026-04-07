param(
    [string]$ServerHost = "135.136.186.133",
    [string]$User = "agentcodex",
    [string]$KeyPath = "$HOME\.ssh\id_ed25519_agentcodex_vps",
    [int]$LocalPort = 18789,
    [int]$RemotePort = 18789,
    [int]$WaitSeconds = 15
)

$resolvedKey = [Environment]::ExpandEnvironmentVariables($KeyPath)
if (-not (Test-Path $resolvedKey)) {
    throw "SSH key not found: $resolvedKey"
}

function Test-LocalPortListening {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    return $null -ne $connection
}

if (Test-LocalPortListening -Port $LocalPort) {
    Write-Host "OpenClaw UI tunnel is already listening on 127.0.0.1:$LocalPort"
    Write-Host "Control UI endpoint: http://127.0.0.1:$LocalPort"
    return
}

$sshArgs = @(
    "-o", "ExitOnForwardFailure=yes",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=3",
    "-o", "StrictHostKeyChecking=accept-new",
    "-i", $resolvedKey,
    "-L", "${LocalPort}:127.0.0.1:${RemotePort}",
    "${User}@${ServerHost}",
    "-N"
)

$process = Start-Process -FilePath "ssh.exe" -ArgumentList $sshArgs -WindowStyle Normal -PassThru

$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline) {
    if (Test-LocalPortListening -Port $LocalPort) {
        Write-Host "OpenClaw UI tunnel started. Keep the opened ssh window running."
        Write-Host "Control UI endpoint: http://127.0.0.1:$LocalPort"
        return
    }
    if ($process.HasExited) {
        throw "SSH tunnel process exited before opening local port $LocalPort."
    }
    Start-Sleep -Milliseconds 500
}

if (-not $process.HasExited) {
    Stop-Process -Id $process.Id -Force
}

throw "OpenClaw UI tunnel did not start listening on local port $LocalPort within $WaitSeconds seconds."
