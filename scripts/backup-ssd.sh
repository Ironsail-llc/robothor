#!/bin/bash
# Robothor full system backup to external SSD
# Weekly Sunday at 4:15 AM via cron
# First run: ~4.5 GB. Subsequent: incremental (rsync).

set -euo pipefail

SSD_MOUNT="/mnt/robothor-backup"
BACKUP_ROOT="$SSD_MOUNT/robothor"
DATE=$(date +%Y%m%d)
LOG="$HOME/robothor/scripts/backup.log"

# Check SSD is mounted — skip silently if not plugged in
if ! mountpoint -q "$SSD_MOUNT" 2>/dev/null; then
    echo "[$(date)] SSD not mounted at $SSD_MOUNT — skipping backup" >> "$LOG"
    exit 0
fi

mkdir -p "$BACKUP_ROOT/latest" "$BACKUP_ROOT/db"

echo "[$(date)] Starting weekly backup..." >> "$LOG"

# Rsync all project directories (incremental)
for dir in clawd moltbot garmin-sync clawd-main; do
    rsync -a --delete --exclude='__pycache__' \
        "$HOME/$dir/" "$BACKUP_ROOT/latest/$dir/" >> "$LOG" 2>&1
done

# Hidden config directories
rsync -a --delete "$HOME/.openclaw/" "$BACKUP_ROOT/latest/openclaw/" >> "$LOG" 2>&1
rsync -a --delete "$HOME/.cloudflared/" "$BACKUP_ROOT/latest/cloudflared/" >> "$LOG" 2>&1
rsync -a "$HOME/.config/systemd/" "$BACKUP_ROOT/latest/systemd-user/" >> "$LOG" 2>&1

# System-level service files (vision, mediamtx, etc.)
sudo cp /etc/systemd/system/robothor-*.service "$BACKUP_ROOT/latest/" 2>> "$LOG"
sudo cp /etc/systemd/system/mediamtx-webcam.service "$BACKUP_ROOT/latest/" 2>> "$LOG" || true

# PostgreSQL dump (dated, keep 8 weeks)
pg_dump robothor_memory | gzip > "$BACKUP_ROOT/db/robothor_memory-$DATE.sql.gz" 2>> "$LOG"
find "$BACKUP_ROOT/db" -name "robothor_memory-*" -mtime +56 -delete 2>> "$LOG"

# Crontab + model manifest
crontab -l > "$BACKUP_ROOT/latest/crontab.bak" 2>> "$LOG"
ollama list > "$BACKUP_ROOT/latest/ollama-models.txt" 2>> "$LOG"

echo "[$(date)] Backup complete. $(du -sh "$BACKUP_ROOT" | cut -f1) total." >> "$LOG"
