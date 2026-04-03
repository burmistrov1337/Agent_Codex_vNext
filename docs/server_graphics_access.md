# Server Graphics Access

## What is installed

The VPS uses a lightweight desktop stack:

- `XFCE`
- `xrdp`
- `Falkon` browser
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

## Keyboard layout

The remote desktop session is configured with:

- English + Russian layouts
- switch shortcut: `Alt` + `Shift`

If the current session was opened before this change, disconnect and reconnect once.

## How to use Agent_Codex from the server desktop

The first practical paths are:

1. Open `Falkon` if you want to use the familiar browser route and sign in to the web chat you already use.
2. Open the terminal if you want to manage the local `Agent_Codex_vNext` runtime directly.
3. Go to the deployed project:

```bash
cd /opt/agent_codex_vnext
```

4. Check status:

```bash
docker compose ps
docker compose logs --tail=100 agent_codex_bot
```

5. Run a one-shot command inside the bot container:

```bash
docker compose exec agent_codex_bot python -m agent_codex.apps.cli.main doctor --project-root /app --json
```

6. For live conversational usage of the deployed runtime, keep using the Telegram bot as the main ingress. The remote desktop is the visual admin layer around the same runtime.

## Notes

- This does not yet create a web chat UI for `Agent_Codex_vNext`.
- If a browser-based chat UI is needed later, build it as a separate next wave.
- Keep the SSH tunnel window open during the RDP session.
