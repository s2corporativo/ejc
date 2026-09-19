#!/usr/bin/env bash
# CI LOCAL do EJC — paridade dos gates de CI fora do GitHub Actions.
# Usa somente banco efêmero; nunca aponta para produção.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-full}" # full|required|backend|eval|frontend|p0|status|architecture|continuity|ui-extra|fast
PG_PORT_OVERRIDE="${PG_PORT:-}"
PG_PORT="$PG_PORT_OVERRIDE"
PG_CONTAINER="${PG_CONTAINER:-ejc_ci_pg_${$}}"
PGVECTOR_IMAGE="${PGVECTOR_IMAGE:-pgvector/pgvector:pg16@sha256:b02ab52c7c0e98df0c41ea8d7843d5b3a6b7e6f96e75e8dc3e9fae69dcf4c1c2}"
STATE_ROOT="${EJC_CI_STATE_ROOT:-${XDG_CACHE_HOME:-${HOME:-/tmp}/.cache}/ejc-ci-local}"
VENV_DIR_OVERRIDE="${VENV_DIR:-}"
VENV_DIR=""
PIP_AUDIT_VERSION="${PIP_AUDIT_VERSION:-2.10.0}"
# Guarda o PYTHON do tool-venv, não o console script: `python -m venv` grava
# shebang ABSOLUTO, e o venv é construído em $build_dir e só depois movido
# para $tool_dir — o shebang de bin/pip-audit continua apontando para o
# caminho de build, que já não existe ("cannot execute: required file not
# found"). Invocar por módulo é imune ao rename, e é o que o venv principal
# já fazia ("$PY" -m ruff / -m pytest).
PIP_AUDIT_BIN=""
PGDATA="${PGDATA:-$STATE_ROOT/pgdata-${$}}"
REPORT_ROOT="${EJC_CI_REPORT_ROOT:-$STATE_ROOT/reports}"
REPORT_DIR="${EJC_CI_REPORT_DIR:-$REPORT_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-${$}}"
DBU="${EJC_CI_DB_USER:-ejc_user}"
DBP="${EJC_CI_DB_PASSWORD:-ejc_pass}"
DBN="${EJC_CI_DB_NAME:-ejc_db}"
PYTHON_BIN="${PYTHON_BIN:-}"
NODE_MAJOR_REQUIRED="${NODE_MAJOR_REQUIRED:-22}"
REPORT_RETENTION_DAYS="${EJC_CI_REPORT_RETENTION_DAYS:-14}"

log() { printf '\n\033[1;36m[ci-local]\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }

canon() {
  if command -v realpath >/dev/null 2>&1; then realpath -m "$1"; else printf '%s\n' "$1"; fi
}

assert_state_root() {
  local resolved root_resolved home_resolved
  resolved="$(canon "$STATE_ROOT")"
  root_resolved="$(canon "$ROOT")"
  home_resolved="$(canon "${HOME:-/__no_home__}")"
  case "$resolved" in
    /|/opt/ejc|/opt/ejc/*|"$root_resolved"|"$root_resolved"/*|"$home_resolved")
      die "STATE_ROOT inseguro: $resolved"
      ;;
  esac
}

assert_state_child() {
  local path="$1" label="$2" resolved state_resolved root_resolved
  resolved="$(canon "$path")"
  state_resolved="$(canon "$STATE_ROOT")"
  root_resolved="$(canon "$ROOT")"
  [[ "$resolved" == "$state_resolved/"* ]] || die "$label deve ficar sob STATE_ROOT: $resolved"
  case "$resolved" in
    /opt/ejc|/opt/ejc/*|"$root_resolved"|"$root_resolved"/*) die "$label aponta para caminho protegido: $resolved" ;;
  esac
}

safe_remove_tree() {
  local path="${1:-}" croot cstate
  [ -n "$path" ] || return 0
  croot="$(canon "$ROOT")"
  cstate="$(canon "$STATE_ROOT")"
  path="$(canon "$path")"
  case "$path" in
    /|"$croot"|"${HOME:-/__no_home__}") die "limpeza recusada para caminho protegido: $path" ;;
  esac
  [[ "$path" == "$cstate/"* ]] || die "limpeza recusada fora do STATE_ROOT: $path"
  [ -d "$path" ] || return 0
  find "$path" -depth -mindepth 1 -delete
  rmdir "$path" 2>/dev/null || true
}

case "$(canon "$ROOT")" in
  /opt/ejc|/opt/ejc/*) die "CI local recusado em /opt/ejc (produção). Use worktree isolado em máquina de desenvolvimento/homologação." ;;
esac
if [ "${APP_ENV:-}" = "production" ] || [ "${EJC_ENV:-}" = "production" ]; then
  die "CI local recusado com ambiente de produção ativo."
fi
if [ -e /opt/ejc/.deployed_sha ] || [ -e /opt/ejc/.env ]; then
  die "CI local recusado: host contém marcadores da instalação produtiva /opt/ejc."
fi
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -Eq '^(ejc_backend|ejc_worker|ejc_db|ejc_frontend|ejc_redis)$'; then
    die "CI local recusado: containers canônicos do EJC estão ativos neste host."
  fi
fi
if [ "$(id -u)" -eq 0 ] && [ "${EJC_ALLOW_ROOT_DIAGNOSTIC:-0}" != "1" ]; then
  die "CI local promovível não roda como root. EJC_ALLOW_ROOT_DIAGNOSTIC=1 serve apenas para diagnóstico não-promovível."
fi
[[ "$REPORT_RETENTION_DAYS" =~ ^[1-9][0-9]*$ ]] || die "EJC_CI_REPORT_RETENTION_DAYS deve ser inteiro >=1"

assert_state_root
assert_state_child "$PGDATA" "PGDATA"
assert_state_child "$REPORT_ROOT" "REPORT_ROOT"
assert_state_child "$REPORT_DIR" "REPORT_DIR"
[ -z "$VENV_DIR_OVERRIDE" ] || assert_state_child "$VENV_DIR_OVERRIDE" "VENV_DIR"
mkdir -p "$STATE_ROOT" "$REPORT_ROOT" "$REPORT_DIR"
[ ! -L "$STATE_ROOT" ] || die "STATE_ROOT não pode ser symlink"
chmod 700 "$STATE_ROOT" "$REPORT_ROOT" "$REPORT_DIR" 2>/dev/null || true

while IFS= read -r -d '' old_report; do
  safe_remove_tree "$old_report"
done < <(find "$REPORT_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime "+$REPORT_RETENTION_DAYS" -print0 2>/dev/null || true)

PG_MODE=""
PGBIN=""

stop_pg() {
  if [ "$PG_MODE" = "docker" ]; then
    docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || die "não foi possível encerrar o PostgreSQL Docker efêmero"
  elif [ "$PG_MODE" = "local" ] && [ -n "$PGBIN" ] && [ -d "$PGDATA" ]; then
    "$PGBIN/pg_ctl" -D "$PGDATA" stop -m fast >/dev/null 2>&1 || die "não foi possível encerrar o PostgreSQL local efêmero"
  fi
  if [ -d "$PGDATA" ]; then safe_remove_tree "$PGDATA"; fi
  PG_MODE=""
  PGBIN=""
  [ -n "$PG_PORT_OVERRIDE" ] || PG_PORT=""
}

_cleanup() {
  set +e
  if [ "$PG_MODE" = "docker" ]; then docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true; fi
  if [ "$PG_MODE" = "local" ] && [ -n "$PGBIN" ] && [ -d "$PGDATA" ]; then "$PGBIN/pg_ctl" -D "$PGDATA" stop -m fast >/dev/null 2>&1 || true; fi
  if [ -d "$PGDATA" ]; then
    local cdata cstate
    cdata="$(canon "$PGDATA")"; cstate="$(canon "$STATE_ROOT")"
    if [[ "$cdata" == "$cstate/"* ]]; then
      find "$PGDATA" -depth -mindepth 1 -delete >/dev/null 2>&1 || true
      rmdir "$PGDATA" >/dev/null 2>&1 || true
    fi
  fi
}
trap _cleanup EXIT

choose_python() {
  if [ -n "$PYTHON_BIN" ]; then
    command -v "$PYTHON_BIN" >/dev/null || die "PYTHON_BIN=$PYTHON_BIN não encontrado"
  elif command -v python3.11 >/dev/null 2>&1; then PYTHON_BIN=python3.11
  elif command -v python3 >/dev/null 2>&1; then PYTHON_BIN=python3
  else die "python3 ausente"; fi
  local version
  version="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if [ "$version" != "3.11" ] && [ "${EJC_ALLOW_PYTHON_MISMATCH:-0}" != "1" ]; then
    die "Python $version detectado; o CI canônico usa Python 3.11. Defina EJC_ALLOW_PYTHON_MISMATCH=1 apenas para diagnóstico não-promovível."
  fi
}

python_runtime_key() {
  "$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}_{sys.version_info.minor}_{sys.version_info.micro}")'
}

resolve_venv_dir() {
  [ -n "$VENV_DIR" ] && return 0
  if [ -n "$VENV_DIR_OVERRIDE" ]; then VENV_DIR="$VENV_DIR_OVERRIDE"; return 0; fi
  [ -f backend/requirements.txt ] || die "backend/requirements.txt ausente"
  local req_hash py_key
  req_hash="$($PYTHON_BIN -c 'import hashlib,pathlib; print(hashlib.sha256(pathlib.Path("backend/requirements.txt").read_bytes()).hexdigest()[:16])')"
  py_key="$(python_runtime_key)"
  VENV_DIR="$STATE_ROOT/venv-py${py_key}-${req_hash}"
  assert_state_child "$VENV_DIR" "VENV_DIR"
}

ensure_venv() {
  choose_python; resolve_venv_dir
  local ready="$VENV_DIR/.ejc-ready" lock_file="$VENV_DIR.lock" build_dir="${VENV_DIR}.build.$$.$RANDOM"
  assert_state_child "$lock_file" "VENV_LOCK"
  assert_state_child "$build_dir" "VENV_BUILD"
  mkdir -p "$(dirname "$VENV_DIR")"
  [ ! -L "$VENV_DIR" ] || die "VENV_DIR não pode ser symlink"

  exec {venv_lock_fd}>"$lock_file"
  flock "$venv_lock_fd"
  if [ -x "$VENV_DIR/bin/python" ] && [ -s "$ready" ]; then
    flock -u "$venv_lock_fd"
    eval "exec ${venv_lock_fd}>&-"
    log "Reutilizando venv imutável do mesmo runtime + requirements hash."
    return 0
  fi
  if [ "${CI_SKIP_PIP:-0}" = "1" ]; then
    flock -u "$venv_lock_fd"; eval "exec ${venv_lock_fd}>&-"
    die "CI_SKIP_PIP=1 solicitado, mas o venv hermético pronto não existe: $VENV_DIR"
  fi

  [ ! -e "$VENV_DIR" ] || safe_remove_tree "$VENV_DIR"
  safe_remove_tree "$build_dir"
  log "Construindo venv hermético imutável em $build_dir…"
  if ! (
    "$PYTHON_BIN" -m venv "$build_dir" \
      && "$build_dir/bin/python" -m pip install -q --upgrade pip \
      && "$build_dir/bin/python" -m pip install -q -r backend/requirements.txt \
      && "$build_dir/bin/python" -m pip check >/dev/null \
      && printf 'python=%s\nrequirements_sha256=%s\n' \
          "$("$build_dir/bin/python" -c 'import platform; print(platform.python_version())')" \
          "$(sha256sum backend/requirements.txt | awk '{print $1}')" > "$build_dir/.ejc-ready"
  ); then
    safe_remove_tree "$build_dir"
    flock -u "$venv_lock_fd"; eval "exec ${venv_lock_fd}>&-"
    die "falha ao construir venv hermético"
  fi
  chmod 600 "$build_dir/.ejc-ready" 2>/dev/null || true
  mv "$build_dir" "$VENV_DIR"
  flock -u "$venv_lock_fd"
  eval "exec ${venv_lock_fd}>&-"
  ok "Venv imutável promovido atomicamente: $VENV_DIR"
}

ensure_pip_audit() {
  choose_python
  local py_key tool_dir ready lock_file build_dir
  py_key="$(python_runtime_key)"
  tool_dir="$STATE_ROOT/tools/pip-audit-${PIP_AUDIT_VERSION}-py${py_key}"
  ready="$tool_dir/.ejc-ready"
  lock_file="$tool_dir.lock"
  build_dir="${tool_dir}.build.$$.$RANDOM"
  assert_state_child "$tool_dir" "PIP_AUDIT_VENV"
  assert_state_child "$lock_file" "PIP_AUDIT_LOCK"
  assert_state_child "$build_dir" "PIP_AUDIT_BUILD"
  mkdir -p "$STATE_ROOT/tools"
  [ ! -L "$tool_dir" ] || die "tool venv do pip-audit não pode ser symlink"

  exec {tool_lock_fd}>"$lock_file"
  flock "$tool_lock_fd"
  if [ ! -x "$tool_dir/bin/python" ] || [ ! -s "$ready" ]; then
    [ ! -e "$tool_dir" ] || safe_remove_tree "$tool_dir"
    safe_remove_tree "$build_dir"
    log "Construindo tool-venv pip-audit==$PIP_AUDIT_VERSION…"
    if ! (
      "$PYTHON_BIN" -m venv "$build_dir" \
        && "$build_dir/bin/python" -m pip install -q --upgrade pip \
        && "$build_dir/bin/python" -m pip install -q "pip-audit==$PIP_AUDIT_VERSION" \
        && "$build_dir/bin/python" -m pip check >/dev/null \
        && "$build_dir/bin/python" -m pip_audit --version > "$build_dir/.ejc-ready"
    ); then
      safe_remove_tree "$build_dir"
      flock -u "$tool_lock_fd"; eval "exec ${tool_lock_fd}>&-"
      die "falha ao construir tool-venv do pip-audit"
    fi
    chmod 600 "$build_dir/.ejc-ready" 2>/dev/null || true
    mv "$build_dir" "$tool_dir"
  fi
  PIP_AUDIT_BIN="$tool_dir/bin/python"
  flock -u "$tool_lock_fd"
  eval "exec ${tool_lock_fd}>&-"
}

check_node() {
  command -v npm >/dev/null 2>&1 || die "npm ausente"; command -v node >/dev/null 2>&1 || die "node ausente"
  local major; major="$(node -p 'process.versions.node.split(".")[0]')"
  [ "$major" = "$NODE_MAJOR_REQUIRED" ] || die "Node $(node --version) detectado; esperado major $NODE_MAJOR_REQUIRED."
}

pick_pg_port() {
  if [ -n "$PG_PORT" ]; then return 0; fi
  command -v python3 >/dev/null 2>&1 || die "python3 necessário para escolher porta efêmera"
  PG_PORT="$(python3 - <<'PY'
import socket
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind(("127.0.0.1", 0))
    print(s.getsockname()[1])
PY
)"
  [ -n "$PG_PORT" ] || die "não foi possível selecionar porta PostgreSQL efêmera"
}

start_pg() {
  [ -z "$PG_MODE" ] || return 0
  command -v psql >/dev/null 2>&1 || die "cliente psql ausente"
  pick_pg_port
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    PG_MODE=docker
    case "$PGVECTOR_IMAGE" in
      *@sha256:*) ;;
      *) die "PGVECTOR_IMAGE deve usar referência fixada com @sha256:<digest> para evidência promovível; recebido: $PGVECTOR_IMAGE" ;;
    esac
    log "Subindo PostgreSQL 16 + pgvector efêmero via Docker em 127.0.0.1:$PG_PORT…"
    docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
    docker run -d --name "$PG_CONTAINER" -e POSTGRES_USER="$DBU" -e POSTGRES_PASSWORD="$DBP" -e POSTGRES_DB="$DBN" -p "127.0.0.1:$PG_PORT:5432" "$PGVECTOR_IMAGE" >/dev/null
    for _ in $(seq 1 45); do docker exec "$PG_CONTAINER" pg_isready -U "$DBU" -d "$DBN" >/dev/null 2>&1 && break; sleep 1; done
    docker exec "$PG_CONTAINER" pg_isready -U "$DBU" -d "$DBN" >/dev/null 2>&1 || die "PostgreSQL efêmero não ficou pronto"
    local pg_version_num pg_docker_major
    pg_version_num="$(PGPASSWORD="$DBP" psql -h 127.0.0.1 -p "$PG_PORT" -U "$DBU" -d "$DBN" -Atqc 'SHOW server_version_num;' 2>/dev/null)" \
      || die "não foi possível validar a versão real do PostgreSQL Docker efêmero"
    [[ "$pg_version_num" =~ ^[0-9]+$ ]] || die "server_version_num inválido no PostgreSQL Docker: $pg_version_num"
    pg_docker_major="$((pg_version_num / 10000))"
    [ "$pg_docker_major" = "16" ] || die "PostgreSQL Docker major $pg_docker_major detectado; o CI canônico exige 16."
  else
    PG_MODE=local
    PGBIN="$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1 || true)"
    [ -n "$PGBIN" ] || die "Sem Docker e sem PostgreSQL local com pgvector."
    local pg_major
    pg_major="$("$PGBIN/postgres" --version | sed -n 's/.* \([0-9][0-9]*\)\..*/\1/p')"
    if [ "$pg_major" != "16" ] && [ "${EJC_ALLOW_POSTGRES_MISMATCH:-0}" != "1" ]; then
      die "PostgreSQL local major $pg_major detectado; o CI canônico exige 16."
    fi
    log "Subindo cluster PostgreSQL local efêmero em 127.0.0.1:$PG_PORT…"
    safe_remove_tree "$PGDATA"; mkdir -p "$PGDATA"
    "$PGBIN/initdb" -D "$PGDATA" -U "$DBU" --auth-local=trust --auth-host=scram-sha-256 --pwfile=<(printf '%s\n' "$DBP") >/dev/null
    "$PGBIN/pg_ctl" -D "$PGDATA" -o "-p $PG_PORT -c listen_addresses=127.0.0.1" -l "$PGDATA/pg.log" start >/dev/null
    for _ in $(seq 1 45); do PGPASSWORD="$DBP" "$PGBIN/pg_isready" -h 127.0.0.1 -p "$PG_PORT" -U "$DBU" >/dev/null 2>&1 && break; sleep 1; done
    PGPASSWORD="$DBP" "$PGBIN/createdb" -h 127.0.0.1 -p "$PG_PORT" -U "$DBU" "$DBN" >/dev/null 2>&1 || true
  fi
  PGPASSWORD="$DBP" psql -h 127.0.0.1 -p "$PG_PORT" -U "$DBU" -d "$DBN" -v ON_ERROR_STOP=1 \
    -c "CREATE EXTENSION IF NOT EXISTS vector;" -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" >/dev/null
  export APP_ENV=development
  export DATABASE_URL="postgresql+asyncpg://$DBU:$DBP@127.0.0.1:$PG_PORT/$DBN"
  export DATABASE_URL_SYNC="postgresql://$DBU:$DBP@127.0.0.1:$PG_PORT/$DBN"
  export SCHEMA_CHECK_DATABASE_URL="$DATABASE_URL_SYNC"
  export RUN_DB_TESTS=1
  ok "PostgreSQL efêmero pronto em 127.0.0.1:$PG_PORT"
}

run_backend() {
  ensure_venv; ensure_pip_audit; start_pg
  local PY="$VENV_DIR/bin/python"
  log "Sintaxe dos scripts críticos de produção…"; bash -n scripts/backup/ativar_backup.sh scripts/deploy_vps_safe.sh
  log "Compatibilidade dos modelos RAG (sem baixar pesos)…"
  (cd backend && "$PY" -c "from app.services.embedding_service import validar_modelo_local; ok,msg=validar_modelo_local(); print(msg); raise SystemExit(0 if ok else 1)")
  (cd backend && "$PY" -c "from app.core.config import get_settings; from fastembed.rerank.cross_encoder import TextCrossEncoder; s=get_settings(); nomes={m['model'] for m in TextCrossEncoder.list_supported_models()}; assert s.RAG_RERANK_MODEL in nomes, s.RAG_RERANK_MODEL; print(s.RAG_RERANK_MODEL)")
  log "Ruff…"; (cd backend && "$PY" -m ruff check app --output-format=concise) | tee "$REPORT_DIR/ruff.log"
  log "pip-audit $PIP_AUDIT_VERSION em tool-venv isolado…"
  (cd backend && "$PIP_AUDIT_BIN" -m pip_audit -r requirements.txt --desc) | tee "$REPORT_DIR/pip-audit.log"
  log "Alembic upgrade head…"; (cd backend && "$PY" -m alembic upgrade head)
  log "Pytest completo com banco + cobertura >=65%…"
  (cd backend && "$PY" -m pytest tests -q --tb=short --maxfail=25 --cov=app --cov-report=term-missing:skip-covered --cov-report="xml:$REPORT_DIR/backend-coverage.xml" --cov-fail-under=65) | tee "$REPORT_DIR/backend-tests.log"
  stop_pg; ok "Backend CI equivalente OK — banco efêmero encerrado"
}

run_eval() {
  ensure_venv; local PY="$VENV_DIR/bin/python"
  log "Eval smoke dos gold sets…"; (cd backend && "$PY" -m app.eval.run_eval --smoke) | tee "$REPORT_DIR/eval-gold.log"
  log "Eval de trajetória do agente…"; (cd backend && "$PY" -m app.eval.agent_trajectory --min-tool 1.0 --max-violacoes-hitl 0) | tee "$REPORT_DIR/eval-trajectory.log"
  ok "Eval offline OK"
}

run_frontend() {
  check_node
  log "Frontend: npm ci…"; (cd frontend && npm ci --no-audit --no-fund)
  log "Frontend: Prettier…"; (cd frontend && npm run format:check) | tee "$REPORT_DIR/prettier.log"
  log "Frontend: governança CSS…"; (cd frontend && npm run audit:css:verificar) | tee "$REPORT_DIR/css-audit.log"
  log "Frontend: Vitest…"; (cd frontend && npm run test -- --reporter=dot) | tee "$REPORT_DIR/vitest.log"
  log "Frontend: npm audit high…"; (cd frontend && npm audit --audit-level=high) | tee "$REPORT_DIR/npm-audit.log"
  log "Frontend: typecheck/build…"; (cd frontend && npm run build) | tee "$REPORT_DIR/frontend-build.log"
  ok "Frontend CI equivalente OK"
}

run_p0() {
  log "Release Gate P0…"; bash scripts/ci_guard.sh | tee "$REPORT_DIR/ci-guard.log"
  log "Backup wrapper cifrado…"; bash scripts/tests/test_backup_wrapper.sh | tee "$REPORT_DIR/backup-wrapper.log"
  log "Rollback de deploy…"; bash scripts/tests/test_deploy_rollback.sh | tee "$REPORT_DIR/deploy-rollback.log"
  log "Recuperação idempotente de runner…"; bash scripts/tests/test_selfhosted_runner_setup.sh | tee "$REPORT_DIR/runner-recovery.log"
  log "Bloco remoto de recuperação de runner…"; bash scripts/tests/test_recover_runner_recovery.sh | tee "$REPORT_DIR/runner-remote-block.log"
  log "Configuração de autenticação do Woodpecker…"; bash scripts/tests/test_woodpecker_compose.sh | tee "$REPORT_DIR/woodpecker-compose.log"
  log "Rotação de logs Docker…"; python scripts/tests/test_docker_log_rotation.py | tee "$REPORT_DIR/docker-log-rotation.log"
  log "Contrato de ativação RAG…"; bash scripts/tests/test_rag_activation.sh | tee "$REPORT_DIR/rag-activation.log"
  ok "P0 guard equivalente OK"
}

run_status() {
  log "Plano-Mestre: paridade do checklist-mestre…"; bash scripts/tests/test_status_check.sh | tee "$REPORT_DIR/status-check-tests.log"
  log "Plano-Mestre: validação de docs/PLANO_MESTRE_STATUS.md…"; bash scripts/status_check.sh --resumo | tee "$REPORT_DIR/status-check.log"
  ok "Plano-Mestre status OK"
}

run_architecture() {
  ensure_venv
  local PY="$VENV_DIR/bin/python" out
  out="$(mktemp -d "$STATE_ROOT/architecture-${$}.XXXXXX")"
  log "Architecture Inventory: testes…"; "$PY" -m unittest scripts.tests.test_generate_architecture_inventory scripts.tests.test_refine_architecture_inventory -v | tee "$REPORT_DIR/architecture-tests.log"
  log "Architecture Inventory: geração/refino…"; "$PY" scripts/generate_architecture_inventory.py --output "$out" --check; "$PY" scripts/refine_architecture_inventory.py --output "$out" --check
  safe_remove_tree "$out"; ok "Architecture Inventory OK"
}

run_continuity() {
  ensure_venv; start_pg
  command -v pg_dump >/dev/null 2>&1 || die "pg_dump ausente"
  local PY="$VENV_DIR/bin/python"
  export RESTORE_DRILL_ALLOW=1
  export RESTORE_DRILL_REPORT="${RESTORE_DRILL_REPORT:-$REPORT_DIR/restore-drill-report.json}"
  assert_state_child "$RESTORE_DRILL_REPORT" "RESTORE_DRILL_REPORT"
  log "Continuidade: preparando schema migrado em banco novo…"; (cd backend && "$PY" -m alembic upgrade head)
  log "Continuidade: prova integral backup/restore…"; "$PY" -m py_compile scripts/backup/restore_drill.py; (cd backend && PYTHONPATH=. "$PY" ../scripts/backup/restore_drill.py)
  [ -s "$RESTORE_DRILL_REPORT" ] || die "restore drill não produziu relatório"
  stop_pg; ok "Continuidade backup/restore OK — banco efêmero independente encerrado"
}

run_ui_extra() {
  check_node
  [ -d frontend/node_modules ] || (cd frontend && npm ci --no-audit --no-fund)
  log "Frontend extra: ESLint…"; (cd frontend && npm run lint:eslint) | tee "$REPORT_DIR/eslint.log"
  log "Frontend extra: build…"; (cd frontend && npm run build) | tee "$REPORT_DIR/ui-build.log"
  log "Frontend extra: Playwright/Chromium sem instalação privilegiada de pacotes do SO…"
  (cd frontend && npm install --no-save --package-lock=false playwright@1.56.1)
  (cd frontend && npx playwright install chromium)
  mkdir -p "$REPORT_DIR/browser/login" "$REPORT_DIR/browser/premium-dashboard"
  (cd frontend && SCREENSHOT_DIR="$REPORT_DIR/browser/login" npm run test:responsive)
  (cd frontend && PREMIUM_SCREENSHOT_DIR="$REPORT_DIR/browser/premium-dashboard" npm run test:premium-responsive)
  ok "Frontend browser responsivo OK"
}

run_fast() {
  ensure_venv; local PY="$VENV_DIR/bin/python"
  (cd backend && "$PY" -m ruff check app --output-format=concise)
  (cd backend && "$PY" -m pytest tests -q --ignore-glob='*dblevel*')
  ok "Fast gate OK"
}

log "EJC CI local — modo: $MODE"
log "Evidências locais: $REPORT_DIR"
case "$MODE" in
  backend) run_backend ;;
  eval) run_eval ;;
  frontend) run_frontend ;;
  p0) run_p0 ;;
  status) run_status ;;
  architecture) run_architecture ;;
  continuity) run_continuity ;;
  ui-extra) run_ui_extra ;;
  fast) run_fast ;;
  required) run_backend; run_eval; run_frontend; run_p0; run_status ;;
  full) run_backend; run_eval; run_frontend; run_p0; run_status; run_architecture; run_continuity; run_ui_extra ;;
  *) die "modo inválido: $MODE" ;;
esac
ok "CI local concluído com sucesso."