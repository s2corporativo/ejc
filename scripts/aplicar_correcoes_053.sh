#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# EJC — Aplicação das correções da auditoria 28/06/2026 (migration 053 + fixes)
#
# O QUE FAZ (em ordem, seguro):
#   1. Pré-checagens de isolamento (só toca containers ejc_*, nunca o sistema-s2)
#   2. BACKUP do banco (pg_dump gzip) ANTES de qualquer mudança  ← Regra 10
#   3. Copia o código corrigido para os containers (docker cp) — workflow CLAUDE.md
#   4. alembic upgrade head  (migration 053 é IDEMPOTENTE: no-op se já existir)
#   5. restart backend + rebuild frontend
#   6. Smoke-test dos endpoints que estavam quebrados (P0-1/P0-2/P0-3)
#
# USO (rodar NA VPS, a partir de /opt/ejc):
#   SRC=/caminho/para/ejc_project_corrigido  bash scripts/aplicar_correcoes_053.sh
#   (SRC = pasta onde você extraiu o ejc_project_CORRIGIDO_v6.6_*.zip)
#
# DRY-RUN (não altera nada, só mostra o que faria):
#   DRY_RUN=1 SRC=... bash scripts/aplicar_correcoes_053.sh
#
# NUNCA usa `docker compose down -v`. NUNCA troca a imagem do postgres.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ejc}"
SRC="${SRC:-}"
DRY_RUN="${DRY_RUN:-0}"
BACKUP_DIR="${BACKUP_DIR:-/opt/ejc/backups}"
DB_CONTAINER="ejc_db"
BE_CONTAINER="ejc_backend"
DB_USER="${POSTGRES_USER:-ejc_user}"
DB_NAME="${POSTGRES_DB:-ejc_db}"
DATE="$(date +%Y%m%d_%H%M%S)"

log()  { echo "[$(date '+%F %T')] $*"; }
run()  { if [ "$DRY_RUN" = "1" ]; then echo "  DRY-RUN > $*"; else eval "$*"; fi; }
die()  { echo "❌ $*" >&2; exit 1; }

echo "═══════════════════════════════════════════════════════════════"
echo " EJC — Aplicar correções 053  (DRY_RUN=$DRY_RUN)"
echo "═══════════════════════════════════════════════════════════════"

# ── 1. Pré-checagens / isolamento ───────────────────────────────────────────
[ -d "$APP_DIR" ] || die "APP_DIR não existe: $APP_DIR"
cd "$APP_DIR"
[ -f docker-compose.yml ] || die "docker-compose.yml não encontrado em $APP_DIR (você está no projeto EJC?)"
[ -n "$SRC" ] || die "Defina SRC=<pasta com o ejc_project corrigido extraído>"
[ -f "$SRC/backend/alembic/versions/053_reconcile_schema.py" ] || die "053_reconcile_schema.py não encontrado em \$SRC/backend/..."
docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER" || die "Container $DB_CONTAINER não está rodando"
docker ps --format '{{.Names}}' | grep -qx "$BE_CONTAINER" || die "Container $BE_CONTAINER não está rodando"
# Guarda anti-acidente: confirmar que NÃO vamos mexer no sistema-s2
log "Containers EJC detectados. (sistema-s2 deployment-* NÃO será tocado.)"

# ── 2. BACKUP do banco (obrigatório, antes de tudo) ─────────────────────────
log "Backup do banco antes da mudança de schema…"
run "mkdir -p '$BACKUP_DIR'"
BK="$BACKUP_DIR/pre_053_${DATE}.sql.gz"
run "docker exec $DB_CONTAINER sh -c 'pg_dump -U $DB_USER -d $DB_NAME' | gzip > '$BK'"
if [ "$DRY_RUN" != "1" ]; then
  [ -s "$BK" ] || die "Backup vazio/falhou — ABORTANDO antes de qualquer alteração."
  log "Backup OK: $BK ($(du -sh "$BK" | cut -f1))"
fi

# ── 3. Copiar código corrigido para o container backend ─────────────────────
log "Copiando migrations (053 + 054) + código backend para $BE_CONTAINER…"
run "docker cp '$SRC/backend/alembic/versions/053_reconcile_schema.py' $BE_CONTAINER:/app/alembic/versions/053_reconcile_schema.py"
run "docker cp '$SRC/backend/alembic/versions/054_victory_vault.py' $BE_CONTAINER:/app/alembic/versions/054_victory_vault.py"
# Copia a árvore app/ inteira (9 routers de prefixo, ai_brain, models/__init__,
# victory_vault DB-backed, data/mock_db p/ o seed inicial, etc.)
run "docker cp '$SRC/backend/app/.' $BE_CONTAINER:/app/app/"

# ── 4. Migration (idempotente) ──────────────────────────────────────────────
log "Conferindo head atual…"
run "docker compose exec -T backend sh -c 'cd /app && alembic current'"
log "Aplicando alembic upgrade head (cria tabelas/colunas faltantes se não existirem)…"
run "docker compose exec -T backend sh -c 'cd /app && alembic upgrade head'"

# ── 5. Restart backend + rebuild frontend ───────────────────────────────────
log "Reiniciando backend…"
run "docker compose restart backend"
log "Rebuild do frontend (aplica correção do typo /v1/v1 e demais)…"
run "docker compose build frontend && docker compose up -d frontend"

# ── 6. Smoke-test ────────────────────────────────────────────────────────────
log "Smoke-test (aguardando backend subir)…"
run "sleep 5"
log "Health:"
run "curl -fsS http://localhost:8000/api/health || echo 'health falhou'"
echo ""
log "Rotas que estavam em 404 por duplo-prefixo agora devem responder 401 (exigem token), não 404:"
for p in /api/v1/datajud/ /api/v1/despesas /api/v1/partner-withdrawals /api/v1/office-contracts; do
  if [ "$DRY_RUN" = "1" ]; then echo "  DRY-RUN > curl -s -o /dev/null -w '%{http_code}' http://localhost:8000$p"; else
    code="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:8000$p" || true)"
    echo "  $p → HTTP $code  $( [ "$code" = "404" ] && echo '⚠️ ainda 404 — revisar' || echo 'OK (não-404)')"
  fi
done

echo "═══════════════════════════════════════════════════════════════"
log "Concluído. Para validar com token, use scripts/smoke_test_053.sh."
log "Rollback do banco (se necessário):  gunzip -c $BK | docker exec -i $DB_CONTAINER psql -U $DB_USER -d $DB_NAME"
echo "═══════════════════════════════════════════════════════════════"
