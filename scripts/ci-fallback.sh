#!/usr/bin/env bash
# CI fallback do EJC para runner dedicado, fora da VPS de produção.
# Executa validação bloqueante equivalente aos gates principais quando o
# GitHub-hosted falha antes do primeiro step. Nunca deve ser usado em produção.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REPORT_DIR="${EJC_CI_REPORT_DIR:-$ROOT/.ci-fallback-report}"
VENV_DIR="${VENV_DIR:-$ROOT/.ci-fallback-venv}"
PG_PORT="${PG_PORT:-55452}"
PG_CONTAINER="${PG_CONTAINER:-ejc_ci_fallback_pg}"
PGVECTOR_IMAGE="${PGVECTOR_IMAGE:-pgvector/pgvector:pg16}"
PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/ejc-ci-browsers}"
export PLAYWRIGHT_BROWSERS_PATH

log() { printf '\n\033[1;36m[ci-fallback]\033[0m %s\n' "$*"; }
ok() { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }

proteger_producao() {
  [ "${APP_ENV:-}" != "production" ] || die "APP_ENV=production: fallback recusado."
  case "$ROOT" in
    /opt/ejc|/opt/ejc/*) die "workspace sob /opt/ejc: fallback recusado." ;;
  esac
  [ ! -e /opt/ejc/.env ] || die "marcador /opt/ejc/.env detectado: host de produção recusado."
  [ ! -e /opt/ejc/.deployed_sha ] || die "marcador /opt/ejc/.deployed_sha detectado: host de produção recusado."
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    local nomes
    nomes="$(docker ps --format '{{.Names}}' 2>/dev/null || true)"
    for nome in ejc_backend ejc_db ejc_frontend ejc_worker; do
      if printf '%s\n' "$nomes" | grep -qx "$nome"; then
        die "container produtivo $nome detectado: fallback recusado."
      fi
    done
  fi
}

cleanup() {
  set +e
  if command -v docker >/dev/null 2>&1; then
    docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

proteger_producao

if [ "${EJC_CI_GUARD_ONLY:-0}" = "1" ]; then
  ok "Guard fail-closed aprovado; host não parece produção."
  exit 0
fi

for cmd in git python3 npm docker psql; do
  command -v "$cmd" >/dev/null 2>&1 || die "dependência ausente: $cmd"
done
docker info >/dev/null 2>&1 || die "Docker indisponível para o usuário do runner."

rm -rf "$REPORT_DIR"
mkdir -p "$REPORT_DIR"
SHA="$(git rev-parse HEAD)"
printf 'sha=%s\nstarted_at=%s\n' "$SHA" "$(date -u +%FT%TZ)" > "$REPORT_DIR/metadata.txt"

log "Autoauditoria do isolamento do runner/fallback"
bash scripts/tests/test_ci_fallback_isolation.sh \
  2>&1 | tee "$REPORT_DIR/ci-fallback-isolation.log"

log "Release Gate P0"
bash scripts/ci_guard.sh 2>&1 | tee "$REPORT_DIR/ci-guard.log"
bash scripts/tests/test_backup_wrapper.sh 2>&1 | tee "$REPORT_DIR/backup-wrapper.log"
bash scripts/tests/test_deploy_rollback.sh 2>&1 | tee "$REPORT_DIR/deploy-rollback.log"
bash scripts/tests/test_selfhosted_runner_setup.sh 2>&1 | tee "$REPORT_DIR/runner-setup.log"

log "Architecture Inventory"
python3 -m unittest \
  scripts.tests.test_generate_architecture_inventory \
  scripts.tests.test_refine_architecture_inventory \
  -v 2>&1 | tee "$REPORT_DIR/architecture-tests.log"
TMP_ARCH="$(mktemp -d)"
python3 scripts/generate_architecture_inventory.py --output "$TMP_ARCH" --check
python3 scripts/refine_architecture_inventory.py --output "$TMP_ARCH" --check
cp "$TMP_ARCH/README.md" "$REPORT_DIR/architecture-summary.md"
rm -rf "$TMP_ARCH"

log "Preparando Python"
if [ ! -d "$VENV_DIR" ]; then python3 -m venv "$VENV_DIR"; fi
PY="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
"$PIP" install -q --upgrade pip
"$PIP" install -q -r backend/requirements.txt
"$PIP" install -q pip-audit

log "PostgreSQL+pgvector efêmero"
docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$PG_CONTAINER" \
  -e POSTGRES_USER=ejc_user \
  -e POSTGRES_PASSWORD=ejc_pass \
  -e POSTGRES_DB=ejc_db \
  -p "127.0.0.1:${PG_PORT}:5432" \
  "$PGVECTOR_IMAGE" >/dev/null
for _ in $(seq 1 40); do
  if PGPASSWORD=ejc_pass psql -h 127.0.0.1 -p "$PG_PORT" -U ejc_user -d ejc_db -c 'select 1' >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
PGPASSWORD=ejc_pass psql -h 127.0.0.1 -p "$PG_PORT" -U ejc_user -d ejc_db \
  -c 'CREATE EXTENSION IF NOT EXISTS vector;' \
  -c 'CREATE EXTENSION IF NOT EXISTS pg_trgm;' \
  -c 'CREATE EXTENSION IF NOT EXISTS pgcrypto;' >/dev/null

export APP_ENV=development
export RUN_DB_TESTS=1
export DATABASE_URL="postgresql+asyncpg://ejc_user:ejc_pass@127.0.0.1:${PG_PORT}/ejc_db"
export DATABASE_URL_SYNC="postgresql://ejc_user:ejc_pass@127.0.0.1:${PG_PORT}/ejc_db"
export SCHEMA_CHECK_DATABASE_URL="$DATABASE_URL_SYNC"

log "Backend: lint, auditoria, migrations e suíte completa"
(
  cd backend
  "$PY" -m ruff check app --output-format=concise 2>&1 | tee "$REPORT_DIR/ruff.log"
  "$VENV_DIR/bin/pip-audit" -r requirements.txt --desc 2>&1 | tee "$REPORT_DIR/pip-audit.log"
  "$PY" -m alembic upgrade head
  "$PY" -m pytest tests -q --tb=short --maxfail=25 \
    --cov=app --cov-report=term-missing:skip-covered \
    --cov-report="xml:$REPORT_DIR/backend-coverage.xml" --cov-fail-under=65 \
    2>&1 | tee "$REPORT_DIR/backend-tests.log"
  "$PY" -m app.eval.run_eval --smoke 2>&1 | tee "$REPORT_DIR/eval-smoke.log"
  "$PY" -m app.eval.agent_trajectory --min-tool 1.0 --max-violacoes-hitl 0 \
    2>&1 | tee "$REPORT_DIR/agent-trajectory.log"
)

log "Continuidade: restore drill em banco efêmero"
export RESTORE_DRILL_ALLOW=1
export RESTORE_DRILL_REPORT="$REPORT_DIR/restore-drill-report.json"
(
  cd backend
  "$PY" -m py_compile ../scripts/backup/restore_drill.py
  PYTHONPATH=. "$PY" ../scripts/backup/restore_drill.py
)

log "Frontend: formatação, testes, auditoria, lint e build"
(
  cd frontend
  npm ci --no-fund
  npm run format:check 2>&1 | tee "$REPORT_DIR/prettier.log"
  npm run test -- --reporter=dot 2>&1 | tee "$REPORT_DIR/frontend-tests.log"
  npm audit --audit-level=high 2>&1 | tee "$REPORT_DIR/npm-audit.log"
  npm run lint:eslint 2>&1 | tee "$REPORT_DIR/eslint.log"
  npm run build 2>&1 | tee "$REPORT_DIR/frontend-build.log"
  npm install --no-save --package-lock=false playwright@1.56.1 >/dev/null
  npx playwright install chromium >/dev/null
  SCREENSHOT_DIR="$REPORT_DIR/login" npm run test:responsive \
    2>&1 | tee "$REPORT_DIR/responsive-login.log"
  PREMIUM_SCREENSHOT_DIR="$REPORT_DIR/premium-dashboard" npm run test:premium-responsive \
    2>&1 | tee "$REPORT_DIR/responsive-premium.log"
)

printf 'finished_at=%s\nresult=success\n' "$(date -u +%FT%TZ)" >> "$REPORT_DIR/metadata.txt"
ok "Fallback completo aprovado para $SHA."
