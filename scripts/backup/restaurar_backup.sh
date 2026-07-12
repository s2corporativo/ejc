#!/usr/bin/env bash
# ── EJC — Restauração guiada de backup (PostgreSQL -Fc + uploads/GED) ────────
#
# Restaura um dump gerado por backup_diario.sh. DESTRUTIVO: sobrescreve o banco
# alvo. Exige confirmação explícita digitando o nome do banco. Faça um dump de
# segurança do estado atual ANTES (o script oferece fazer isso).
#
# Uso:
#   bash scripts/backup/restaurar_backup.sh <arquivo.dump> [arquivo_uploads.tar.gz]
#
# Config (override por env var — mesmas do backup):
#   EJC_BACKUP_MODE   docker | local | auto (default auto)
#   DB_CONTAINER      container Postgres (default ejc_db)
#   APP_CONTAINER     container backend  (default ejc_backend)
#   PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE  (modo local)
#   ASSUME_YES=1      pula a confirmação interativa (use com MUITO cuidado)
set -euo pipefail

DUMP_FILE="${1:-}"
UPLOADS_FILE="${2:-}"
DB_CONTAINER="${DB_CONTAINER:-ejc_db}"
APP_CONTAINER="${APP_CONTAINER:-ejc_backend}"
EJC_BACKUP_MODE="${EJC_BACKUP_MODE:-auto}"
UPLOADS_DIR_CONTAINER="/app/uploads"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
erro() { echo "ERRO: $*" >&2; exit 1; }

[ -n "$DUMP_FILE" ] || erro "uso: $0 <arquivo.dump> [uploads.tar.gz]"
[ -f "$DUMP_FILE" ] || erro "dump não encontrado: $DUMP_FILE"

# ── Credenciais (mesmo padrão do backup_diario.sh) ────────────────────────────
if [ -f .env ]; then
    set +u
    POSTGRES_USER_ENV=$(grep -E '^POSTGRES_USER=' .env | tail -1 | cut -d= -f2-)
    POSTGRES_DB_ENV=$(grep -E '^POSTGRES_DB=' .env | tail -1 | cut -d= -f2-)
    POSTGRES_PASSWORD_ENV=$(grep -E '^POSTGRES_PASSWORD=' .env | tail -1 | cut -d= -f2-)
    set -u
fi
PGUSER_EFF="${PGUSER:-${POSTGRES_USER_ENV:-ejc_user}}"
PGDB_EFF="${PGDATABASE:-${POSTGRES_DB_ENV:-ejc_db}}"

if [ "$EJC_BACKUP_MODE" = "auto" ]; then
    if docker exec "$DB_CONTAINER" true 2>/dev/null; then EJC_BACKUP_MODE="docker"; else EJC_BACKUP_MODE="local"; fi
fi

# ── Verifica integridade do dump ANTES de tocar no banco ──────────────────────
log "Verificando o dump ($DUMP_FILE)..."
if [ "$EJC_BACKUP_MODE" = "docker" ]; then
    N_OBJ=$(docker exec -i "$DB_CONTAINER" pg_restore --list < "$DUMP_FILE" | grep -c '^[0-9]' || true)
else
    N_OBJ=$(pg_restore --list "$DUMP_FILE" | grep -c '^[0-9]' || true)
fi
[ "${N_OBJ:-0}" -gt 0 ] || erro "dump inválido/corrompido ($DUMP_FILE)"
log "Dump OK: $N_OBJ objetos. Modo: $EJC_BACKUP_MODE | banco alvo: $PGDB_EFF"

# ── Confirmação explícita (DESTRUTIVO) ────────────────────────────────────────
cat <<AVISO

  ┌──────────────────────────────────────────────────────────────┐
  │  ATENÇÃO: a restauração VAI SOBRESCREVER o banco "$PGDB_EFF".
  │  Todos os dados atuais serão substituídos pelos do backup.
  │  Recomendado: gere um backup do estado ATUAL antes de seguir.
  └──────────────────────────────────────────────────────────────┘
AVISO
if [ "${ASSUME_YES:-0}" != "1" ]; then
    read -r -p "Fazer backup de segurança do estado atual agora? [S/n] " bkp
    if [ "${bkp:-S}" != "n" ] && [ "${bkp:-S}" != "N" ]; then
        log "Gerando backup de segurança pré-restauração..."
        BACKUP_BASE_DIR="${BACKUP_BASE_DIR:-/opt/ejc/backups}" \
            bash "$(dirname "$0")/backup_diario.sh" || log "AVISO: backup de segurança falhou — decida se continua."
    fi
    read -r -p "Digite o nome do banco para CONFIRMAR a restauração ($PGDB_EFF): " conf
    [ "$conf" = "$PGDB_EFF" ] || erro "confirmação não confere — abortado."
fi

# ── Restauração do banco (--clean --if-exists: dropa e recria objetos) ─────────
log "Restaurando banco $PGDB_EFF ..."
if [ "$EJC_BACKUP_MODE" = "docker" ]; then
    docker exec -i "$DB_CONTAINER" pg_restore -U "$PGUSER_EFF" -d "$PGDB_EFF" \
        --clean --if-exists --no-owner < "$DUMP_FILE"
else
    PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD_ENV:-}}" \
        pg_restore -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" -U "$PGUSER_EFF" \
        -d "$PGDB_EFF" --clean --if-exists --no-owner "$DUMP_FILE"
fi
log "Banco restaurado."

# ── Restauração dos uploads (opcional) ────────────────────────────────────────
if [ -n "$UPLOADS_FILE" ]; then
    [ -f "$UPLOADS_FILE" ] || erro "arquivo de uploads não encontrado: $UPLOADS_FILE"
    log "Restaurando uploads de $UPLOADS_FILE ..."
    if [ "$EJC_BACKUP_MODE" = "docker" ]; then
        docker exec -i "$APP_CONTAINER" sh -c "mkdir -p $UPLOADS_DIR_CONTAINER && tar xzf - -C $UPLOADS_DIR_CONTAINER" < "$UPLOADS_FILE"
    else
        UPLOADS_DIR="${UPLOADS_DIR:-backend/uploads}"
        mkdir -p "$UPLOADS_DIR"
        tar xzf "$UPLOADS_FILE" -C "$UPLOADS_DIR"
    fi
    log "Uploads restaurados."
else
    log "Sem arquivo de uploads informado — restaurado somente o banco."
fi

log "Restauração concluída. Rode 'alembic upgrade head' se o backup for de um schema anterior."
