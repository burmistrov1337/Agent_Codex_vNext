# Work Log

Repository-wide memory for all work between the user and Codex in this project.

## Rules

- This is the single durable memory file for the whole repository.
- Each working session should be recorded here with date/time, topic, decisions, completed steps, pending tasks, blockers, commands run, and important files.
- Before continuing later work, read this file first.
- Keep entries practical and concise; do not rely only on chat history.

## Session 2026-04-30 - MAX And Telegram Bot Review

### Topic

- User asked to check the already-built MAX messenger and Telegram bot work.

### Completed

- Inspected repository structure and found key folders:
  - `max_bot/`
  - `telegram_adk_bot/`
  - `bot_analytics/`
  - `instruction_search/`
- Ran syntax compilation:
  - `python -m compileall max_bot telegram_adk_bot bot_analytics instruction_search`
  - Result: passed.
- Ran runtime checks through CLI:
  - `doctor --json`
  - `metrics --json`
  - Result: passed, no config issues reported by `doctor`.
- Checked bot databases:
  - `max_bot/data/bot.db` contains 99 `instruction_index` rows.
  - `telegram_adk_bot/data/bot.db` contains 121 `instruction_index` rows.
- Checked heartbeat files:
  - `max_bot/runtime/heartbeat.json`
  - `telegram_adk_bot/runtime/heartbeat.json`
  - Last updates were on 2026-04-22, so live running status needs verification.

### Blockers

- Could not run tests or Ruff because `pytest` and `ruff` are missing from both system Python and `.venv`.

### Findings

- Code compiles, but full test/lint validation is blocked by missing dev dependencies.
- Large runtime/generated browser-profile artifacts exist in `generated/`.
- Root-level temporary files exist, including `tmp_customer_groups.csv`, `tmp_customer_groups_updated.csv`, `tmp_offer.pdf`, and `tmp_offer.txt`.
- `git status` showed many generated files added, especially under `generated/`; these likely should not be committed without explicit intent.

### Pending

- Decide whether `max_bot/`, `telegram_adk_bot/`, `bot_analytics/`, and `instruction_search/` are repository-level components or should be reorganized.
- Install or restore dev dependencies: `pytest`, `ruff`, and possibly `mypy`.
- Re-run validation after dependencies are available.
- Verify whether MAX and Telegram bots should be running now; restart or inspect services if needed.
- Clean, ignore, or intentionally preserve generated artifacts before committing.

## Session 2026-04-30 - Repository-Wide Memory Rule

### Topic

- User clarified that memory should cover all work in this repository, not be separate for every project.

### Decisions

- Use `WORK_LOG.md` as the single repository-wide durable memory file.
- `AGENTS.md` now instructs future sessions to read and update `WORK_LOG.md`.

### Completed

- Updated `AGENTS.md` Session Memory rules.
- Created `WORK_LOG.md`.

### Pending

- Continue using this file as the canonical continuity log for all future work in this repository.

## Session 2026-04-30 - MAX Webhook Migration

### Topic

- User received a MAX security notice: long polling limits change on 2026-05-11 and MAX recommends switching bots to webhook delivery.
- Scope: MAX bot for instruction search and subscription checks. Telegram bot is not affected by the MAX long polling notice.

### Source

- MAX documentation checked: `https://dev.max.ru/docs-api/methods/POST/subscriptions`
- Key requirements from docs:
  - Active webhook subscription disables long polling.
  - Webhook endpoint must be available over HTTPS on port 443.
  - Endpoint must return HTTP 200 within 30 seconds.
  - Optional `secret` is sent in `X-Max-Bot-Api-Secret` and should be verified.
  - If webhook delivery fails for 8 hours, MAX automatically unsubscribes the bot.

### Completed

- Added webhook settings to `max_bot/config.py`:
  - `MAX_WEBHOOK_URL`
  - `MAX_WEBHOOK_HOST`
  - `MAX_WEBHOOK_PORT`
  - `MAX_WEBHOOK_PATH`
  - `MAX_WEBHOOK_SECRET`
- Refactored `max_bot/main.py` so polling and webhook use shared context/update handling.
- Added webhook server entrypoint:
  - `max_bot/webhook.py`
  - Validates `X-Max-Bot-Api-Secret` when configured.
  - Accepts MAX update JSON on `MAX_WEBHOOK_PATH`.
  - Writes heartbeat in webhook mode.
  - Schedules update processing asynchronously and returns 200 quickly.
- Added MAX subscription API helpers in `max_bot/max_api.py`.
- Added `max_bot/register_webhook.py` and `scripts/register_max_webhook.ps1`.
- Added `deploy/vps/max-bot-webhook.service`.
- Updated `scripts/install_instruction_refresh_vps.ps1` to upload webhook-related MAX modules and enable `max-bot-webhook.service`.
- Updated `scripts/check_max_bot_vps.ps1` to check `max-bot-webhook.service` first.
- Updated `.env.example` with MAX webhook variables.

### Verification

- `python -m compileall max_bot` passed.
- `python -m compileall max_bot scripts` passed.
- `.venv` dependency import check passed for `aiohttp`, `aiosqlite`, and `google.auth`.
- Created aiohttp app from `max_bot.webhook.create_app()` successfully and confirmed routes include `/max/webhook` and `/health`.

### Pending

- Configure real `MAX_WEBHOOK_URL` with HTTPS domain on port 443.
- Configure a strong `MAX_WEBHOOK_SECRET` using allowed characters `[A-Za-z0-9_-]`, length 5-256.
- Configure reverse proxy on VPS so public `https://domain/max/webhook` forwards to local `MAX_WEBHOOK_HOST:MAX_WEBHOOK_PORT`.
- Deploy updated files to VPS.
- Register the MAX webhook subscription with `python -m max_bot.register_webhook` or `scripts/register_max_webhook.ps1`.
- Stop/disable old long polling `max-bot.service` if it exists, because webhook subscription disables long polling anyway.

### Follow-up Discovery

- User clarified they have a domain with HTTPS certificate but do not know how to configure the endpoint.
- Checked `.env`: VPS access and MAX token values exist, but no domain or `MAX_WEBHOOK_URL` is configured.
- Checked VPS:
  - Hostname: `agent-codex.host`
  - `nginx`, `caddy`, and `certbot` were not found in PATH.
  - `nginx` and `caddy` systemd services are inactive/not present.
  - No `/etc/nginx` configs or `/etc/letsencrypt/live` certificates were found.
- Next step requires the real public domain name that should receive MAX webhooks.

### Deployment Completed

- User added DNS A record for `bot.adkcosmetics.ru`.
- Verified DNS:
  - `bot.adkcosmetics.ru -> 135.136.186.133`
  - Google DNS `8.8.8.8` also resolves it to `135.136.186.133`.
- Configured VPS:
  - Installed `nginx`, `certbot`, and `python3-certbot-nginx`.
  - Uploaded updated MAX bot modules and shared packages to `/opt/max_bot/app`.
  - Updated `/opt/max_bot/.env` with webhook variables:
    - `MAX_WEBHOOK_URL=https://bot.adkcosmetics.ru/max/webhook`
    - `MAX_WEBHOOK_HOST=127.0.0.1`
    - `MAX_WEBHOOK_PORT=8085`
    - `MAX_WEBHOOK_PATH=/max/webhook`
    - generated `MAX_WEBHOOK_SECRET`
  - Installed nginx reverse proxy for `bot.adkcosmetics.ru`.
  - Issued Let's Encrypt certificate for `bot.adkcosmetics.ru`; expires on 2026-07-29 and certbot renewal timer is active.
  - Enabled and started `max-bot-webhook.service`.
  - Registered MAX webhook subscription; API returned `{"success": true}`.
  - Disabled/stopped old `max-bot.service` long polling service.
- Verification:
  - `https://bot.adkcosmetics.ru/health` returns `{"ok": true, "service": "max_bot_webhook"}`.
  - POST to `https://bot.adkcosmetics.ru/max/webhook` without `X-Max-Bot-Api-Secret` returns HTTP 403.
  - POST with the configured secret returns HTTP 200 and `{"ok": true}`.
  - `/opt/max_bot/app/max_bot/runtime/heartbeat.json` now records `"mode": "webhook"`.

### Current Production State

- MAX bot is now using webhook delivery.
- Telegram bot remains unchanged on long polling.
- Public MAX webhook endpoint:
  - `https://bot.adkcosmetics.ru/max/webhook`
- Public health endpoint:
  - `https://bot.adkcosmetics.ru/health`

## Session 2026-04-30 - Move Bot Context Into Orchestra

### Topic

- User asked to find the multi-agent system project Orchestra and clone the MAX/Telegram bot project and memory there so future development can continue through Orchestra.

### Completed

- Found Orchestra at `D:\Orchestra\Agent_Orchestra`.
- Found Orchestra domain layout: sibling domain repositories under `D:\Orchestra\Agent_Domain_*`, registered in `D:\Orchestra\Agent_Orchestra\configs\domains.json`.
- Created new domain repository:
  - `D:\Orchestra\Agent_Domain_ADK_Bots`
- Copied bot workspace code without runtime secrets/data:
  - `workspace/max_bot`
  - `workspace/telegram_adk_bot`
  - `workspace/bot_analytics`
  - `workspace/instruction_search`
  - `workspace/deploy`
  - selected operational scripts under `workspace/scripts`
  - `.env.example`
- Excluded real `.env`, runtime directories, bot databases, lock files, heartbeat files, generated browser profiles, and `__pycache__`.
- Added domain documentation and memory:
  - `D:\Orchestra\Agent_Domain_ADK_Bots\AGENTS.md`
  - `D:\Orchestra\Agent_Domain_ADK_Bots\README.md`
  - `D:\Orchestra\Agent_Domain_ADK_Bots\memory\README.md`
  - `D:\Orchestra\Agent_Domain_ADK_Bots\memory\source_WORK_LOG.md`
  - `D:\Orchestra\Agent_Domain_ADK_Bots\prompts\system_prompt.md`
- Registered the domain in Orchestra:
  - domain id: `adk_bots`
  - path: `../Agent_Domain_ADK_Bots`
- Added Orchestra agent:
  - `adk_bot_engineer`
- Initialized git in `D:\Orchestra\Agent_Domain_ADK_Bots`.

### Verification

- `configs/domains.json` and `configs/agents.json` parse as valid JSON.
- `python -m agent_orchestra.interfaces.cli doctor` shows `adk_bots` and `adk_bot_engineer`.
- Test routing request selected `adk_bots` and context refs from the new domain; the test queued task was cancelled afterward through `TaskBus.reject`.
- `python -m compileall workspace\max_bot workspace\telegram_adk_bot workspace\bot_analytics workspace\instruction_search` passed inside `Agent_Domain_ADK_Bots`.
- Removed compile-generated `__pycache__` files from the new domain.
- Orchestra queue is empty after cleanup.

### Pending

- Commit or otherwise preserve the new `Agent_Domain_ADK_Bots` domain repository.
- Commit/update Orchestra config changes in `Agent_Orchestra`.
- Continue future MAX/Telegram bot development from the `adk_bots` domain.

### Handoff Documentation Added

- Added `D:\Orchestra\Agent_Domain_ADK_Bots\HANDOFF.md`.
- The handoff states:
  - exactly what code and memory were moved;
  - what was intentionally not moved;
  - where to find missing runtime material in `D:\Agent_Codex_vNext` and on the VPS;
  - current production services and URLs;
  - how to continue development and verify/deploy safely.
- Updated `Agent_Domain_ADK_Bots`:
  - `README.md` now points future agents to `HANDOFF.md`.
  - `AGENTS.md` requires reading `HANDOFF.md` and `memory/README.md` before changes.
  - `memory/README.md` references `HANDOFF.md`.

## 2026-04-30 10:41 +07:00 - Codex Session Restore Config Error

### Topic

- User reported Codex could not resume chats with: `failed to load configuration: d:\Agent_Codex\.codex\config.toml:133:1: invalid type: map, expected a sequence`.

### Completed

- Inspected `D:\Agent_Codex\.codex\config.toml` around line 133.
- Found legacy GSD hook config:
  - `[[hooks]]`
  - `event = "SessionStart"`
  - `command = "node D:/Agent_Codex/.codex/hooks/gsd-check-update.js"`
- Created backup:
  - `D:\Agent_Codex\.codex\config.toml.bak-20260430-hooks-error`
- Commented out only the problematic hook block in `D:\Agent_Codex\.codex\config.toml`.

### Verification

- Confirmed both TOML files parse with Python `tomllib`:
  - `D:\Agent_Codex\.codex\config.toml`
  - `C:\Users\dasha\.codex\config.toml`
- Checked CLI version: `codex-cli 0.126.0-alpha.8`.

### Pending

- Reopen/resume a Codex session to confirm the UI no longer throws the restore error.
- If GSD session-start update checks are needed, reinstall/update GSD or migrate the hook block to the hook schema expected by the current Codex CLI.
