#!/usr/bin/env bash
# Backs up Photoapp's database and uploaded photos/files.
#
# Usage:
#   ./scripts/backup.sh [destination-dir]
#
# Defaults match the paths docker-compose.yml mounts on this homelab
# machine. Override via env vars if your setup differs:
#   DATA_DIR, UPLOAD_FOLDER, BACKUP_DEST, KEEP
#
# To run nightly, add a line like this to `crontab -e`:
#   0 3 * * * /home/rushi/Photoapp/scripts/backup.sh >> /var/log/photoapp-backup.log 2>&1

set -euo pipefail

DATA_DIR="${DATA_DIR:-/DATA/photoapp/data}"
UPLOAD_FOLDER="${UPLOAD_FOLDER:-/DATA/photoapp/uploads}"
BACKUP_DEST="${1:-${BACKUP_DEST:-/DATA/photoapp-backups}}"
KEEP="${KEEP:-14}"   # how many backups to retain

timestamp=$(date +%Y-%m-%d_%H-%M-%S)
archive="$BACKUP_DEST/photoapp-backup-$timestamp.tar.gz"

mkdir -p "$BACKUP_DEST"

echo "Backing up $DATA_DIR and $UPLOAD_FOLDER (excluding thumbnails, which regenerate automatically) to $archive"

tar --exclude="$UPLOAD_FOLDER/thumbnails" -czf "$archive" \
    -C / \
    "${DATA_DIR#/}" \
    "${UPLOAD_FOLDER#/}"

echo "Backup complete: $(du -h "$archive" | cut -f1)"

# Keep only the most recent $KEEP backups
mapfile -t old_backups < <(ls -1t "$BACKUP_DEST"/photoapp-backup-*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)))
if [ "${#old_backups[@]}" -gt 0 ]; then
    for f in "${old_backups[@]}"; do
        echo "Removing old backup: $f"
        rm -f "$f"
    done
fi
