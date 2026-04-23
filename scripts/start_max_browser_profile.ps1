param(
    [string]$ProfileDir = ".\generated\max_browser_profile",
    [int]$RemoteDebuggingPort = 9223,
    [string]$StartUrl = "https://max.ru/",
    [switch]$CleanLockFiles,
    [switch]$PrintOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

function Resolve-YandexBrowserPath {
    $candidates = @(
        $env:YANDEX_BROWSER_PATH,
        $env:MAX_BROWSER_EXECUTABLE,
        "C:\Users\$env:USERNAME\AppData\Local\Yandex\YandexBrowser\Application\browser.exe",
        "C:\Program Files\Yandex\YandexBrowser\Application\browser.exe",
        "C:\Program Files (x86)\Yandex\YandexBrowser\Application\browser.exe"
    )

    foreach ($candidate in $candidates) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path $candidate)) {
            return (Resolve-Path $candidate).Path
        }
    }

    throw "Yandex Browser executable was not found. Set YANDEX_BROWSER_PATH if it is installed in a custom location."
}

function Remove-ProfileLockFiles {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ResolvedProfileDir
    )

    $lockNames = @("SingletonLock", "SingletonSocket", "SingletonCookie")
    foreach ($name in $lockNames) {
        $target = Join-Path $ResolvedProfileDir $name
        if (Test-Path $target) {
            Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
        }
    }
}

$resolvedProfileDir = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $ProfileDir))
New-Item -ItemType Directory -Force -Path $resolvedProfileDir | Out-Null

if ($CleanLockFiles) {
    Remove-ProfileLockFiles -ResolvedProfileDir $resolvedProfileDir
}

$browserPath = Resolve-YandexBrowserPath
$args = @(
    "--user-data-dir=$resolvedProfileDir",
    "--remote-debugging-port=$RemoteDebuggingPort",
    "--remote-allow-origins=*",
    "--no-first-run",
    "--no-default-browser-check",
    "--restore-last-session",
    $StartUrl
)

if ($PrintOnly) {
    Write-Host "Browser: $browserPath"
    Write-Host "Profile: $resolvedProfileDir"
    Write-Host "CDP: http://127.0.0.1:$RemoteDebuggingPort"
    Write-Host "Args: $($args -join ' ')"
    exit 0
}

$existing = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match 'browser\.exe' -and $_.CommandLine -match [Regex]::Escape($resolvedProfileDir) }
if ($existing) {
    Write-Host "Yandex Browser is already running with profile: $resolvedProfileDir"
    Write-Host "CDP endpoint: http://127.0.0.1:$RemoteDebuggingPort"
    exit 0
}

Start-Process -FilePath $browserPath -ArgumentList $args | Out-Null

Write-Host "Started Yandex Browser with isolated MAX profile."
Write-Host "Profile: $resolvedProfileDir"
Write-Host "CDP endpoint: http://127.0.0.1:$RemoteDebuggingPort"
Write-Host "If MAX requires login, complete it in that browser window and keep the browser open for Playwright export."
