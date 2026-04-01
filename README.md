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
```
