from __future__ import annotations

import argparse
import os
from pathlib import Path

import paramiko


def load_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = os.path.expandvars(value.strip())
    return data


def read_password(secret_path: Path) -> str:
    text = secret_path.read_text(encoding="utf-8").strip()
    if "=" in text and text.startswith("ROOT_PASSWORD="):
        return text.split("=", 1)[1].strip()
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap root key-based SSH access using a password from a local file.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--secret", required=True, type=Path)
    parser.add_argument("--public-key", required=True, type=Path)
    args = parser.parse_args()

    cfg = load_env(args.config)
    host = cfg.get("HOST")
    user = cfg.get("USER", "root")
    port = int(cfg.get("PORT", "22"))
    password = read_password(args.secret)
    public_key = args.public_key.read_text(encoding="utf-8").strip()

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=host,
            port=port,
            username=user,
            password=password,
            timeout=20,
            look_for_keys=False,
            allow_agent=False,
        )
    except Exception as exc:
        print(f"Bootstrap failed: {exc}")
        return 1

    escaped_key = public_key.replace("'", "'\"'\"'")
    command = (
        "install -d -m 700 ~/.ssh && "
        "touch ~/.ssh/authorized_keys && "
        "chmod 600 ~/.ssh/authorized_keys && "
        f"grep -qxF '{escaped_key}' ~/.ssh/authorized_keys || echo '{escaped_key}' >> ~/.ssh/authorized_keys"
    )
    _, stdout, stderr = client.exec_command(command, timeout=20)
    output = stdout.read().decode("utf-8", errors="replace").strip()
    error = stderr.read().decode("utf-8", errors="replace").strip()
    if output:
        print(output)
    if error:
        print(error)
        client.close()
        return 1

    print(f"Installed public key for {user}@{host}:{port}")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
