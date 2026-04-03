#!/usr/bin/env bash
set -euo pipefail

ADMIN_USER="${1:-agentcodex}"
export DEBIAN_FRONTEND=noninteractive

sudo apt-get update
sudo apt-get install -y xfce4 xfce4-goodies xrdp xorgxrdp dbus-x11 xterm falkon

cat <<'EOF' | sudo tee "/home/${ADMIN_USER}/.xsession" >/dev/null
#!/bin/sh
setxkbmap -layout us,ru -option grp:alt_shift_toggle
startxfce4
EOF
sudo chown "${ADMIN_USER}:${ADMIN_USER}" "/home/${ADMIN_USER}/.xsession"
sudo chmod +x "/home/${ADMIN_USER}/.xsession"

sudo -u "${ADMIN_USER}" mkdir -p "/home/${ADMIN_USER}/.config/xfce4/xfconf/xfce-perchannel-xml"
cat <<'EOF' | sudo tee "/home/${ADMIN_USER}/.config/xfce4/xfconf/xfce-perchannel-xml/keyboard-layout.xml" >/dev/null
<?xml version="1.0" encoding="UTF-8"?>
<channel name="keyboard-layout" version="1.0">
  <property name="Default" type="empty">
    <property name="XkbDisable" type="bool" value="false"/>
    <property name="XkbLayout" type="string" value="us,ru"/>
    <property name="XkbVariant" type="string" value=","/>
    <property name="XkbOptions" type="string" value="grp:alt_shift_toggle"/>
  </property>
</channel>
EOF
sudo chown -R "${ADMIN_USER}:${ADMIN_USER}" "/home/${ADMIN_USER}/.config/xfce4"

sudo adduser xrdp ssl-cert || true
sudo systemctl enable xrdp
sudo systemctl restart xrdp
sudo ufw deny 3389/tcp || true

echo "xrdp status:"
sudo systemctl --no-pager --full status xrdp | sed -n '1,12p'
