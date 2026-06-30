#!/usr/bin/env bash
# ── EJC — Restauração de backup ──────────────────────────────────────────────
# Uso: bash scripts/restore.sh /var/backups/ejc/ejc_db_YYYYMMDD_HHMM.dump
set -euo pipefail
[ $# -eq 1 ] || { echo "Uso: $0 <arquivo.dump>"; exit 1; }
source .env 2>/dev/null || true
PGUSER="${POSTGRES_USER:-ejc_user}"
PGDB="${POSTGRES_DB:-ejc_db}"

echo "⚠️  Isso vai SOBRESCREVER o banco $PGDB. Ctrl+C p/ abortar (5s)..."
sleep 5
docker compose exec -T db pg_restore -U "$PGUSER" -d "$PGDB" --clean --if-exists < "$1"
echo "✅ Banco restaurado de $1"
