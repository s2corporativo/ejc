#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# CI LOCAL do EJC — roda a MESMA validação do antigo GitHub Actions, de graça,
# no seu VPS ou na sua máquina. NÃO depende do GitHub Actions (custo zero).
#
# Reproduz o ci.yml:
#   Backend  — Postgres+pgvector → alembic upgrade head → pytest (RUN_DB_TESTS=1)
#   Frontend — npm ci → tsc (typecheck) → vite build
#
# USO:
#   scripts/ci-local.sh                # tudo (backend + frontend)
#   scripts/ci-local.sh backend        # só backend (com banco)
#   scripts/ci-local.sh frontend       # só frontend
#   scripts/ci-local.sh fast           # backend SEM banco (rápido, p/ pre-push)
#
# Postgres: usa Docker (pgvector/pgvector:pg16) se houver; senão sobe um cluster
# LOCAL efêmero com initdb (requer postgresql-16 + postgresql-16-pgvector).
# Sai com código != 0 se qualquer etapa falhar (serve de gate real).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-full}"          # full | backend | frontend | fast
PG_PORT="${PG_PORT:-5455}"
PG_CONTAINER="${PG_CONTAINER:-ejc_ci_pg}"
PGVECTOR_IMAGE="${PGVECTOR_IMAGE:-pgvector/pgvector:pg16}"
VENV_DIR="${VENV_DIR:-$ROOT/.ci-venv}"
PGDATA="${PGDATA:-$ROOT/.ci-pgdata}"
DBU=ejc_user; DBP=ejc_pass; DBN=ejc_db

log()  { printf '\n\033[1;36m[ci-local]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }

PG_MODE=""       # docker | local
_cleanup() {
  set +e
  if [ "$PG_MODE" = "docker" ]; then docker rm -f "$PG_CONTAINER" >/dev/null 2>&1; fi
  if [ "$PG_MODE" = "local" ] && [ -d "$PGDATA" ]; then
    "$PGBIN/pg_ctl" -D "$PGDATA" stop -m fast >/dev/null 2>&1
    rm -rf "$PGDATA"
  fi
}
trap _cleanup EXIT

run_local_first_selftest() {
  [ -f scripts/ejc-local-first.sh ] || return 0
  [ -f scripts/test_ejc_local_first.sh ] || die "scripts/test_ejc_local_first.sh ausente"
  log "Validando mecanismo local-first…"
  bash -n scripts/ejc-local-first.sh scripts/test_ejc_local_first.sh
  bash scripts/test_ejc_local_first.sh
  ok "Local-first OK"
}

# ── Postgres com pgvector ────────────────────────────────────────────────────
start_pg() {
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    PG_MODE=docker
    log "Subindo Postgres+pgvector via Docker ($PGVECTOR_IMAGE)…"
    docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
    docker run -d --name "$PG_CONTAINER" \
      -e POSTGRES_USER=$DBU -e POSTGRES_PASSWORD=$DBP -e POSTGRES_DB=$DBN \
      -p "$PG_PORT:5432" "$PGVECTOR_IMAGE" >/dev/null
    for _ in $(seq 1 30); do
      docker exec "$PG_CONTAINER" pg_isready -U $DBU -d $DBN >/dev/null 2>&1 && break; sleep 1
    done
    PSQL_ENV=(env PGPASSWORD=$DBP)
  else
    PG_MODE=local
    PGBIN="$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1 || true)"
    [ -n "${PGBIN:-}" ] || die "Sem Docker e sem postgresql local. Instale docker OU postgresql-16 + postgresql-16-pgvector."
    log "Sem Docker — subindo cluster Postgres LOCAL efêmero ($PGBIN)…"
    rm -rf "$PGDATA"; mkdir -p "$PGDATA"
    if id postgres >/dev/null 2>&1 && [ "$(id -u)" = "0" ]; then
      chown -R postgres "$PGDATA"; SU="su postgres -c"
    else SU="bash -c"; fi
    $SU "$PGBIN/initdb -D $PGDATA -U $DBU --auth=trust" >/dev/null
    $SU "$PGBIN/pg_ctl -D $PGDATA -o '-p $PG_PORT -c listen_addresses=127.0.0.1' -l $PGDATA/pg.log start" >/dev/null
    for _ in $(seq 1 30); do pg_isready -h 127.0.0.1 -p "$PG_PORT" -U $DBU >/dev/null 2>&1 && break; sleep 1; done
    "$PGBIN/createdb" -h 127.0.0.1 -p "$PG_PORT" -U $DBU $DBN >/dev/null 2>&1 || true
    PSQL_ENV=(env)
  fi
  # extensões (mesmas do ci.yml)
  "${PSQL_ENV[@]}" psql -h 127.0.0.1 -p "$PG_PORT" -U $DBU -d $DBN -qc \
    "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm; CREATE EXTENSION IF NOT EXISTS pgcrypto;" >/dev/null
  ok "Postgres pronto em 127.0.0.1:$PG_PORT (modo: $PG_MODE)"
}

# ── Backend ──────────────────────────────────────────────────────────────────
run_backend() {
  local with_db="$1"   # 1 = sobe banco + migrations + RUN_DB_TESTS; 0 = rápido
  command -v python3 >/dev/null || die "python3 ausente"
  if [ ! -d "$VENV_DIR" ]; then
    log "Criando venv em $VENV_DIR…"; python3 -m venv "$VENV_DIR"
  fi
  if [ "${CI_SKIP_PIP:-0}" = "1" ]; then
    log "CI_SKIP_PIP=1 — pulando instalação de dependências (já presentes)."
  else
    log "Instalando dependências do backend…"
    "$VENV_DIR/bin/pip" install -q --upgrade pip
    "$VENV_DIR/bin/pip" install -q -r backend/requirements.txt
  fi
  local PY="$VENV_DIR/bin/python"

  export APP_ENV=development
  if [ "$with_db" = "1" ]; then
    start_pg
    export DATABASE_URL="postgresql+asyncpg://$DBU@127.0.0.1:$PG_PORT/$DBN"
    export DATABASE_URL_SYNC="postgresql://$DBU@127.0.0.1:$PG_PORT/$DBN"
    export SCHEMA_CHECK_DATABASE_URL="postgresql://$DBU@127.0.0.1:$PG_PORT/$DBN"
    export RUN_DB_TESTS=1
    log "alembic upgrade head…"; ( cd backend && "$PY" -m alembic upgrade head )
    log "pytest (suíte completa + banco)…"; ( cd backend && "$PY" -m pytest tests -q )
  else
    log "pytest (rápido — sem banco)…"; ( cd backend && "$PY" -m pytest tests -q --ignore-glob='*dblevel*' )
  fi
  ok "Backend OK"
}

# ── Frontend ─────────────────────────────────────────────────────────────────
run_frontend() {
  [ -d frontend ] || { log "sem pasta frontend — pulando"; return 0; }
  command -v npm >/dev/null || die "npm ausente (instale Node LTS)"
  log "Frontend: npm ci…"; ( cd frontend && npm ci --no-audit --no-fund )
  # Typecheck + build (mesmo do ci.yml). Usa os scripts do package.json quando existem.
  if ( cd frontend && npm run -s typecheck >/dev/null 2>&1 ); then :; else
    ( cd frontend && npx --no-install tsc --noEmit )
  fi
  log "Frontend: build (vite)…"; ( cd frontend && npm run -s build )
  ok "Frontend OK"
}

log "EJC CI local — modo: $MODE"
run_local_first_selftest
case "$MODE" in
  full)     run_backend 1; run_frontend ;;
  backend)  run_backend 1 ;;
  fast)     run_backend 0 ;;
  frontend) run_frontend ;;
  *) die "modo inválido: $MODE (use: full | backend | frontend | fast)" ;;
esac
ok "CI local concluído com sucesso — pode sincronizar/publicar pela política local-first."
