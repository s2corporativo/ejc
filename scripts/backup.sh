#!/bin/bash
# EJC — Backup diário: PostgreSQL + uploads/GED + envio ao Google Drive.
# Cron: 0 2 * * * /opt/ejc/scripts/backup.sh >> /var/log/ejc_backup.log 2>&1
set -euo pipefail

BACKUP_DIR="/opt/ejc/backups"
DB_CONTAINER="ejc_db"
APP_CONTAINER="ejc_backend"
DB_NAME="ejc_db"
DB_USER="ejc_user"
UPLOADS_DIR_CONTAINER="/app/uploads"
RETENTION_DAYS=30
RETENTION_DRIVE_DAYS=90
DRIVE_REMOTE="gdrive"
DRIVE_FOLDER="EJC-Backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Envia um arquivo ao Google Drive e rotaciona os antigos do mesmo prefixo.
#   $1 = arquivo local ; $2 = glob de retenção (ex.: 'ejc_db_*.sql.gz')
enviar_drive() {
    local f="$1" glob="$2"
    if command -v rclone &>/dev/null && [ -f "/root/.config/rclone/rclone.conf" ]; then
        echo "[$(date)] Enviando $(basename "$f") para Drive ($DRIVE_REMOTE:$DRIVE_FOLDER)..."
        if rclone copy "$f" "$DRIVE_REMOTE:$DRIVE_FOLDER/" --stats-one-line 2>&1; then
            echo "[$(date)] Upload OK → Drive:$DRIVE_FOLDER/$(basename "$f")"
            rclone delete "$DRIVE_REMOTE:$DRIVE_FOLDER/" \
                --min-age "${RETENTION_DRIVE_DAYS}d" --include "$glob" 2>/dev/null || true
        else
            echo "[$(date)] AVISO: falha no upload de $(basename "$f") — cópia local mantida"
        fi
    else
        echo "[$(date)] rclone não configurado — apenas backup local"
    fi
}

# ── 1. Banco PostgreSQL ───────────────────────────────────────────────────────
DB_FILE="${BACKUP_DIR}/ejc_db_${DATE}.sql.gz"
echo "[$(date)] Backup do banco..."
docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$DB_FILE"
echo "[$(date)] Banco salvo: $DB_FILE ($(du -sh "$DB_FILE" | cut -f1))"
enviar_drive "$DB_FILE" "ejc_db_*.sql.gz"

# ── 2. Uploads / GED (arquivos enviados pelos usuários) ───────────────────────
# Sem isto, um pg_dump não recupera os DOCUMENTOS em disco (só os metadados).
UPLOADS_FILE="${BACKUP_DIR}/ejc_uploads_${DATE}.tar.gz"
if ! docker ps --format '{{.Names}}' | grep -qx "$APP_CONTAINER"; then
    echo "[$(date)] AVISO: $APP_CONTAINER não está rodando — uploads NÃO salvos nesta rodada"
elif ! docker exec "$APP_CONTAINER" sh -c "test -d $UPLOADS_DIR_CONTAINER"; then
    echo "[$(date)] $APP_CONTAINER sem $UPLOADS_DIR_CONTAINER — pulando uploads"
else
    echo "[$(date)] Backup dos uploads ($UPLOADS_DIR_CONTAINER)..."
    # O diretório está VIVO durante o backup: um upload/remoção concorrente faz o
    # GNU tar sair com rc=1 ("file changed/removed as we read it") mesmo com o
    # arquivo gerado íntegro — isso é tolerável. Já um arquivo ILEGÍVEL
    # (permissão/I/O) sai com rc>=2 e DEVE falhar: marcar um backup PARCIAL como
    # OK seria perda silenciosa. Por isso NÃO usamos --ignore-failed-read (que
    # mascararia o arquivo ilegível como sucesso); --warning=no-file-changed só
    # corta o ruído do log, e o stderr real segue visível para diagnóstico.
    # (Bug anterior: `2>/dev/null` + `if tar` tratava o rc=1 como falha total e
    # apagava um backup de uploads válido — daí o "falha no backup dos uploads".)
    set +e
    docker exec "$APP_CONTAINER" tar --warning=no-file-changed \
        -czf - -C "$UPLOADS_DIR_CONTAINER" . > "$UPLOADS_FILE"
    tar_rc=$?
    set -e
    if [ "$tar_rc" -le 1 ] && [ -s "$UPLOADS_FILE" ]; then
        aviso=""; [ "$tar_rc" -eq 1 ] && aviso=" (aviso: arquivos mudaram durante a leitura)"
        echo "[$(date)] Uploads salvos: $UPLOADS_FILE ($(du -sh "$UPLOADS_FILE" | cut -f1))${aviso}"
        enviar_drive "$UPLOADS_FILE" "ejc_uploads_*.tar.gz"
    else
        echo "[$(date)] AVISO: falha no backup dos uploads (tar rc=${tar_rc})"
        rm -f "$UPLOADS_FILE"
    fi
fi

# ── 3. Rotação local (banco + uploads) ────────────────────────────────────────
find "$BACKUP_DIR" -name "ejc_db_*.sql.gz"      -mtime +${RETENTION_DAYS} -delete
find "$BACKUP_DIR" -name "ejc_uploads_*.tar.gz" -mtime +${RETENTION_DAYS} -delete
echo "[$(date)] Retidos localmente — banco: $(ls -1 "${BACKUP_DIR}"/ejc_db_*.sql.gz 2>/dev/null | wc -l), uploads: $(ls -1 "${BACKUP_DIR}"/ejc_uploads_*.tar.gz 2>/dev/null | wc -l)"
