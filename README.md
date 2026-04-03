# Agent_Codex vNext

Clean-room repo for the next generation of `Agent_Codex`.

## Goals

- one server-ready agent system for work and study;
- explicit runtime contracts and hooks;
- durable memory and session logs;
- first-class marketplace vertical;
- stable headless runs for `n8n` and Telegram.

## What Already Works

- Telegram ingress in `vNext` via long polling;
- headless CLI runs for `doctor`, `marketplace-watch`, and future scheduled jobs;
- runtime memory and session storage in `.agent_codex/`;
- marketplace artifact generation, including HTML dashboards;
- Docker Compose layout for an always-on bot plus local-only `n8n`.

## Local Quickstart

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

- long polling;
- single-user access via `TELEGRAM_ALLOWED_CHAT_ID`;
- async task queue with `ack`, `confirm`, and final result;
- text, documents, and photos;
- risky requests require `/confirm`.

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

Windows helpers:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_telegram_bot.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\status_telegram_bot.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\logs_telegram_bot.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\stop_telegram_bot.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\install_telegram_bot_autostart.ps1
```

Important:

- only one long-polling instance should run at a time;
- if the local Windows bot is active, do not start the VPS bot with the same token until the local one is stopped.

## Server Layout

Target server:

- Ubuntu 22.04.5 LTS;
- Docker Compose;
- one always-on `agent_codex_bot` container;
- one sidecar `n8n` container;
- persistent runtime data in `.agent_codex/`;
- persistent `n8n` data in `.docker/n8n/`.

By default:

- `n8n` binds to `127.0.0.1:5678`;
- Telegram is the primary live ingress;
- `doctor --json` is the healthcheck and smoke-test baseline.

## First Server Bootstrap

On the Ubuntu host:

```bash
sudo bash deploy/bootstrap_server.sh
```

This prepares:

- baseline packages;
- timezone;
- `ufw`;
- `fail2ban`;
- Docker and Docker Compose;
- app directories under `/opt/agent_codex_vnext` and `/var/lib`.

## First Deploy On Server

```bash
cd /opt/agent_codex_vnext
cp .env.example .env
vim .env
bash deploy/deploy_stack.sh
```

Useful ops:

```bash
bash deploy/stack_status.sh
bash deploy/stack_logs.sh
bash deploy/stack_logs.sh agent_codex_bot
bash deploy/smoke_check.sh
bash deploy/backup_runtime.sh
```

## Docs Map

- `docs/server_readiness.md` - deploy and operations runbook;
- `docs/migration_matrix.md` - what we reuse, redesign, or discard;
- `docs/claude_gap_target_spec.md` - explicit audit of `vNext` against Claude-style architecture patterns.
