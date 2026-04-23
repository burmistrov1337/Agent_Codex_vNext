param(
    [string]$ProjectRoot = "d:\Agent_Codex_vNext"
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

@'
from pathlib import Path
import json
import time
import paramiko

root = Path(r"d:/Agent_Codex_vNext")
env_path = root / ".env"
if not env_path.exists():
    raise SystemExit(f".env not found: {env_path}")

cfg = {}
for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    cfg[key.strip()] = value.strip().strip('"').strip("'")

host = cfg.get("VPS_HOST")
user = cfg.get("VPS_USER", "root")
if not host:
    raise SystemExit("VPS_HOST is missing in .env")

key_path = root / ".secrets" / "openclaw_ssh_key"
if not key_path.exists():
    raise SystemExit(f"SSH key not found: {key_path}")

pkey = None
for cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
    try:
        pkey = cls.from_private_key_file(str(key_path))
        break
    except Exception:
        pass
if pkey is None:
    raise SystemExit("Cannot parse SSH private key")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(hostname=host, username=user, pkey=pkey, timeout=20)

def run(cmd: str) -> str:
    stdin, stdout, stderr = ssh.exec_command(cmd)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    if code != 0:
        return f"ERROR({code}): {err or out}"
    return out

print("SERVICE_ACTIVE:", run("systemctl is-active max-bot.service || true"))
print("SERVICE_STATE:")
print(run("systemctl show -p ActiveState -p SubState -p MainPID max-bot.service"))

hb_raw = run("cat /opt/max_bot/app/max_bot/runtime/heartbeat.json 2>/dev/null || true")
if not hb_raw:
    print("HEARTBEAT: missing")
else:
    try:
        hb = json.loads(hb_raw)
        ts = int(hb.get("ts_unix", 0))
        age = int(time.time() - ts) if ts else -1
        hb["age_sec"] = age
        print("HEARTBEAT:", json.dumps(hb, ensure_ascii=False))
    except Exception:
        print("HEARTBEAT_RAW:", hb_raw)

print("RECENT_LOGS:")
print(run("journalctl -u max-bot.service -n 20 --no-pager -o cat | tail -n 20"))
ssh.close()
'@ | .\.venv\Scripts\python.exe -

