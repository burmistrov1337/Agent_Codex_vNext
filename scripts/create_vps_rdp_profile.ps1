param(
    [int]$LocalPort = 3390,
    [string]$User = "agentcodex"
)

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$rdpPath = Join-Path $scriptRoot "Agent_Codex Server.rdp"

$content = @"
screen mode id:i:2
use multimon:i:0
desktopwidth:i:1440
desktopheight:i:900
session bpp:i:32
winposstr:s:0,3,0,0,1200,800
compression:i:1
keyboardhook:i:2
audiocapturemode:i:0
videoplaybackmode:i:1
connection type:i:7
networkautodetect:i:1
bandwidthautodetect:i:1
displayconnectionbar:i:1
enableworkspacereconnect:i:0
disable wallpaper:i:0
allow font smoothing:i:1
allow desktop composition:i:1
disable full window drag:i:0
disable menu anims:i:0
disable themes:i:0
disable cursor setting:i:0
bitmapcachepersistenable:i:1
full address:s:127.0.0.1:$LocalPort
username:s:$User
prompt for credentials:i:0
administrative session:i:0
autoreconnection enabled:i:1
"@

Set-Content -LiteralPath $rdpPath -Value $content -Encoding ASCII
Write-Host $rdpPath
