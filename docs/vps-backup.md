# VPS Backup

Current VPS backup flow:

- Secrets: `/root/.config/vps-backup.env`
- Script: `/usr/local/bin/vps-backup-to-ftp.sh`
- Units:
  - `/etc/systemd/system/vps-backup-to-ftp.service`
  - `/etc/systemd/system/vps-backup-to-ftp.timer`

Schedule:

- Daily at `03:30 UTC`
- `Persistent=true`
- `RandomizedDelaySec=10m`

Included paths:

- `/root/.openclaw`
- `/root/.ssh`
- `/root/.config/systemd/user`
- `/etc`
- `/var/spool/cron`

Excluded paths:

- `/root/.cache`
- `/root/.npm`
- `/root/.local/share/pnpm/store`
- `/root/.openclaw/agents/main/sessions`
- `/var/log/journal`

Config knobs in `/root/.config/vps-backup.env`:

- `FTP_HOST`
- `FTP_USER`
- `FTP_PASSWORD`
- `FTP_REMOTE_DIR`
- `BACKUP_TMP_DIR`
- `LOCAL_RETENTION_DAYS`
- `REMOTE_KEEP_ARCHIVES`

Manual checks:

```bash
systemctl status vps-backup-to-ftp.service
systemctl list-timers vps-backup-to-ftp.timer
journalctl -u vps-backup-to-ftp.service -n 100 --no-pager
/usr/local/bin/vps-backup-to-ftp.sh --dry-run
/usr/local/bin/vps-backup-to-ftp.sh
```

Restore checklist:

1. Download the matching `.tar.gz`, `.sha256`, and `.manifest.txt` from FTP.
2. Verify integrity with `sha256sum -c <archive>.sha256`.
3. Inspect the manifest for hostname, timestamp, included paths, and script version.
4. Extract into a staging directory first:

```bash
mkdir -p /restore/staging
tar -xzf agent-codex-backup-YYYYmmddTHHMMSSZ.tar.gz -C /restore/staging
```

5. Restore only the needed paths, starting with:
   - `/root/.openclaw`
   - `/root/.ssh`
   - `/root/.config/systemd/user`
   - `/etc`
6. Recheck permissions before restarting services.
7. Restart and verify:

```bash
systemctl daemon-reload
systemctl --user restart openclaw-gateway
openclaw status --deep
```

Risk note:

- The current transport is plain FTP without TLS. This keeps the current working setup intact, but credentials and file contents are not protected in transit.
