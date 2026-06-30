#!/usr/bin/env bash
# ── EJC — Restauração de backup ──────────────────────────────────────────────
# Uso: bash scripts/restore.sh <arquivo>
#
# Aceita os formatos gerados pelo backup.sh e variantes:
#   *.sql.gz   → SQL puro comprimido  (gunzip | psql)   ← formato atual do backup.sh
#   *.sql      → SQL puro             (psql)
#   *.dump     → formato custom/tar   (pg_restore)
#
# Antes de sobrescrever, gera um backup de segurança automático do estado atual.
set -euo pipefail

[ $# -eq 1 ] || { echo "Uso: $0 <arquivo.sql.gz | arquivo.sql | arquivo.dump>"; exit 1; }
ARQ="$1"
[ -f "$ARQ" ] || { echo "ERRO: arquivo não encontrado: $ARQ"; exit 1; }

# Mesmas variáveis do backup.sh (fonte única de verdade do nome do container).
DB_CONTAINER="${DB_CONTAINER:-ejc_db}"
source .env 2>/dev/null || true
PGUSER="${POSTGRES_USER:-ejc_user}"
PGDB="${POSTGRES_DB:-ejc_db}"

# Confere que o container está de pé.
docker exec "$DB_CONTAINER" true 2>/dev/null \
  || { echo "ERRO: container '$DB_CONTAINER' não está rodando. Ajuste DB_CONTAINER=... (veja 'docker ps')."; exit 1; }

echo "⚠️  Isso vai SOBRESCREVER o banco '$PGDB' no container '$DB_CONTAINER'."
echo "    Arquivo de origem: $ARQ"
echo "    Ctrl+C para abortar (10s)..."
sleep 10

# ── Backup de segurança automático do estado atual (antes de sobrescrever) ────
SAFETY="/tmp/ejc_pre_restore_$(date +%Y%m%d_%H%M%S).sql.gz"
echo "[$(date)] Salvando rede de segurança do estado atual em: $SAFETY"
docker exec "$DB_CONTAINER" pg_dump -U "$PGUSER" "$PGDB" | gzip > "$SAFETY"
echo "[$(date)] Rede de segurança salva ($(du -sh "$SAFETY" | cut -f1)). Se algo der errado, restaure este arquivo."

# ── Restauração conforme o formato do arquivo ─────────────────────────────────
echo "[$(date)] Iniciando restauração..."
case "$ARQ" in
  *.sql.gz)
    gunzip -c "$ARQ" | docker exec -i "$DB_CONTAINER" psql -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1
    ;;
  *.sql)
    docker exec -i "$DB_CONTAINER" psql -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1 < "$ARQ"
    ;;
  *.dump|*.custom|*.tar)
    docker exec -i "$DB_CONTAINER" pg_restore -U "$PGUSER" -d "$PGDB" --clean --if-exists < "$ARQ"
    ;;
  *)
    echo "ERRO: extensão não reconhecida. Use .sql.gz, .sql ou .dump"; exit 1
    ;;
esac

echo "✅ Banco '$PGDB' restaurado a partir de $ARQ"
echo "   (Rede de segurança do estado anterior: $SAFETY)"
