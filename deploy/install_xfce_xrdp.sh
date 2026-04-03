#!/usr/bin/env bash
set -euo pipefail

ADMIN_USER="${1:-agentcodex}"
export DEBIAN_FRONTEND=noninteractive

sudo apt-get update
sudo apt-get install -y xfce4 xfce4-goodies xrdp xorgxrdp dbus-x11 xterm falkon

echo "startxfce4" | sudo tee "/home/${ADMIN_USER}/.xsession" >/dev/null
sudo chown "${ADMIN_USER}:${ADMIN_USER}" "/home/${ADMIN_USER}/.xsession"

sudo adduser xrdp ssl-cert || true
sudo systemctl enable xrdp
sudo systemctl restart xrdp
sudo ufw deny 3389/tcp || true

echo "xrdp status:"
sudo systemctl --no-pager --full status xrdp | sed -n '1,12p'
