param(
    [string]$ProjectRoot = "d:\Agent_Codex_vNext"
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

@'
from __future__ import annotations

from pathlib import Path
import posixpath
import paramiko


ROOT = Path(r"d:/Agent_Codex_vNext")
ENV_PATH = ROOT / ".env"
if not ENV_PATH.exists():
    raise SystemExit(f".env not found: {ENV_PATH}")

cfg: dict[str, str] = {}
for raw in ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    cfg[key.strip()] = value.strip().strip('"').strip("'")

host = cfg.get("VPS_HOST")
user = cfg.get("VPS_USER", "root")
if not host:
    raise SystemExit("VPS_HOST is missing in .env")

key_path = ROOT / ".secrets" / "openclaw_ssh_key"
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
sftp = ssh.open_sftp()


def run(cmd: str) -> str:
    stdin, stdout, stderr = ssh.exec_command(cmd)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if code != 0:
        raise RuntimeError(f"Command failed ({code}): {cmd}\nSTDOUT:\n{out}\nSTDERR:\n{err}")
    return out


def ensure_remote_dir(path: str) -> None:
    run(f"mkdir -p {path}")


def upload_file(local_path: Path, remote_path: str, mode: int | None = None) -> None:
    ensure_remote_dir(posixpath.dirname(remote_path))
    sftp.put(str(local_path), remote_path)
    if mode is not None:
        sftp.chmod(remote_path, mode)


def upload_tree(local_dir: Path, remote_dir: str) -> None:
    ensure_remote_dir(remote_dir)
    for path in local_dir.rglob("*"):
        relative = path.relative_to(local_dir).as_posix()
        remote_path = posixpath.join(remote_dir, relative)
        if path.is_dir():
            ensure_remote_dir(remote_path)
        else:
            upload_file(path, remote_path)


print("Uploading shared instruction_search package...")
upload_tree(ROOT / "instruction_search", "/opt/telegram_adk_bot/app/instruction_search")
upload_tree(ROOT / "instruction_search", "/opt/max_bot/app/instruction_search")

print("Uploading shared scripts...")
shared_scripts = [
    "scripts/_env.py",
    "scripts/import_instruction_posts.py",
    "scripts/reindex_instruction_search.py",
    "scripts/fetch_max_channel_posts.py",
    "scripts/fetch_telegram_channel_posts.py",
    "scripts/refresh_max_instruction_index.sh",
    "scripts/refresh_telegram_instruction_index.sh",
]
for rel in shared_scripts:
    local_path = ROOT / rel
    upload_file(local_path, f"/opt/telegram_adk_bot/app/{rel.replace('scripts/', 'scripts/')}", 0o755 if local_path.suffix == ".sh" else None)
    upload_file(local_path, f"/opt/max_bot/app/{rel.replace('scripts/', 'scripts/')}", 0o755 if local_path.suffix == ".sh" else None)

print("Uploading MAX API modules needed by refresh...")
upload_file(ROOT / "max_bot" / "max_api.py", "/opt/max_bot/app/max_bot/max_api.py")
upload_file(ROOT / "max_bot" / "config.py", "/opt/max_bot/app/max_bot/config.py")

print("Uploading requirements...")
upload_file(ROOT / "max_bot" / "requirements.txt", "/opt/telegram_adk_bot/app/requirements.txt")
upload_file(ROOT / "max_bot" / "requirements.txt", "/opt/max_bot/app/requirements.txt")

print("Uploading systemd units...")
unit_files = [
    ("deploy/vps/telegram-instruction-refresh.service", "/etc/systemd/system/telegram-instruction-refresh.service"),
    ("deploy/vps/telegram-instruction-refresh.timer", "/etc/systemd/system/telegram-instruction-refresh.timer"),
    ("deploy/vps/max-instruction-refresh.service", "/etc/systemd/system/max-instruction-refresh.service"),
    ("deploy/vps/max-instruction-refresh.timer", "/etc/systemd/system/max-instruction-refresh.timer"),
]
for rel, remote in unit_files:
    upload_file(ROOT / rel, remote)

print("Installing Python dependencies...")
run("/opt/telegram_adk_bot/.venv/bin/pip install -r /opt/telegram_adk_bot/app/requirements.txt")
run("/opt/max_bot/venv/bin/pip install -r /opt/max_bot/app/requirements.txt")

print("Reloading systemd and enabling timers...")
run("systemctl daemon-reload")
run("systemctl enable --now telegram-instruction-refresh.timer")
run("systemctl enable --now max-instruction-refresh.timer")

print("Timer status:")
print(run("systemctl list-timers --all 'telegram-instruction-refresh.timer' 'max-instruction-refresh.timer' --no-pager"))

sftp.close()
ssh.close()
'@ | .\.venv\Scripts\python.exe -
