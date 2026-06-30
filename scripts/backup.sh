#!/bin/bash
# EJC v2 — Backup diário PostgreSQL + upload Google Drive
# Cron: 0 2 * * * /opt/ejc/scripts/backup.sh >> /var/log/ejc_backup.log 2>&1
set -euo pipefail

BACKUP_DIR="/opt/ejc/backups"
DB_CONTAINER="ejc_db"
DB_NAME="ejc_db"
DB_USER="ejc_user"
RETENTION_DAYS=7
RETENTION_DRIVE_DAYS=90
DATE=$(date +%Y%m%d_%H%M%S)
FILENAME="${BACKUP_DIR}/ejc_db_${DATE}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Iniciando backup..."
docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$FILENAME"
SIZE=$(du -sh "$FILENAME" | cut -f1)
echo "[$(date)] Backup local salvo: $FILENAME ($SIZE)"

# ── Upload para Google Drive ──────────────────────────────────────────────────
if command -v rclone &>/dev/null && [ -f "/root/.config/rclone/rclone.conf" ]; then
    DRIVE_REMOTE="gdrive"
    DRIVE_FOLDER="EJC-Backups"
    echo "[$(date)] Enviando para Google Drive ($DRIVE_REMOTE:$DRIVE_FOLDER)..."
    if rclone copy "$FILENAME" "$DRIVE_REMOTE:$DRIVE_FOLDER/" --stats-one-line 2>&1; then
        echo "[$(date)] Upload OK → Drive:$DRIVE_FOLDER/$(basename $FILENAME)"
        # Limpar backups antigos no Drive (manter 90 dias)
        rclone delete "$DRIVE_REMOTE:$DRIVE_FOLDER/" \
            --min-age "${RETENTION_DRIVE_DAYS}d" \
            --include "ejc_db_*.sql.gz" 2>/dev/null || true
    else
        echo "[$(date)] AVISO: falha no upload para o Drive — backup local mantido"
    fi
else
    echo "[$(date)] rclone não configurado — apenas backup local"
fi

# ── Limpar backups locais antigos ─────────────────────────────────────────────
find "$BACKUP_DIR" -name "ejc_db_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
LOCAL_COUNT=$(ls -1 "${BACKUP_DIR}"/ejc_db_*.sql.gz 2>/dev/null | wc -l)
echo "[$(date)] Backups locais retidos: $LOCAL_COUNT"
