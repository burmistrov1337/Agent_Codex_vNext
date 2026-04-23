# Instruction Search MVP Quickstart

Operator quickstart for the local instruction-search flow. This covers five tasks:

1. Bootstrap the Google Sheets tabs.
2. Export MAX posts through an isolated local Yandex Browser profile when API export is not enough.
3. Import exported posts JSON into the workbook.
4. Rebuild the local SQLite indexes for Telegram and MAX.
5. Run the local test bots.

## Prerequisites

- Run commands from `D:\Agent_Codex_vNext`.
- Make sure the repo Python environment is available (`.venv`, `venv`, `py -3.12`, or `python`).
- Set these environment variables before using the sheets/bootstrap/import/reindex commands:

```powershell
$env:BOT_ANALYTICS_SPREADSHEET_ID = "your-google-sheet-id"
$env:GOOGLE_SERVICE_ACCOUNT_FILE = "D:\path\to\service-account.json"
```

- For Telegram test bot runs, make sure `.env` or your shell provides the bot settings used by `agent_codex.apps.cli.main`, especially `TELEGRAM_BOT_TOKEN` and allowed chat id settings.
- For MAX test bot runs, make sure `.env` or your shell provides `MAX_ACCESS_TOKEN` or `MAX_ACCESS_TOKEN_LOCAL`, `MAX_REQUIRED_CHAT_ID`, and optionally `MAX_BOT_DB_PATH`.
- For browser-based MAX export, keep `Yandex Browser` installed locally. If it is installed in a custom path, set `YANDEX_BROWSER_PATH`.
- Playwright is declared in `pyproject.toml`. In this workspace it is available in `.venv`, so the browser-export commands below use `.\.venv\Scripts\python.exe`.

## 1. Bootstrap Google Sheets Tabs

Creates or verifies these tabs: `POSTS_TELEGRAM`, `POSTS_MAX`, `INSTRUCTION_INDEX`, `SYNONYMS`, `SYNC_STATE`, `RECIPE_BACKLOG`.

```powershell
py -3.12 .\scripts\bootstrap_instruction_search_sheets.py
```

## 2. Export MAX Posts via Isolated Browser Profile

Use this path when MAX API history is incomplete, when you need the live web rendering, or when you want a dedicated local profile that does not touch the main Yandex Browser profile.

### Start the isolated browser profile

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_max_browser_profile.ps1
```

Optional custom values:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_max_browser_profile.ps1 `
  -ProfileDir .\generated\max_browser_profile `
  -RemoteDebuggingPort 9223 `
  -StartUrl "https://max.ru/"
```

What this does:

- starts Yandex Browser with a separate user data directory,
- exposes CDP on `http://127.0.0.1:9223`,
- keeps MAX login isolated from the user's normal browser profile.

### Log in and open the target MAX page

In the browser window started by the script:

- sign in to MAX if needed,
- open the channel/chat you want to export,
- keep the browser window open.

### Run the Playwright export

```powershell
.\.venv\Scripts\python.exe .\scripts\fetch_max_channel_posts_browser.py `
  --url "https://max.ru/" `
  --cdp-url "http://127.0.0.1:9223" `
  --channel-name "ADK MAX" `
  --channel-id "max-browser-channel"
```

Useful options:

- `--scrolls 20` if the page needs more history loaded before export.
- `--scroll-pause-ms 2000` if content appears slowly.
- `--output .\generated\instruction_search\max_export_2026-04-22\browser_result.json` to force a specific output file.

Default output path:

```text
.\generated\instruction_search\max_export_YYYY-MM-DD\browser_result.json
```

Important limitations:

- the exporter only sees what the current MAX web page has rendered,
- older posts may require manual scrolling or a higher `--scrolls` value,
- DOM selectors are generic and may need adjustment if MAX changes its web UI.

## 3. Import Exported Posts JSON

The importer accepts either:

- a top-level JSON array, or
- an object with `items` or `posts`.

Useful source fields include `id` or `post_id`, `url` or `post_url`, `published_at_utc` or `date`, `title`, `text`, `caption`, `media`, `is_instruction`, `is_recipe_candidate`, `extracted_active_primary`, `extracted_inci_primary`, and `tags`.

Example: import Telegram export.

```powershell
py -3.12 .\scripts\import_instruction_posts.py `
  --platform telegram `
  --input .\exports\telegram_posts.json `
  --channel-name "ADK Telegram" `
  --channel-id "@adk_channel"
```

Example: import MAX browser export.

```powershell
py -3.12 .\scripts\import_instruction_posts.py `
  --platform max `
  --input .\generated\instruction_search\max_export_YYYY-MM-DD\browser_result.json `
  --channel-name "ADK MAX" `
  --channel-id "max-browser-channel"
```

Example: import MAX API export.

```powershell
py -3.12 .\scripts\import_instruction_posts.py `
  --platform max `
  --input .\exports\max_posts.json `
  --channel-name "ADK MAX" `
  --channel-id "max-channel-1"
```

## 4. Rebuild Local Indexes

Pick the SQLite file each bot should read from. Current defaults in code are:

- Telegram local bot runtime: use an explicit path you control for MVP smoke tests.
- MAX bot default DB: `max_bot/data/bot.db` unless `MAX_BOT_DB_PATH` overrides it.

Example paths:

```powershell
$telegramDb = ".\.agent_codex\instruction_search\telegram_instruction_search.db"
$maxDb = ".\max_bot\data\bot.db"
```

Rebuild Telegram:

```powershell
py -3.12 .\scripts\reindex_instruction_search.py --platform telegram --db-path $telegramDb
```

Rebuild MAX:

```powershell
py -3.12 .\scripts\reindex_instruction_search.py --platform max --db-path $maxDb
```

Optional smoke check after each rebuild:

```powershell
py -3.12 .\scripts\check_instruction_search_readiness.py --platform telegram --db-path $telegramDb
py -3.12 .\scripts\check_instruction_search_readiness.py --platform max --db-path $maxDb
```

## 5. Run Local Test Bots

Telegram foreground bot:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_telegram_bot_foreground.ps1
```

MAX foreground bot:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_max_bot.ps1
```

With verbose update logging:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_max_bot.ps1 -DebugUpdates
```

## Minimal Operator Flow

```powershell
$env:BOT_ANALYTICS_SPREADSHEET_ID = "your-google-sheet-id"
$env:GOOGLE_SERVICE_ACCOUNT_FILE = "D:\path\to\service-account.json"
$telegramDb = ".\.agent_codex\instruction_search\telegram_instruction_search.db"
$maxDb = ".\max_bot\data\bot.db"

py -3.12 .\scripts\bootstrap_instruction_search_sheets.py
powershell -ExecutionPolicy Bypass -File .\scripts\start_max_browser_profile.ps1
.\.venv\Scripts\python.exe .\scripts\fetch_max_channel_posts_browser.py --url "https://max.ru/" --cdp-url "http://127.0.0.1:9223" --channel-name "ADK MAX" --channel-id "max-browser-channel"
py -3.12 .\scripts\import_instruction_posts.py --platform max --input .\generated\instruction_search\max_export_YYYY-MM-DD\browser_result.json --channel-name "ADK MAX" --channel-id "max-browser-channel"
py -3.12 .\scripts\reindex_instruction_search.py --platform max --db-path $maxDb
py -3.12 .\scripts\check_instruction_search_readiness.py --platform max --db-path $maxDb
```
