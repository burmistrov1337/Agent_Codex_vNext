param(
    [string]$ConfigPath = "$HOME\.agent-codex-vps\server.env",
    [string]$SecretPath = "$HOME\.agent-codex-vps\root-password.txt"
)

$ErrorActionPreference = "Stop"

function Read-EnvFile {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw "Config file was not found: $Path"
    }

    $map = @{}
    foreach ($line in Get-Content -Path $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $parts = $trimmed.Split("=", 2)
        if ($parts.Count -ne 2) { continue }
        $value = [Environment]::ExpandEnvironmentVariables($parts[1].Trim())
        $map[$parts[0].Trim()] = $value
    }
    return $map
}

function Test-LocalPort {
    param([int]$Port)

    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $connected = $async.AsyncWaitHandle.WaitOne(700)
        if ($connected -and $client.Connected) {
            $client.EndConnect($async) | Out-Null
            $client.Close()
            return $true
        }
        $client.Close()
        return $false
    } catch {
        return $false
    }
}

function Get-SecretValue {
    param(
        [hashtable]$Config,
        [string]$Path
    )

    if ($Config.ContainsKey("PASSWORD") -and -not [string]::IsNullOrWhiteSpace($Config["PASSWORD"])) {
        return $Config["PASSWORD"]
    }

    if (-not (Test-Path $Path)) {
        return ""
    }

    $raw = (Get-Content -Path $Path -Raw).Trim()
    if (-not $raw) {
        return ""
    }
    if ($raw.StartsWith("ROOT_PASSWORD=")) {
        return $raw.Substring("ROOT_PASSWORD=".Length)
    }
    return $raw
}

function Resolve-ClientPath {
    param(
        [string[]]$Candidates
    )

    foreach ($candidate in $Candidates) {
        $expanded = [Environment]::ExpandEnvironmentVariables($candidate)
        if (Test-Path $expanded) {
            return $expanded
        }
    }
    return $null
}

function Normalize-HostKey {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }

    if ($Value -match '^[0-9]+\s+SHA256:') {
        $parts = $Value -split '\s+'
        if ($parts.Length -ge 2) {
            return $parts[1]
        }
    }

    return $Value.Trim()
}

$cfg = Read-EnvFile -Path $ConfigPath
$required = "HOST", "PORT", "USER", "LOCAL_PORT", "OPENCLAW_REMOTE_PORT", "OPENCLAW_SCHEME", "OPENCLAW_PATH"
foreach ($key in $required) {
    if (-not $cfg.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($cfg[$key])) {
        throw "Missing required config value: $key"
    }
}

$serverHost = $cfg["HOST"]
$port = [int]$cfg["PORT"]
$user = $cfg["USER"]
$localPort = [int]$cfg["LOCAL_PORT"]
$remotePort = [int]$cfg["OPENCLAW_REMOTE_PORT"]
$scheme = $cfg["OPENCLAW_SCHEME"]
$path = $cfg["OPENCLAW_PATH"]
$strict = if ($cfg.ContainsKey("STRICT_HOST_KEY_CHECKING")) { $cfg["STRICT_HOST_KEY_CHECKING"] } else { "accept-new" }
$keyPath = if ($cfg.ContainsKey("KEY_PATH")) { $cfg["KEY_PATH"] } else { "" }
$uiUrl = "{0}://127.0.0.1:{1}{2}" -f $scheme, $localPort, $path
$password = Get-SecretValue -Config $cfg -Path $SecretPath
$hostKey = if ($cfg.ContainsKey("HOST_KEY")) { Normalize-HostKey -Value $cfg["HOST_KEY"] } else { $null }

$plinkPath = Resolve-ClientPath -Candidates @(
    "$env:ProgramFiles\PuTTY\plink.exe",
    "$env:ProgramFiles(x86)\PuTTY\plink.exe"
)
$puttyPath = Resolve-ClientPath -Candidates @(
    "$env:ProgramFiles\PuTTY\putty.exe",
    "$env:ProgramFiles(x86)\PuTTY\putty.exe"
)
$sshPath = (Get-Command ssh -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)

if (-not $plinkPath -and -not $sshPath) {
    throw "Neither PuTTY/plink nor OpenSSH ssh.exe is available."
}

if (-not (Test-LocalPort -Port $localPort)) {
    if ($plinkPath -and $password) {
        $tunnelArgs = @(
            "-batch"
            "-ssh"
            "-N"
            "-P", $port
            "-l", $user
            "-pw", $password
            "-L", "127.0.0.1:${localPort}:127.0.0.1:${remotePort}"
        )
        if ($hostKey) {
            $tunnelArgs += @("-hostkey", $hostKey)
        }
        $tunnelArgs += $serverHost
        $tunnelProcess = Start-Process -FilePath $plinkPath -ArgumentList $tunnelArgs -WindowStyle Hidden -PassThru
    } else {
        if (-not $sshPath) {
            throw "Password-based tunnel requires plink.exe, or a working key-based ssh.exe setup."
        }

        $tunnelArgs = @(
            "-N"
            "-T"
            "-p", $port
            "-o", "ExitOnForwardFailure=yes"
            "-o", "ServerAliveInterval=30"
            "-o", "ServerAliveCountMax=3"
            "-o", "StrictHostKeyChecking=$strict"
            "-L", "127.0.0.1:${localPort}:127.0.0.1:${remotePort}"
        )

        if ($keyPath -and (Test-Path $keyPath)) {
            $tunnelArgs += @("-i", $keyPath)
        }

        $tunnelArgs += "$user@$serverHost"
        $tunnelProcess = Start-Process -FilePath $sshPath -ArgumentList $tunnelArgs -WindowStyle Hidden -PassThru
    }

    Start-Sleep -Seconds 3

    if (-not (Test-LocalPort -Port $localPort)) {
        if ($tunnelProcess -and $tunnelProcess.HasExited) {
            throw "SSH tunnel failed to start. ssh.exe exited immediately."
        }
        Write-Warning "SSH tunnel process started, but 127.0.0.1:$localPort is still not reachable."
    }
}

Start-Process $uiUrl

if ($puttyPath -and $password) {
    $puttyArgs = @(
        "-ssh"
        "-P", $port
        "-l", $user
        "-pw", $password
    )
    if ($hostKey) {
        $puttyArgs += @("-hostkey", $hostKey)
    }
    $puttyArgs += $serverHost
    Start-Process -FilePath $puttyPath -ArgumentList $puttyArgs
    exit 0
}

if (-not $sshPath) {
    throw "Interactive shell requires putty.exe with password or ssh.exe with manual/key auth."
}

$shellArgs = @()
if ($keyPath -and (Test-Path $keyPath)) {
    $shellArgs += "ssh -i `"$keyPath`" -p $port -o StrictHostKeyChecking=$strict $user@$serverHost"
} else {
    $shellArgs += "ssh -p $port -o StrictHostKeyChecking=$strict $user@$serverHost"
}

Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-Command", $shellArgs[0])
