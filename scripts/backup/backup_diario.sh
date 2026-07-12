#!/usr/bin/env bash
# ── EJC — Backup diário canônico: PostgreSQL (pg_dump -Fc) + uploads/GED ─────
#
# Substitui o scripts/backup.sh legado como rotina diária (aquele permanece
# apenas como snapshot pré-deploy do deploy_vps_safe.sh). Diferenças:
#   • Dump em FORMATO CUSTOM (-Fc): restauração seletiva com pg_restore,
#     compressão nativa e VERIFICAÇÃO DE INTEGRIDADE via `pg_restore --list`.
#   • Rotação por CONTAGEM: mantém os N diários + M semanais mais recentes
#     (default 7 + 4), imune a relógio errado — `find -mtime` não é.
#   • Sai com código != 0 se o dump OU a verificação falharem (o cron loga).
#
# Cron sugerido na VPS (ver RUNBOOK_BACKUP.md na raiz do repo):
#   0 2 * * * cd /opt/ejc && bash scripts/backup/backup_diario.sh >> /var/log/ejc_backup.log 2>&1
#
# Configuração (todas com override por env var):
#   BACKUP_BASE_DIR   destino local (default /opt/ejc/backups)
#   KEEP_DAILY        nº de backups diários retidos   (default 7)
#   KEEP_WEEKLY       nº de backups semanais retidos  (default 4)
#   WEEKLY_DOW        dia da cópia semanal, 1=seg..7=dom (default 7)
#   DB_CONTAINER      container do Postgres  (default ejc_db)
#   APP_CONTAINER     container do backend   (default ejc_backend)
#   EJC_BACKUP_MODE   docker | local | auto  (default auto)
#                     • docker: pg_dump DENTRO do container ejc_db e tar dos
#                       uploads DENTRO do ejc_backend (volume uploads_data,
#                       montado em /app/uploads — ver docker-compose.yml).
#                     • local : pg_dump direto no host (PGHOST/PGPORT/PGUSER/
#                       PGPASSWORD/PGDATABASE) e tar de UPLOADS_DIR — usado
#                       para testar o script fora do compose.
#   RCLONE_REMOTE     destino offsite rclone (ex.: "gdrive:EJC-Backups").
#                     Vazio = sem offsite. Falha de upload NÃO derruba o
#                     backup local (avisa no log).
set -euo pipefail

BACKUP_BASE_DIR="${BACKUP_BASE_DIR:-/opt/ejc/backups}"
KEEP_DAILY="${KEEP_DAILY:-7}"
KEEP_WEEKLY="${KEEP_WEEKLY:-4}"
WEEKLY_DOW="${WEEKLY_DOW:-7}"
DB_CONTAINER="${DB_CONTAINER:-ejc_db}"
APP_CONTAINER="${APP_CONTAINER:-ejc_backend}"
EJC_BACKUP_MODE="${EJC_BACKUP_MODE:-auto}"
RCLONE_REMOTE="${RCLONE_REMOTE:-}"
UPLOADS_DIR_CONTAINER="/app/uploads"

TS="$(date +%Y%m%d_%H%M%S)"
DIR_DIARIO="$BACKUP_BASE_DIR/diario"
DIR_SEMANAL="$BACKUP_BASE_DIR/semanal"
FALHAS=0

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# ── Credenciais: mesmas variáveis do docker-compose (.env na raiz) ────────────
# Só exporta POSTGRES_* — nunca "source" cru do .env inteiro no ambiente.
if [ -f .env ]; then
    set +u
    POSTGRES_USER_ENV=$(grep -E '^POSTGRES_USER=' .env | tail -1 | cut -d= -f2-)
    POSTGRES_DB_ENV=$(grep -E '^POSTGRES_DB=' .env | tail -1 | cut -d= -f2-)
    POSTGRES_PASSWORD_ENV=$(grep -E '^POSTGRES_PASSWORD=' .env | tail -1 | cut -d= -f2-)
    set -u
fi
PGUSER_EFF="${PGUSER:-${POSTGRES_USER_ENV:-ejc_user}}"
PGDB_EFF="${PGDATABASE:-${POSTGRES_DB_ENV:-ejc_db}}"

# ── Modo docker ou local ──────────────────────────────────────────────────────
if [ "$EJC_BACKUP_MODE" = "auto" ]; then
    if docker exec "$DB_CONTAINER" true 2>/dev/null; then
        EJC_BACKUP_MODE="docker"
    else
        EJC_BACKUP_MODE="local"
    fi
fi
log "Modo: $EJC_BACKUP_MODE | banco: $PGDB_EFF | usuário: $PGUSER_EFF | destino: $BACKUP_BASE_DIR"

mkdir -p "$DIR_DIARIO" "$DIR_SEMANAL"

# ── 1. Banco PostgreSQL — pg_dump formato custom (-Fc) ────────────────────────
DB_FILE="$DIR_DIARIO/ejc_db_${TS}.dump"
log "Backup do banco → $DB_FILE"
if [ "$EJC_BACKUP_MODE" = "docker" ]; then
    docker exec "$DB_CONTAINER" pg_dump -U "$PGUSER_EFF" -Fc "$PGDB_EFF" > "$DB_FILE"
else
    PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD_ENV:-}}" \
        pg_dump -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" \
                -U "$PGUSER_EFF" -Fc "$PGDB_EFF" > "$DB_FILE"
fi
log "Banco salvo: $DB_FILE ($(du -sh "$DB_FILE" | cut -f1))"

# ── 2. Verificação de integridade (pg_restore --list lê o TOC inteiro) ────────
log "Verificando integridade do dump (pg_restore --list)..."
if [ "$EJC_BACKUP_MODE" = "docker" ]; then
    N_OBJ=$(docker exec -i "$DB_CONTAINER" pg_restore --list < "$DB_FILE" | grep -c '^[0-9]' || true)
else
    N_OBJ=$(pg_restore --list "$DB_FILE" | grep -c '^[0-9]' || true)
fi
if [ "${N_OBJ:-0}" -gt 0 ]; then
    log "Integridade OK: $N_OBJ objetos no dump"
else
    log "ERRO: dump vazio ou corrompido ($DB_FILE) — backup INVÁLIDO"
    FALHAS=$((FALHAS + 1))
fi

# ── 3. Uploads / GED (o pg_dump só traz METADADOS; os arquivos vivem aqui) ────
UP_FILE="$DIR_DIARIO/ejc_uploads_${TS}.tar.gz"
if [ "$EJC_BACKUP_MODE" = "docker" ]; then
    if docker exec "$APP_CONTAINER" sh -c "test -d $UPLOADS_DIR_CONTAINER" 2>/dev/null; then
        log "Backup dos uploads ($APP_CONTAINER:$UPLOADS_DIR_CONTAINER)..."
        if docker exec "$APP_CONTAINER" tar czf - -C "$UPLOADS_DIR_CONTAINER" . > "$UP_FILE" 2>/dev/null; then
            log "Uploads salvos: $UP_FILE ($(du -sh "$UP_FILE" | cut -f1))"
        else
            log "ERRO: falha no tar dos uploads"; rm -f "$UP_FILE"; FALHAS=$((FALHAS + 1))
        fi
    else
        log "AVISO: $APP_CONTAINER sem $UPLOADS_DIR_CONTAINER — pulando uploads"
    fi
else
    UPLOADS_DIR="${UPLOADS_DIR:-backend/uploads}"
    if [ -d "$UPLOADS_DIR" ]; then
        log "Backup dos uploads locais ($UPLOADS_DIR)..."
        tar czf "$UP_FILE" -C "$UPLOADS_DIR" .
        log "Uploads salvos: $UP_FILE ($(du -sh "$UP_FILE" | cut -f1))"
    else
        log "AVISO: diretório de uploads '$UPLOADS_DIR' não existe — pulando uploads"
    fi
fi

# ── 4. Cópia semanal (no dia WEEKLY_DOW; hardlink = custo zero de disco) ──────
if [ "$(date +%u)" = "$WEEKLY_DOW" ]; then
    log "Dia semanal (dow=$WEEKLY_DOW): copiando para $DIR_SEMANAL"
    for f in "$DB_FILE" "$UP_FILE"; do
        [ -f "$f" ] && ln "$f" "$DIR_SEMANAL/$(basename "$f")" 2>/dev/null \
            || { [ -f "$f" ] && cp "$f" "$DIR_SEMANAL/"; }
    done
fi

# ── 5. Rotação por contagem (mais novos primeiro; imune a mtime bagunçado) ────
rotacionar() { # $1=dir  $2=glob  $3=manter
    local dir="$1" glob="$2" manter="$3"
    ls -1t "$dir"/$glob 2>/dev/null | tail -n +"$((manter + 1))" | while read -r velho; do
        log "Rotação: removendo $velho"
        rm -f "$velho"
    done
}
rotacionar "$DIR_DIARIO"  'ejc_db_*.dump'        "$KEEP_DAILY"
rotacionar "$DIR_DIARIO"  'ejc_uploads_*.tar.gz' "$KEEP_DAILY"
rotacionar "$DIR_SEMANAL" 'ejc_db_*.dump'        "$KEEP_WEEKLY"
rotacionar "$DIR_SEMANAL" 'ejc_uploads_*.tar.gz' "$KEEP_WEEKLY"

# ── 6. Offsite opcional via rclone (não derruba o backup local se falhar) ─────
if [ -n "$RCLONE_REMOTE" ]; then
    if command -v rclone >/dev/null 2>&1; then
        for f in "$DB_FILE" "$UP_FILE"; do
            [ -f "$f" ] || continue
            log "Offsite: enviando $(basename "$f") → $RCLONE_REMOTE"
            rclone copy "$f" "$RCLONE_REMOTE/" --stats-one-line \
                || log "AVISO: upload offsite de $(basename "$f") falhou — cópia local mantida"
        done
    else
        log "AVISO: RCLONE_REMOTE definido mas rclone não está instalado"
    fi
else
    log "Offsite desativado (RCLONE_REMOTE vazio) — ver RUNBOOK_BACKUP.md"
fi

log "Retidos — diários: $(ls -1 "$DIR_DIARIO"/ejc_db_*.dump 2>/dev/null | wc -l) dumps," \
    "semanais: $(ls -1 "$DIR_SEMANAL"/ejc_db_*.dump 2>/dev/null | wc -l) dumps"
if [ "$FALHAS" -gt 0 ]; then
    log "BACKUP TERMINOU COM $FALHAS FALHA(S) — investigar!"
    exit 1
fi
log "Backup concluído com sucesso."
