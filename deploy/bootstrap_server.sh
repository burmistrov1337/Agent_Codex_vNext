#!/usr/bin/env bash
set -euo pipefail

SERVER_TZ="${SERVER_TZ:-Asia/Novosibirsk}"
APP_USER="${APP_USER:-agentcodex}"
APP_ROOT="${APP_ROOT:-/opt/agent_codex_vnext}"
RUNTIME_ROOT="${RUNTIME_ROOT:-/var/lib/agent_codex_vnext}"
N8N_ROOT="${N8N_ROOT:-/var/lib/n8n}"

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get upgrade -y
apt-get install -y curl git ca-certificates ufw fail2ban htop jq unzip

ln -fs "/usr/share/zoneinfo/${SERVER_TZ}" /etc/localtime
dpkg-reconfigure -f noninteractive tzdata >/dev/null 2>&1 || true

if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  useradd -m -s /bin/bash -G sudo "${APP_USER}"
fi

if ! getent group docker >/dev/null 2>&1; then
  groupadd docker
fi

usermod -aG docker "${APP_USER}" || true

mkdir -p "${APP_ROOT}" "${RUNTIME_ROOT}" "${N8N_ROOT}"
chown -R "${APP_USER}:${APP_USER}" "${APP_ROOT}" "${RUNTIME_ROOT}" "${N8N_ROOT}"

ufw allow OpenSSH
ufw --force enable

systemctl enable --now fail2ban

"$(dirname "$0")/install_docker_ubuntu.sh"

printf '\nBootstrap complete.\n'
printf 'Timezone: %s\n' "${SERVER_TZ}"
printf 'App user: %s\n' "${APP_USER}"
printf 'App root: %s\n' "${APP_ROOT}"
