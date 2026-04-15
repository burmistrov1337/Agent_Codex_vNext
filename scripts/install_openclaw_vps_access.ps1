param(
    [string]$PdfPath = "",
    [string]$InstallRoot = "$HOME\.agent-codex-vps",
    [string]$DesktopPath = [Environment]::GetFolderPath("Desktop")
)

$ErrorActionPreference = "Stop"

function Ensure-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command was not found in PATH: $Name"
    }
}

Ensure-Command -Name "uv"
Ensure-Command -Name "powershell"

$repoRoot = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $InstallRoot "server.env"
$passwordPath = Join-Path $InstallRoot "root-password.txt"
$pdfJsonPath = Join-Path $InstallRoot "activation-data.json"
$iconPath = Join-Path $InstallRoot "openclaw-vps.ico"
$launcherTarget = Join-Path $repoRoot "scripts\launch_openclaw_vps.ps1"
$shortcutPath = Join-Path $DesktopPath "OpenClaw VPS.lnk"

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null

$uvArgs = @(
    "run"
    "--with"
    "pypdf"
    "python"
    "$repoRoot\scripts\extract_vps_pdf.py"
    "--json-out"
    "$pdfJsonPath"
    "--env-out"
    "$configPath"
)

if ($PdfPath) {
    $uvArgs += @("--pdf", $PdfPath)
}

& uv @uvArgs
if ($LASTEXITCODE -ne 0) {
    throw "PDF extraction failed."
}

if (-not (Test-Path $passwordPath)) {
    Set-Content -Path $passwordPath -Value "ROOT_PASSWORD=" -Encoding UTF8
}

& "$repoRoot\scripts\create_openclaw_icon.ps1" -OutputPath $iconPath

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-ExecutionPolicy Bypass -File `"$launcherTarget`""
$shortcut.WorkingDirectory = $repoRoot
$shortcut.IconLocation = $iconPath
$shortcut.Description = "Open SSH and local OpenClaw UI tunnel for the VPS"
$shortcut.Save()

& icacls $passwordPath /inheritance:r /grant:r "${env:USERNAME}:(F)" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Failed to restrict ACL on $passwordPath"
}

Write-Host "Installed OpenClaw VPS access files:"
Write-Host "  Config:   $configPath"
Write-Host "  Secret:   $passwordPath"
Write-Host "  Extract:  $pdfJsonPath"
Write-Host "  Shortcut: $shortcutPath"
Write-Host ""
Write-Host "If root password login is still enabled, run:"
Write-Host "  powershell -ExecutionPolicy Bypass -File `"$repoRoot\scripts\refresh_vps_hostkey.ps1`""
Write-Host "  uv run --with paramiko python `"$repoRoot\scripts\bootstrap_root_key_access.py`" --config `"$configPath`" --secret `"$passwordPath`" --public-key `"$HOME\.ssh\agent_codex_server.pub`""
