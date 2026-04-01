# Server Readiness

Current deployment assumption:

- Ubuntu 22.04.5 LTS
- VPS/VDS
- `n8n` on the same host
- `Docker Compose` as the default deployment shape until a different choice is made

## Minimal runtime contract

- `agent_codex.apps.cli.main marketplace-watch --headless` is the headless entrypoint for automation
- runtime state lives in `.agent_codex/`
- marketplace artifacts are written to `.agent_codex/artifacts/marketplace/`
- Telegram delivery is optional and controlled by env configuration

