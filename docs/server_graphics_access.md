# Server Graphics Access

## What is installed

The VPS uses a lightweight desktop stack:

- `XFCE`
- `xrdp`
- local-only RDP access through an SSH tunnel

Port `3389` is not intended to be exposed publicly. Connect through SSH tunneling from the local Windows machine.

## How to connect from Windows

1. Start the tunnel:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Agent_Codex_vNext\scripts\start_vps_rdp_tunnel.ps1
```

2. Keep the SSH tunnel window open.

3. Open Remote Desktop and connect to:

```text
127.0.0.1:3390
```

Or launch both steps together:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Agent_Codex_vNext\scripts\open_vps_rdp.ps1
```

## Login inside the desktop session

Use the Linux account:

- username: `agentcodex`
- password: the server password currently assigned to `agentcodex`

## How to use Agent_Codex from the server desktop

The first practical paths are:

1. Open the terminal in the remote desktop session.
2. Go to the deployed project:

```bash
cd /opt/agent_codex_vnext
```

3. Check status:

```bash
docker compose ps
docker compose logs --tail=100 agent_codex_bot
```

4. Run a one-shot command inside the bot container:

```bash
docker compose exec agent_codex_bot python -m agent_codex.apps.cli.main doctor --project-root /app --json
```

5. For live conversational usage, keep using the Telegram bot as the main ingress. The remote desktop is the visual admin layer around the same runtime.

## Notes

- This does not yet create a web chat UI for `Agent_Codex_vNext`.
- If a browser-based chat UI is needed later, build it as a separate next wave.
- Keep the SSH tunnel window open during the RDP session.
