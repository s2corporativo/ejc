#!/usr/bin/env bash
# ── EJC — Restauração de backup ──────────────────────────────────────────────
# Uso: bash scripts/restore.sh <arquivo>
#
# Aceita os formatos gerados pelo backup.sh e variantes:
#   *.sql.gz          → SQL puro comprimido  (gunzip | psql)  ← formato do backup.sh
#   *.sql             → SQL puro             (psql)
#   *.dump            → formato custom/tar   (pg_restore)
#   ejc_uploads_*.tar.gz → arquivos/GED      (tar -x em /app/uploads no ejc_backend)
#
# Antes de sobrescrever, gera um backup de segurança automático do estado atual.
#
# TESTE DE RESTAURAÇÃO (validar o backup sem tocar em produção — rodar periodicamente):
#   1. Suba um Postgres descartável:  docker run --rm -d --name ejc_db_teste \
#        -e POSTGRES_USER=ejc_user -e POSTGRES_PASSWORD=x -e POSTGRES_DB=ejc_db \
#        pgvector/pgvector:pg16
#   2. Restaure o último dump nele:   DB_CONTAINER=ejc_db_teste bash scripts/restore.sh \
#        /opt/ejc/backups/ejc_db_AAAAMMDD_HHMMSS.sql.gz   (responda ao aviso de 10s)
#   3. Confira contagens:  docker exec ejc_db_teste psql -U ejc_user -d ejc_db \
#        -c "SELECT count(*) FROM clients; SELECT count(*) FROM cases;"
#   4. docker rm -f ejc_db_teste
#   Uploads: extraia ejc_uploads_*.tar.gz num diretório temporário e confira os arquivos.
set -euo pipefail

[ $# -eq 1 ] || { echo "Uso: $0 <ejc_db_*.sql.gz | *.sql | *.dump | ejc_uploads_*.tar.gz>"; exit 1; }
ARQ="$1"
[ -f "$ARQ" ] || { echo "ERRO: arquivo não encontrado: $ARQ"; exit 1; }

# ── Restauração de UPLOADS/GED (tarball gerado pelo backup.sh) ────────────────
# Detecta o tarball de uploads pelo nome e restaura os ARQUIVOS (o pg_dump só
# traz metadados). Gera uma rede de segurança dos uploads atuais antes.
APP_CONTAINER="${APP_CONTAINER:-ejc_backend}"
UPLOADS_DIR_CONTAINER="/app/uploads"
case "$(basename "$ARQ")" in
  ejc_uploads_*.tar.gz|*uploads*.tar.gz)
    docker exec "$APP_CONTAINER" true 2>/dev/null \
      || { echo "ERRO: container '$APP_CONTAINER' não está rodando. Ajuste APP_CONTAINER=..."; exit 1; }
    echo "⚠️  Isso vai SOBRESCREVER os uploads em $APP_CONTAINER:$UPLOADS_DIR_CONTAINER."
    echo "    Arquivo: $ARQ ; Ctrl+C para abortar (10s)..."
    sleep 10
    SAFETY="/tmp/ejc_uploads_pre_restore_$(date +%Y%m%d_%H%M%S).tar.gz"
    echo "[$(date)] Rede de segurança dos uploads atuais → $SAFETY"
    docker exec "$APP_CONTAINER" tar czf - -C "$UPLOADS_DIR_CONTAINER" . > "$SAFETY" 2>/dev/null || true
    echo "[$(date)] Restaurando uploads..."
    docker exec -i "$APP_CONTAINER" sh -c "mkdir -p '$UPLOADS_DIR_CONTAINER' && tar xzf - -C '$UPLOADS_DIR_CONTAINER'" < "$ARQ"
    echo "✅ Uploads restaurados a partir de $ARQ (rede de segurança: $SAFETY)"
    exit 0
    ;;
esac

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
