param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("bootstrap-sheets", "import-posts", "reindex", "check", "run-telegram-test-bot", "run-max-test-bot", "start-max-browser-profile", "fetch-max-browser-posts", "max-full-refresh", "max-api-refresh")]
    [string]$Action,

    [ValidateSet("telegram", "max")]
    [string]$Platform,

    [string]$Input,
    [string]$ChannelName,
    [string]$ChannelId,
    [string]$DbPath,
    [string]$ProfileDir,
    [ValidateSet("local", "server")]
    [string]$AppEnv = "server",
    [int]$ChatId,
    [int]$Count = 100,
    [int]$Batches = 10,
    [string]$Output,
    [switch]$ReplaceSheet,
    [switch]$SkipCheck,
    [switch]$DebugUpdates
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

function Resolve-Python {
    $pythonCandidates = @(
        $env:AGENT_CODEX_PYTHON,
        (Join-Path $repoRoot ".venv\Scripts\python.exe"),
        (Join-Path $repoRoot "venv\Scripts\python.exe"),
        (Join-Path $env:USERPROFILE "AppData\Local\Programs\Python\Python312\python.exe"),
        "py",
        "python"
    )

    foreach ($candidate in $pythonCandidates) {
        if (-not $candidate) {
            continue
        }
        if ($candidate -in @("py", "python")) {
            return $candidate
        }
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "Python executable was not found."
}

function Invoke-RepoPython {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,

        [string[]]$ScriptArgs = @()
    )

    $python = Resolve-Python
    if ($python -eq "py") {
        & py -3.12 $ScriptPath @ScriptArgs
    } else {
        & $python $ScriptPath @ScriptArgs
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

function Resolve-MaxDbPath {
    if ($DbPath) {
        return $DbPath
    }
    if ($env:MAX_BOT_DB_PATH) {
        return $env:MAX_BOT_DB_PATH
    }
    return "max_bot/data/bot.db"
}

switch ($Action) {
    "bootstrap-sheets" {
        Invoke-RepoPython "scripts/bootstrap_instruction_search_sheets.py"
        break
    }

    "import-posts" {
        if (-not $Platform) { throw "-Platform is required for import-posts." }
        if (-not $Input) { throw "-Input is required for import-posts." }
        $importArgs = @(
            "--platform", $Platform,
            "--input", $Input
        )
        if ($ChannelName) {
            $importArgs += @("--channel-name", $ChannelName)
        }
        if ($ChannelId) {
            $importArgs += @("--channel-id", $ChannelId)
        }
        if ($ReplaceSheet) {
            $importArgs += "--replace-sheet"
        }
        Invoke-RepoPython "scripts/import_instruction_posts.py" $importArgs
        break
    }

    "reindex" {
        if (-not $Platform) { throw "-Platform is required for reindex." }
        $reindexArgs = @("--platform", $Platform)
        if ($DbPath) {
            $reindexArgs += @("--db-path", $DbPath)
        }
        Invoke-RepoPython "scripts/reindex_instruction_search.py" $reindexArgs
        break
    }

    "check" {
        if (-not $DbPath) { throw "-DbPath is required for check." }
        $checkArgs = @("--db-path", $DbPath)
        if ($Platform) {
            $checkArgs += @("--platform", $Platform)
        }
        Invoke-RepoPython "scripts/check_instruction_search_readiness.py" $checkArgs
        break
    }

    "run-telegram-test-bot" {
        & powershell -ExecutionPolicy Bypass -File "scripts/run_telegram_bot_foreground.ps1"
        if ($LASTEXITCODE -ne 0) {
            throw "Telegram test bot command failed with exit code $LASTEXITCODE"
        }
        break
    }

    "run-max-test-bot" {
        $runnerArgs = @()
        if ($DebugUpdates) {
            $runnerArgs += "-DebugUpdates"
        }
        & powershell -ExecutionPolicy Bypass -File "scripts/run_max_bot.ps1" @runnerArgs
        if ($LASTEXITCODE -ne 0) {
            throw "MAX test bot command failed with exit code $LASTEXITCODE"
        }
        break
    }

    "start-max-browser-profile" {
        $profileArgs = @()
        if ($ProfileDir) {
            $profileArgs += @("-ProfileDir", $ProfileDir)
        }
        & powershell -ExecutionPolicy Bypass -File "scripts/start_max_browser_profile.ps1" @profileArgs
        if ($LASTEXITCODE -ne 0) {
            throw "MAX browser profile launch failed with exit code $LASTEXITCODE"
        }
        break
    }

    "fetch-max-browser-posts" {
        $fetchArgs = @(
            "--url", "https://web.max.ru/-72158373787757",
            "--cdp-url", "http://127.0.0.1:9223",
            "--channel-name", "Активы для косметики",
            "--channel-id", "max-browser-channel"
        )
        Invoke-RepoPython "scripts/fetch_max_channel_posts_browser.py" $fetchArgs
        break
    }

    "max-full-refresh" {
        $resolvedDbPath = Resolve-MaxDbPath
        $outputPath = Join-Path $repoRoot ("generated\instruction_search\max_export_{0}\result.json" -f (Get-Date -Format "yyyy-MM-dd"))

        $exportArgs = @(
            "--app-env", $AppEnv,
            "--count", [string]$Count,
            "--batches", [string]$Batches,
            "--output", $outputPath
        )
        if ($ChatId) {
            $exportArgs += @("--chat-id", [string]$ChatId)
        }
        Invoke-RepoPython "scripts/fetch_max_channel_posts.py" $exportArgs

        $importArgs = @(
            "--platform", "max",
            "--input", $outputPath,
            "--replace-sheet"
        )
        if ($ChannelName) {
            $importArgs += @("--channel-name", $ChannelName)
        }
        if ($ChannelId) {
            $importArgs += @("--channel-id", $ChannelId)
        }
        Invoke-RepoPython "scripts/import_instruction_posts.py" $importArgs
        Invoke-RepoPython "scripts/reindex_instruction_search.py" @(
            "--platform", "max",
            "--db-path", $resolvedDbPath
        )
        break
    }

    "max-api-refresh" {
        $outputPath = $Output
        if (-not $outputPath) {
            $generatedDir = Join-Path $repoRoot ("generated\instruction_search\max_export_{0}" -f (Get-Date -Format "yyyy-MM-dd"))
            New-Item -ItemType Directory -Path $generatedDir -Force | Out-Null
            $outputPath = Join-Path $generatedDir "result.json"
        }

        $exportArgs = @(
            "--app-env", $AppEnv,
            "--count", [string]$Count,
            "--batches", [string]$Batches,
            "--output", $outputPath
        )
        if ($ChatId) {
            $exportArgs += @("--chat-id", [string]$ChatId)
        }
        Invoke-RepoPython "scripts/fetch_max_channel_posts.py" $exportArgs

        $importArgs = @(
            "--platform", "max",
            "--input", $outputPath,
            "--replace-sheet"
        )
        if ($ChannelName) {
            $importArgs += @("--channel-name", $ChannelName)
        }
        if ($ChannelId) {
            $importArgs += @("--channel-id", $ChannelId)
        }
        Invoke-RepoPython "scripts/import_instruction_posts.py" $importArgs

        $resolvedDbPath = Resolve-MaxDbPath
        Invoke-RepoPython "scripts/reindex_instruction_search.py" @(
            "--platform", "max",
            "--db-path", $resolvedDbPath
        )

        if (-not $SkipCheck) {
            Invoke-RepoPython "scripts/check_instruction_search_readiness.py" @(
                "--platform", "max",
                "--db-path", $resolvedDbPath
            )
        }
        break
    }
}
