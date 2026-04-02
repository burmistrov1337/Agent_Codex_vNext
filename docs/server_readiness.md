# Server Readiness

Current deployment assumption:

- Ubuntu 22.04.5 LTS
- VPS/VDS
- `n8n` on the same host
- `Docker Compose` as the default deployment shape until a different choice is made

## Minimal runtime contract

- `agent_codex.apps.cli.main marketplace-watch --headless` is the headless entrypoint for automation
- `agent_codex.apps.cli.main telegram-bot` is the local Telegram ingress entrypoint
- runtime state lives in `.agent_codex/`
- marketplace artifacts are written to `.agent_codex/artifacts/marketplace/`
- Telegram inbox, polling state, and sessions live under `.agent_codex/telegram/`
- Telegram delivery is optional and controlled by env configuration

## Windows bot runtime helpers

- `scripts/start_telegram_bot.ps1` starts the bot in background and writes PID/logs
- `scripts/status_telegram_bot.ps1` shows process state and tail logs
- `scripts/logs_telegram_bot.ps1` shows stdout/stderr logs and can tail them
- `scripts/stop_telegram_bot.ps1` stops the background process
- `scripts/install_telegram_bot_autostart.ps1` registers Windows Task Scheduler autostart
