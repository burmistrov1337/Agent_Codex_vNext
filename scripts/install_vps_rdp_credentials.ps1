param(
    [string]$User = "agentcodex",
    [string]$Password,
    [int]$LocalPort = 3390
)

if (-not $Password) {
    throw "Password is required."
}

$targets = @(
    "TERMSRV/127.0.0.1",
    "TERMSRV/127.0.0.1:$LocalPort"
)

foreach ($target in $targets) {
    cmdkey /generic:$target /user:$User /pass:$Password | Out-Null
}

Write-Host "Saved RDP credentials for $User on 127.0.0.1 and 127.0.0.1:$LocalPort"
