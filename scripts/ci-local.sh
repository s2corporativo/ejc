#!/usr/bin/env bash
# CI LOCAL do EJC — paridade dos gates de CI fora do GitHub Actions.
# Usa somente banco efêmero; nunca aponta para produção.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-full}" # full|required|backend|eval|frontend|p0|architecture|continuity|ui-extra|fast
PG_PORT="${PG_PORT:-5455}"
PG_CONTAINER="${PG_CONTAINER:-ejc_ci_pg_${$}}"
PGVECTOR_IMAGE="${PGVECTOR_IMAGE:-pgvector/pgvector:pg16}"
VENV_DIR="${VENV_DIR:-$ROOT/.ci-venv}"
PGDATA="${PGDATA:-$ROOT/.ci-pgdata-${$}}"
DBU="${EJC_CI_DB_USER:-ejc_user}"
DBP="${EJC_CI_DB_PASSWORD:-ejc_pass}"
DBN="${EJC_CI_DB_NAME:-ejc_db}"
PYTHON_BIN="${PYTHON_BIN:-}"
NODE_MAJOR_REQUIRED="${NODE_MAJOR_REQUIRED:-22}"

log() { printf '\n\033[1;36m[ci-local]\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }

case "$(realpath "$ROOT" 2>/dev/null || printf '%s' "$ROOT")" in
  /opt/ejc|/opt/ejc/*) die "CI local recusado em /opt/ejc (produção). Use worktree isolado em máquina de desenvolvimento/homologação." ;;
esac
if [ "${APP_ENV:-}" = "production" ] || [ "${EJC_ENV:-}" = "production" ]; then
  die "CI local recusado com ambiente de produção ativo."
fi

PG_MODE=""
PGBIN=""
_cleanup() {
  set +e
  if [ "$PG_MODE" = "docker" ]; then docker rm -f "$PG_CONTAINER" >/dev/null 2>&1; fi
  if [ "$PG_MODE" = "local" ] && [ -n "$PGBIN" ] && [ -d "$PGDATA" ]; then
    "$PGBIN/pg_ctl" -D "$PGDATA" stop -m fast >/dev/null 2>&1
    rm -rf "$PGDATA"
  fi
}
trap _cleanup EXIT

choose_python() {
  if [ -n "$PYTHON_BIN" ]; then
    command -v "$PYTHON_BIN" >/dev/null || die "PYTHON_BIN=$PYTHON_BIN não encontrado"
  elif command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN=python3.11
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
  else
    die "python3 ausente"
  fi
  local version
  version="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if [ "$version" != "3.11" ] && [ "${EJC_ALLOW_PYTHON_MISMATCH:-0}" != "1" ]; then
    die "Python $version detectado; o CI canônico usa Python 3.11. Defina EJC_ALLOW_PYTHON_MISMATCH=1 apenas para diagnóstico não-promovível."
  fi
}

ensure_venv() {
  choose_python
  if [ ! -x "$VENV_DIR/bin/python" ]; then
    log "Criando venv em $VENV_DIR…"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi
  if [ "${CI_SKIP_PIP:-0}" = "1" ]; then
    log "CI_SKIP_PIP=1 — reutilizando dependências locais."
  else
    log "Instalando dependências Python bloqueadas…"
    "$VENV_DIR/bin/python" -m pip install -q --upgrade pip
    "$VENV_DIR/bin/python" -m pip install -q -r backend/requirements.txt
  fi
}

check_node() {
  command -v npm >/dev/null 2>&1 || die "npm ausente"
  command -v node >/dev/null 2>&1 || die "node ausente"
  local major
  major="$(node -p 'process.versions.node.split(".")[0]')"
  [ "$major" = "$NODE_MAJOR_REQUIRED" ] || die "Node $(node --version) detectado; esperado major $NODE_MAJOR_REQUIRED."
}

start_pg() {
  [ -z "$PG_MODE" ] || return 0
  command -v psql >/dev/null 2>&1 || die "cliente psql ausente"
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    PG_MODE=docker
    log "Subindo PostgreSQL 16 + pgvector efêmero via Docker…"
    docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
    docker run -d --name "$PG_CONTAINER" \
      -e POSTGRES_USER="$DBU" -e POSTGRES_PASSWORD="$DBP" -e POSTGRES_DB="$DBN" \
      -p "$PG_PORT:5432" "$PGVECTOR_IMAGE" >/dev/null
    for _ in $(seq 1 45); do
      docker exec "$PG_CONTAINER" pg_isready -U "$DBU" -d "$DBN" >/dev/null 2>&1 && break
      sleep 1
    done
    docker exec "$PG_CONTAINER" pg_isready -U "$DBU" -d "$DBN" >/dev/null 2>&1 || die "PostgreSQL efêmero não ficou pronto"
  else
    PG_MODE=local
    PGBIN="$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1 || true)"
    [ -n "$PGBIN" ] || die "Sem Docker e sem PostgreSQL local com pgvector."
    log "Subindo cluster PostgreSQL local efêmero…"
    rm -rf "$PGDATA"; mkdir -p "$PGDATA"
    if id postgres >/dev/null 2>&1 && [ "$(id -u)" = "0" ]; then
      chown -R postgres "$PGDATA"; su postgres -c "$PGBIN/initdb -D '$PGDATA' -U '$DBU' --auth=trust" >/dev/null
      su postgres -c "$PGBIN/pg_ctl -D '$PGDATA' -o '-p $PG_PORT -c listen_addresses=127.0.0.1' -l '$PGDATA/pg.log' start" >/dev/null
    else
      "$PGBIN/initdb" -D "$PGDATA" -U "$DBU" --auth=trust >/dev/null
      "$PGBIN/pg_ctl" -D "$PGDATA" -o "-p $PG_PORT -c listen_addresses=127.0.0.1" -l "$PGDATA/pg.log" start >/dev/null
    fi
    for _ in $(seq 1 45); do pg_isready -h 127.0.0.1 -p "$PG_PORT" -U "$DBU" >/dev/null 2>&1 && break; sleep 1; done
    "$PGBIN/createdb" -h 127.0.0.1 -p "$PG_PORT" -U "$DBU" "$DBN" >/dev/null 2>&1 || true
  fi
  PGPASSWORD="$DBP" psql -h 127.0.0.1 -p "$PG_PORT" -U "$DBU" -d "$DBN" \
    -v ON_ERROR_STOP=1 \
    -c "CREATE EXTENSION IF NOT EXISTS vector;" \
    -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" \
    -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" >/dev/null
  export APP_ENV=development
  export DATABASE_URL="postgresql+asyncpg://$DBU:$DBP@127.0.0.1:$PG_PORT/$DBN"
  export DATABASE_URL_SYNC="postgresql://$DBU:$DBP@127.0.0.1:$PG_PORT/$DBN"
  export SCHEMA_CHECK_DATABASE_URL="$DATABASE_URL_SYNC"
  export RUN_DB_TESTS=1
  ok "PostgreSQL efêmero pronto em 127.0.0.1:$PG_PORT"
}

run_backend() {
  ensure_venv; start_pg
  local PY="$VENV_DIR/bin/python"
  log "Sintaxe dos scripts críticos de produção…"
  bash -n scripts/backup/ativar_backup.sh scripts/deploy_vps_safe.sh
  log "Compatibilidade dos modelos RAG (sem baixar pesos)…"
  (cd backend && "$PY" -c "from app.services.embedding_service import validar_modelo_local; ok,msg=validar_modelo_local(); print(msg); raise SystemExit(0 if ok else 1)")
  (cd backend && "$PY" -c "from app.core.config import get_settings; from fastembed.rerank.cross_encoder import TextCrossEncoder; s=get_settings(); nomes={m['model'] for m in TextCrossEncoder.list_supported_models()}; assert s.RAG_RERANK_MODEL in nomes, s.RAG_RERANK_MODEL; print(s.RAG_RERANK_MODEL)")
  log "Ruff…"; (cd backend && "$PY" -m ruff check app --output-format=concise)
  log "pip-audit…"; "$PY" -m pip install -q pip-audit; (cd backend && "$VENV_DIR/bin/pip-audit" -r requirements.txt --desc)
  log "Alembic upgrade head…"; (cd backend && "$PY" -m alembic upgrade head)
  log "Pytest completo com banco + cobertura >=65%…"
  (cd backend && "$PY" -m pytest tests -q --tb=short --maxfail=25 --cov=app --cov-report=term-missing:skip-covered --cov-fail-under=65)
  ok "Backend CI equivalente OK"
}

run_eval() {
  ensure_venv
  local PY="$VENV_DIR/bin/python"
  log "Eval smoke dos gold sets…"; (cd backend && "$PY" -m app.eval.run_eval --smoke)
  log "Eval de trajetória do agente…"; (cd backend && "$PY" -m app.eval.agent_trajectory --min-tool 1.0 --max-violacoes-hitl 0)
  ok "Eval offline OK"
}

run_frontend() {
  check_node
  log "Frontend: npm ci…"; (cd frontend && npm ci --no-fund)
  log "Frontend: Prettier…"; (cd frontend && npm run format:check)
  log "Frontend: Vitest…"; (cd frontend && npm run test -- --reporter=dot)
  log "Frontend: npm audit high…"; (cd frontend && npm audit --audit-level=high)
  log "Frontend: typecheck/build…"; (cd frontend && npm run build)
  ok "Frontend CI equivalente OK"
}

run_p0() {
  log "Release Gate P0…"; bash scripts/ci_guard.sh
  log "Backup wrapper cifrado…"; bash scripts/tests/test_backup_wrapper.sh
  log "Rollback de deploy…"; bash scripts/tests/test_deploy_rollback.sh
  log "Recuperação idempotente de runner…"; bash scripts/tests/test_selfhosted_runner_setup.sh
  ok "P0 guard equivalente OK"
}

run_architecture() {
  local out
  out="$(mktemp -d)"
  log "Architecture Inventory: testes…"
  python3 -m unittest scripts.tests.test_generate_architecture_inventory scripts.tests.test_refine_architecture_inventory -v
  log "Architecture Inventory: geração/refino…"
  python3 scripts/generate_architecture_inventory.py --output "$out" --check
  python3 scripts/refine_architecture_inventory.py --output "$out" --check
  rm -rf "$out"
  ok "Architecture Inventory OK"
}

run_continuity() {
  ensure_venv; start_pg
  local PY="$VENV_DIR/bin/python"
  export RESTORE_DRILL_ALLOW=1
  export RESTORE_DRILL_REPORT="${RESTORE_DRILL_REPORT:-$ROOT/.ci-restore-drill-report.json}"
  log "Continuidade: prova integral backup/restore…"
  "$PY" -m py_compile scripts/backup/restore_drill.py
  (cd backend && PYTHONPATH=. "$PY" ../scripts/backup/restore_drill.py)
  [ -s "$RESTORE_DRILL_REPORT" ] || die "restore drill não produziu relatório"
  ok "Continuidade backup/restore OK"
}

run_ui_extra() {
  check_node
  [ -d frontend/node_modules ] || (cd frontend && npm ci --no-fund)
  log "Frontend extra: ESLint…"; (cd frontend && npm run lint:eslint)
  log "Frontend extra: build…"; (cd frontend && npm run build)
  log "Frontend extra: Playwright/Chromium…"
  (cd frontend && npm install --no-save --package-lock=false playwright@1.56.1)
  (cd frontend && npx playwright install --with-deps chromium)
  (cd frontend && SCREENSHOT_DIR=tests/__out__/login npm run test:responsive)
  (cd frontend && PREMIUM_SCREENSHOT_DIR=tests/__out__/premium-dashboard npm run test:premium-responsive)
  ok "Frontend browser responsivo OK"
}

run_fast() {
  ensure_venv
  local PY="$VENV_DIR/bin/python"
  (cd backend && "$PY" -m ruff check app --output-format=concise)
  (cd backend && "$PY" -m pytest tests -q --ignore-glob='*dblevel*')
  ok "Fast gate OK"
}

log "EJC CI local — modo: $MODE"
case "$MODE" in
  backend) run_backend ;;
  eval) run_eval ;;
  frontend) run_frontend ;;
  p0) run_p0 ;;
  architecture) run_architecture ;;
  continuity) run_continuity ;;
  ui-extra) run_ui_extra ;;
  fast) run_fast ;;
  required) run_backend; run_eval; run_frontend; run_p0 ;;
  full) run_backend; run_eval; run_frontend; run_p0; run_architecture; run_continuity; run_ui_extra ;;
  *) die "modo inválido: $MODE" ;;
esac
ok "CI local concluído com sucesso."
