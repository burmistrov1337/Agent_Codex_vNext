# Agent_Codex vNext

Новый clean-room репозиторий для следующего поколения `Agent_Codex`.

## Цели

- одна server-ready агентная система для работы и учёбы;
- явные runtime-контракты и hooks;
- устойчивая память и журналы сессий;
- полноценная marketplace-вертикаль как первый домен;
- стабильные headless-запуски для `n8n` и Telegram.

## Что уже работает

- Telegram-ingress в `vNext` через long polling;
- headless CLI-команды для `doctor`, `marketplace-watch` и будущих scheduled-сценариев;
- runtime-память и хранилище сессий в `.agent_codex/`;
- генерация marketplace-артефактов, включая HTML-дашборды;
- Docker Compose-контур для always-on бота и локального `n8n`.

## Быстрый локальный старт

```powershell
cd D:\Agent_Codex_vNext
$env:PYTHONPATH='src'
python -m agent_codex.apps.cli.main doctor
python -m agent_codex.apps.cli.main marketplace-watch --sample-data --headless
python -m agent_codex.apps.cli.main telegram-bot --once --json
```

## Telegram-бот MVP

Первый Telegram-ingress живёт в `vNext`, а не в старом репозитории.

Текущая форма:

- long polling;
- single-user доступ через `TELEGRAM_ALLOWED_CHAT_ID`;
- асинхронная очередь задач с `ack`, `confirm` и финальным ответом;
- текст, документы и фотографии;
- рискованные действия требуют `/confirm`.

Нужные переменные окружения:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_CHAT_ID=
TELEGRAM_POLL_TIMEOUT_SECONDS=20
```

Полезные команды:

```powershell
python -m agent_codex.apps.cli.main telegram-bot
python -m agent_codex.apps.cli.main telegram-bot --once --json
```

Помощники для Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_telegram_bot.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\status_telegram_bot.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\logs_telegram_bot.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\stop_telegram_bot.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\install_telegram_bot_autostart.ps1
```

Важно:

- одновременно должен работать только один long-polling инстанс;
- если локальный Windows-бот уже активен, не запускай VPS-бота с тем же токеном, пока локальный процесс не остановлен.

## Серверная схема

Целевой сервер:

- Ubuntu 22.04.5 LTS;
- Docker Compose;
- один always-on контейнер `agent_codex_bot`;
- один sidecar-контейнер `n8n`;
- постоянные runtime-данные в `.agent_codex/`;
- постоянные данные `n8n` в `.docker/n8n/`.

По умолчанию:

- `n8n` слушает `127.0.0.1:5678`;
- Telegram является основным live-ingress;
- `doctor --json` используется как healthcheck и базовый smoke-test.

## Первый bootstrap сервера

На Ubuntu-хосте:

```bash
sudo bash deploy/bootstrap_server.sh
```

Скрипт подготавливает:

- базовые пакеты;
- timezone;
- `ufw`;
- `fail2ban`;
- Docker и Docker Compose;
- каталоги приложения в `/opt/agent_codex_vnext` и `/var/lib`.

## Первый deploy на сервер

```bash
cd /opt/agent_codex_vnext
cp .env.example .env
vim .env
bash deploy/deploy_stack.sh
```

Полезные операции:

```bash
bash deploy/stack_status.sh
bash deploy/stack_logs.sh
bash deploy/stack_logs.sh agent_codex_bot
bash deploy/smoke_check.sh
bash deploy/backup_runtime.sh
```

## Карта документации

- `docs/server_readiness.md` — runbook по deploy и эксплуатации;
- `docs/migration_matrix.md` — что мы переиспользуем, перепроектируем или отбрасываем;
- `docs/claude_gap_target_spec.md` — явный аудит `vNext` относительно Claude-подобных архитектурных паттернов.
