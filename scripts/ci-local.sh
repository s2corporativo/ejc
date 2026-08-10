#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# CI LOCAL / FALLBACK AUTÔNOMO DO EJC
#
# Objetivo: reproduzir localmente os gates críticos usados no GitHub Actions sem
# transformar o GitHub em ambiente de diagnóstico. Pode rodar em worktree, VPS
# de desenvolvimento ou máquina isolada. NUNCA opera no banco de produção.
#
# Modos:
#   fast         guardas P0 + testes backend sem banco
#   backend      backend completo com PostgreSQL+pgvector, lint, audit e cobertura
#   frontend     prettier + vitest + npm audit + eslint + typecheck/build
#   eval         gold sets + trajetória do agente (offline)
#   release      ci_guard + provas de backup/rollback/runner
#   governance   guardas locais de migration/segredos/branch (sem metadata de PR)
#   architecture inventário arquitetural completo
#   continuity   backup cifrado + restore drill em banco efêmero
#   browser      ESLint/build + Chromium responsivo (Playwright)
#   full         governance + release + architecture + backend + eval + frontend
#   parity       full + continuity + browser (paridade operacional máxima)
#
# Variáveis úteis:
#   CI_SKIP_PIP=1                 não reinstala requirements Python
#   EJC_SKIP_NPM_CI=1             não reinstala node_modules
#   EJC_SKIP_BROWSER_INSTALL=1     não instala Playwright/Chromium
#   EJC_BASE_REF=main              base local para governança
#   EJC_CI_REPORT_DIR=/fora/repo   diretório de logs (default: /tmp)
#
# Falha de qualquer gate => exit != 0. Logs ficam FORA do repositório por padrão.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-full}"
PG_PORT="${PG_PORT:-5455}"
PG_CONTAINER="${PG_CONTAINER:-ejc_ci_pg}"
PGVECTOR_IMAGE="${PGVECTOR_IMAGE:-pgvector/pgvector:pg16}"
VENV_DIR="${VENV_DIR:-$ROOT/.ci-venv}"
PGDATA="${PGDATA:-$ROOT/.ci-pgdata}"
DBU="ejc_user"
DBP="ejc_pass"
DBN="ejc_db"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_DIR="${EJC_CI_REPORT_DIR:-${TMPDIR:-/tmp}/ejc-ci-local/$STAMP}"
mkdir -p "$REPORT_DIR"
exec > >(tee -a "$REPORT_DIR/ci-local.log") 2>&1

log()  { printf '\n\033[1;36m[ci-local]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mAVISO: %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }

PG_MODE=""
PGBIN=""
PY_DEPS_READY=0
NODE_DEPS_READY=0

stop_pg() {
  set +e
  if [ "$PG_MODE" = "docker" ]; then
    docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
  elif [ "$PG_MODE" = "local" ] && [ -d "$PGDATA" ] && [ -n "$PGBIN" ]; then
    "$PGBIN/pg_ctl" -D "$PGDATA" stop -m fast >/dev/null 2>&1 || true
    rm -rf "$PGDATA"
  fi
  PG_MODE=""
  set -e
}

_cleanup() { stop_pg; }
trap _cleanup EXIT

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "comando ausente: $1"
}

ensure_python_deps() {
  require_cmd python3
  if [ ! -d "$VENV_DIR" ]; then
    log "Criando venv isolado em $VENV_DIR…"
    python3 -m venv "$VENV_DIR"
  fi
  if [ "$PY_DEPS_READY" = "1" ]; then return 0; fi
  if [ "${CI_SKIP_PIP:-0}" = "1" ]; then
    log "CI_SKIP_PIP=1 — usando dependências Python já instaladas."
  else
    log "Instalando dependências Python bloqueadas do backend…"
    "$VENV_DIR/bin/pip" install -q --upgrade pip
    "$VENV_DIR/bin/pip" install -q -r backend/requirements.txt
  fi
  PY_DEPS_READY=1
}

ensure_node_deps() {
  require_cmd npm
  if [ "$NODE_DEPS_READY" = "1" ]; then return 0; fi
  if [ "${EJC_SKIP_NPM_CI:-0}" = "1" ]; then
    log "EJC_SKIP_NPM_CI=1 — usando node_modules existente."
  else
    log "Frontend: npm ci (package-lock como fonte da verdade)…"
    ( cd frontend && npm ci --no-fund )
  fi
  NODE_DEPS_READY=1
}

start_pg() {
  [ -z "$PG_MODE" ] || return 0
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    PG_MODE="docker"
    log "Subindo PostgreSQL+pgvector efêmero via Docker ($PGVECTOR_IMAGE)…"
    docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
    docker run -d --name "$PG_CONTAINER" \
      -e POSTGRES_USER="$DBU" -e POSTGRES_PASSWORD="$DBP" -e POSTGRES_DB="$DBN" \
      -p "$PG_PORT:5432" "$PGVECTOR_IMAGE" >/dev/null
    local pronto=0
    for _ in $(seq 1 45); do
      if docker exec "$PG_CONTAINER" pg_isready -U "$DBU" -d "$DBN" >/dev/null 2>&1; then
        pronto=1; break
      fi
      sleep 1
    done
    [ "$pronto" = "1" ] || die "PostgreSQL efêmero não ficou pronto"
    docker exec "$PG_CONTAINER" psql -U "$DBU" -d "$DBN" -v ON_ERROR_STOP=1 \
      -c "CREATE EXTENSION IF NOT EXISTS vector;" \
      -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" \
      -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" >/dev/null
  else
    PG_MODE="local"
    PGBIN="$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1 || true)"
    [ -n "$PGBIN" ] || die "sem Docker e sem PostgreSQL local com pgvector"
    log "Sem Docker — subindo PostgreSQL local efêmero ($PGBIN)…"
    rm -rf "$PGDATA"
    mkdir -p "$PGDATA"
    local SU=(bash -c)
    if id postgres >/dev/null 2>&1 && [ "$(id -u)" = "0" ]; then
      chown -R postgres "$PGDATA"
      SU=(su postgres -c)
    fi
    "${SU[@]}" "$PGBIN/initdb -D '$PGDATA' -U '$DBU' --auth=trust" >/dev/null
    "${SU[@]}" "$PGBIN/pg_ctl -D '$PGDATA' -o '-p $PG_PORT -c listen_addresses=127.0.0.1' -l '$PGDATA/pg.log' start" >/dev/null
    local pronto=0
    for _ in $(seq 1 45); do
      if "$PGBIN/pg_isready" -h 127.0.0.1 -p "$PG_PORT" -U "$DBU" >/dev/null 2>&1; then
        pronto=1; break
      fi
      sleep 1
    done
    [ "$pronto" = "1" ] || die "PostgreSQL local efêmero não ficou pronto"
    "$PGBIN/createdb" -h 127.0.0.1 -p "$PG_PORT" -U "$DBU" "$DBN" >/dev/null 2>&1 || true
    "$PGBIN/psql" -h 127.0.0.1 -p "$PG_PORT" -U "$DBU" -d "$DBN" -v ON_ERROR_STOP=1 \
      -c "CREATE EXTENSION IF NOT EXISTS vector;" \
      -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" \
      -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" >/dev/null
  fi

  export APP_ENV=development
  export DATABASE_URL="postgresql+asyncpg://$DBU:$DBP@127.0.0.1:$PG_PORT/$DBN"
  export DATABASE_URL_SYNC="postgresql://$DBU:$DBP@127.0.0.1:$PG_PORT/$DBN"
  export SCHEMA_CHECK_DATABASE_URL="$DATABASE_URL_SYNC"
  export RUN_DB_TESTS=1
  ok "PostgreSQL efêmero pronto em 127.0.0.1:$PG_PORT ($PG_MODE)"
}

run_script_syntax() {
  log "Validando sintaxe dos scripts críticos de produção…"
  bash -n scripts/backup/ativar_backup.sh scripts/deploy_vps_safe.sh
  ok "Sintaxe de scripts críticos OK"
}

run_governance() {
  log "Governança local: migration, segredos e branch…"
  require_cmd git
  local base="${EJC_BASE_REF:-main}"
  local base_commit=""
  if git rev-parse --verify "$base" >/dev/null 2>&1; then
    base_commit="$(git rev-parse "$base")"
  elif git rev-parse --verify "origin/$base" >/dev/null 2>&1; then
    base_commit="$(git rev-parse "origin/$base")"
  else
    die "base local '$base' não encontrada; atualize a cópia de trabalho quando o remoto voltar"
  fi

  local changed="$REPORT_DIR/alterados.txt"
  {
    git diff --name-only "$base_commit...HEAD" 2>/dev/null || true
    git diff --name-only 2>/dev/null || true
    git diff --cached --name-only 2>/dev/null || true
  } | sed '/^$/d' | sort -u > "$changed"

  if grep -Eq '^backend/alembic/versions/' "$changed"; then
    grep -qx 'backend/alembic/MIGRATION_RESERVATIONS.md' "$changed" \
      || die "migration alterada sem atualizar MIGRATION_RESERVATIONS.md"
  fi

  local patterns='(AKIA[0-9A-Z]{16})|(-----BEGIN [A-Z ]*PRIVATE KEY-----)|(sk-[A-Za-z0-9]{20,})|(ghp_[A-Za-z0-9]{30,})|(xox[baprs]-[A-Za-z0-9-]{10,})'
  local found=0
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    case "$f" in
      *.lock|*.min.js|*.map|*.svg|*.env.example|.env.example) continue ;;
    esac
    if grep -EIn "$patterns" "$f" >/dev/null 2>&1; then
      echo "possível segredo versionado: $f" >&2
      found=1
    fi
  done < "$changed"
  if grep -Eq '(^|/)\.env$|(^|/)\.env\.(local|production|prod)$' "$changed"; then
    echo "arquivo .env real detectado no diff" >&2
    found=1
  fi
  [ "$found" = "0" ] || die "governança local detectou possível segredo"

  local branch
  branch="$(git branch --show-current 2>/dev/null || true)"
  [ "$branch" != "main" ] && [ "$branch" != "master" ] \
    || die "não execute escrita/integração diretamente na branch protegida"

  ok "Governança local OK (metadados/reviews de PR continuam sendo confirmação remota)"
}

run_release() {
  run_script_syntax
  log "Release gate P0 local…"
  bash scripts/ci_guard.sh | tee "$REPORT_DIR/ci_guard.log"
  bash scripts/tests/test_backup_wrapper.sh | tee "$REPORT_DIR/backup-wrapper-test.log"
  bash scripts/tests/test_deploy_rollback.sh | tee "$REPORT_DIR/deploy-rollback-test.log"
  bash scripts/tests/test_selfhosted_runner_setup.sh | tee "$REPORT_DIR/runner-setup-test.log"
  ok "Release gate P0 local OK"
}

run_architecture() {
  require_cmd python3
  log "Inventário arquitetural local…"
  python3 -m unittest \
    scripts.tests.test_generate_architecture_inventory \
    scripts.tests.test_refine_architecture_inventory -v \
    | tee "$REPORT_DIR/architecture-test.log"
  local out="$REPORT_DIR/architecture-inventory"
  python3 scripts/generate_architecture_inventory.py --output "$out" --check
  python3 scripts/refine_architecture_inventory.py --output "$out" --check
  ok "Inventário arquitetural OK"
}

run_backend_fast() {
  ensure_python_deps
  local PY="$VENV_DIR/bin/python"
  export APP_ENV=development
  run_script_syntax
  log "Backend rápido: pytest sem testes DB-level…"
  ( cd backend && "$PY" -m pytest tests -q --ignore-glob='*dblevel*' --maxfail=10 ) \
    | tee "$REPORT_DIR/backend-fast.log"
  ok "Backend rápido OK"
}

run_backend() {
  ensure_python_deps
  local PY="$VENV_DIR/bin/python"
  start_pg
  run_script_syntax

  log "Compatibilidade dos modelos RAG…"
  ( cd backend && "$PY" -c "from app.services.embedding_service import validar_modelo_local; ok,msg=validar_modelo_local(); print(msg); raise SystemExit(0 if ok else 1)" )
  ( cd backend && "$PY" -c "from app.core.config import get_settings; from fastembed.rerank.cross_encoder import TextCrossEncoder; s=get_settings(); nomes={m['model'] for m in TextCrossEncoder.list_supported_models()}; assert s.RAG_RERANK_MODEL in nomes, s.RAG_RERANK_MODEL; print(s.RAG_RERANK_MODEL)" )

  log "Ruff bloqueante…"
  ( cd backend && "$PY" -m ruff check app --output-format=concise ) \
    | tee "$REPORT_DIR/ruff-report.txt"

  log "pip-audit bloqueante…"
  if ! "$VENV_DIR/bin/pip-audit" --version >/dev/null 2>&1; then
    [ "${CI_SKIP_PIP:-0}" != "1" ] || die "pip-audit ausente com CI_SKIP_PIP=1"
    "$VENV_DIR/bin/pip" install -q pip-audit
  fi
  ( cd backend && "$VENV_DIR/bin/pip-audit" -r requirements.txt --desc ) \
    | tee "$REPORT_DIR/pip-audit-report.txt"

  log "Alembic upgrade head em banco efêmero…"
  ( cd backend && "$PY" -m alembic upgrade head )

  log "Pytest completo + cobertura mínima 65%…"
  ( cd backend && "$PY" -m pytest tests -q --tb=short --maxfail=25 \
      --cov=app --cov-report=term-missing:skip-covered \
      --cov-report="xml:$REPORT_DIR/backend-coverage.xml" --cov-fail-under=65 ) \
    | tee "$REPORT_DIR/backend-test-summary.log"
  ok "Backend completo OK"
}

run_eval() {
  ensure_python_deps
  local PY="$VENV_DIR/bin/python"
  log "Gold sets offline…"
  ( cd backend && "$PY" -m app.eval.run_eval --smoke ) \
    | tee "$REPORT_DIR/gold-set-smoke.log"
  ( cd backend && "$PY" -m app.eval.agent_trajectory --min-tool 1.0 --max-violacoes-hitl 0 ) \
    | tee "$REPORT_DIR/agent-trajectory.log"
  ok "Evals offline OK"
}

run_frontend() {
  [ -d frontend ] || die "pasta frontend ausente"
  ensure_node_deps
  log "Prettier bloqueante…"
  ( cd frontend && npm run format:check ) | tee "$REPORT_DIR/prettier-report.txt"
  log "Vitest…"
  ( cd frontend && npm run test -- --reporter=dot ) | tee "$REPORT_DIR/frontend-test-summary.log"
  log "npm audit (high/critical)…"
  ( cd frontend && npm audit --audit-level=high ) | tee "$REPORT_DIR/npm-audit-report.txt"
  log "ESLint…"
  ( cd frontend && npm run lint:eslint ) | tee "$REPORT_DIR/eslint-report.txt"
  log "Typecheck + Vite build…"
  ( cd frontend && npm run build ) | tee "$REPORT_DIR/frontend-build-report.log"
  ok "Frontend completo OK"
}

run_continuity() {
  ensure_python_deps
  local PY="$VENV_DIR/bin/python"
  start_pg
  require_cmd psql
  require_cmd pg_dump
  export RESTORE_DRILL_ALLOW=1
  export RESTORE_DRILL_REPORT="$REPORT_DIR/restore-drill-report.json"
  log "Preparando schema para restore drill…"
  ( cd backend && "$PY" -m alembic upgrade head )
  log "Prova integral de backup cifrado + restauração…"
  "$PY" -m py_compile scripts/backup/restore_drill.py
  ( cd backend && PYTHONPATH=. "$PY" ../scripts/backup/restore_drill.py )
  [ -s "$RESTORE_DRILL_REPORT" ] || die "restore drill não gerou relatório"
  cat "$RESTORE_DRILL_REPORT"
  ok "Continuidade/restore drill OK"
}

run_browser() {
  ensure_node_deps
  log "Browser gate: ESLint + build…"
  ( cd frontend && npm run lint:eslint )
  ( cd frontend && npm run build )
  if [ "${EJC_SKIP_BROWSER_INSTALL:-0}" != "1" ]; then
    log "Instalando Playwright 1.56.1 sem alterar package-lock…"
    ( cd frontend && npm install --no-save --package-lock=false playwright@1.56.1 )
    ( cd frontend && npx playwright install --with-deps chromium )
  fi
  export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-0}"
  export SCREENSHOT_DIR="$REPORT_DIR/browser/login"
  export PREMIUM_SCREENSHOT_DIR="$REPORT_DIR/browser/premium-dashboard"
  mkdir -p "$SCREENSHOT_DIR" "$PREMIUM_SCREENSHOT_DIR"
  log "Smoke responsivo do login…"
  ( cd frontend && npm run test:responsive )
  log "Smoke autenticado do dashboard premium…"
  ( cd frontend && npm run test:premium-responsive )
  ok "Browser responsivo OK"
}

log "EJC CI local — modo: $MODE"
log "Relatórios: $REPORT_DIR"
case "$MODE" in
  fast)         run_governance; run_release; run_backend_fast ;;
  backend)      run_backend ;;
  frontend)     run_frontend ;;
  eval)         run_eval ;;
  release)      run_release ;;
  governance)   run_governance ;;
  architecture) run_architecture ;;
  continuity)   run_continuity ;;
  browser)      run_browser ;;
  full)         run_governance; run_release; run_architecture; run_backend; run_eval; run_frontend ;;
  parity)       run_governance; run_release; run_architecture; run_backend; run_eval; run_frontend; run_continuity; run_browser ;;
  *) die "modo inválido: $MODE" ;;
esac
ok "CI local concluído com sucesso — head apto à confirmação remota quando o GitHub estiver disponível."
