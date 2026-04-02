# Agent_Codex vNext

Clean-room repo for the next generation of `Agent_Codex`.

## Goals

- one server-ready agent system for work and study;
- explicit runtime contracts and hooks;
- durable memory and session logs;
- first-class marketplace vertical;
- stable headless runs for `n8n` and Telegram notifications.

## Quickstart

```powershell
cd D:\Agent_Codex_vNext
$env:PYTHONPATH='src'
python -m agent_codex.apps.cli.main doctor
python -m agent_codex.apps.cli.main marketplace-watch --sample-data --headless
python -m agent_codex.apps.cli.main telegram-bot --once --json
```

## Telegram Bot MVP

The first Telegram ingress lives in `vNext`, not in the legacy repo.

Current shape:

- long polling
- single-user access via `TELEGRAM_ALLOWED_CHAT_ID`
- async task queue with `ack`, `confirm`, and final result
- text, documents, and photos
- risky requests require `/confirm`

Required env:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_CHAT_ID=
TELEGRAM_POLL_TIMEOUT_SECONDS=20
```

Useful commands:

```powershell
python -m agent_codex.apps.cli.main telegram-bot
python -m agent_codex.apps.cli.main telegram-bot --once --json
```
