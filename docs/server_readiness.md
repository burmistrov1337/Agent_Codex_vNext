# Server Readiness

Target runtime:

- Ubuntu 22.04.5 LTS;
- VPS/VDS;
- Docker Compose;
- `n8n` on the same host;
- Telegram ingress in `Agent_Codex_vNext`.

## Runtime Shape

Always-on services:

- `agent_codex_bot` is the primary always-on runtime;
- `n8n` is a sidecar scheduler/orchestrator.

Headless jobs use one-shot CLI invocations such as:

- `agent_codex.apps.cli.main marketplace-watch --headless`;
- `agent_codex.apps.cli.main doctor --json`.

## Deployment Defaults

- runtime state lives in `.agent_codex/`;
- `n8n` state lives in `.docker/n8n/`;
- `n8n` binds to `127.0.0.1:5678` by default;
- no reverse proxy or public `n8n` exposure by default;
- Telegram long polling should run in only one place at a time to avoid token conflicts.

## Server Bootstrap

Run:

```bash
sudo bash deploy/bootstrap_server.sh
```

This prepares:

- base packages;
- timezone;
- `ufw`;
- `fail2ban`;
- Docker and Docker Compose;
- baseline directories for app and runtime data.

The bootstrap script is intentionally safe and generic. It does not deploy secrets and does not publish public services.

## Deploy Layout

Recommended server paths:

- repo root: `/opt/agent_codex_vnext`
- runtime state: `/opt/agent_codex_vnext/.agent_codex`
- `n8n` state: `/opt/agent_codex_vnext/.docker/n8n`
- backups: `/opt/agent_codex_vnext/backups`

If you prefer external persistent storage, map the same folders to `/var/lib/...` and keep the compose contract unchanged.

## First Deploy

1. Copy the repo to `/opt/agent_codex_vnext`.
2. Create `.env` from `.env.example`.
3. Fill Telegram and other required secrets.
4. Run:

```bash
cd /opt/agent_codex_vnext
bash deploy/deploy_stack.sh
```

What `deploy_stack.sh` does:

- ensures required directories exist;
- creates `.env` from `.env.example` if missing;
- builds the `agent_codex_bot` image;
- pulls the `n8n` image;
- starts the stack in detached mode.

## Operations

Status:

```bash
bash deploy/stack_status.sh
```

Logs:

```bash
bash deploy/stack_logs.sh
bash deploy/stack_logs.sh agent_codex_bot
bash deploy/stack_logs.sh n8n
```

Smoke check:

```bash
bash deploy/smoke_check.sh
```

Backup:

```bash
bash deploy/backup_runtime.sh
```

Restore:

```bash
bash deploy/restore_runtime.sh backups/<archive>.tar.gz
```

## Health And Smoke Contracts

The app container healthcheck uses:

```bash
python -m agent_codex.apps.cli.main doctor --project-root /app --json
```

The smoke-check script validates:

- compose configuration;
- runtime directories;
- containerized `doctor --json`;
- sample headless marketplace run.

## Optional systemd

For auto-start after reboot:

1. Copy `deploy/systemd.agent-codex-vnext.service` to `/etc/systemd/system/agent-codex-vnext.service`.
2. Run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now agent-codex-vnext.service
```

## Security Baseline

The server base should eventually include:

- a separate sudo admin user;
- SSH key auth;
- disabled root password login after key-based access is verified;
- `ufw` enabled with the smallest practical port surface;
- `fail2ban` running;
- no public `n8n` exposure unless a deliberate reverse-proxy decision is made.

## Acceptance Checklist

- SSH works for the admin user;
- Docker and Docker Compose are available;
- `ufw` and `fail2ban` are active;
- `docker compose ps` shows the stack;
- `doctor --json` works inside the app container;
- `.agent_codex/` and `.docker/n8n/` survive container restarts;
- only one Telegram polling runtime is active for the configured bot token.
