#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT}/artifacts/auditoria"
mkdir -p "${LOG_DIR}"
LOG="${LOG_DIR}/validacao_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "${LOG}") 2>&1

PASS=0
FAIL=0
SKIP=0

run() {
  local nome="$1"; shift
  echo
  echo "===== ${nome} ====="
  if "$@"; then
    PASS=$((PASS + 1))
    echo "[OK] ${nome}"
  else
    FAIL=$((FAIL + 1))
    echo "[FALHA] ${nome}"
  fi
}

skip() {
  local nome="$1" motivo="$2"
  SKIP=$((SKIP + 1))
  echo "[PULADO] ${nome}: ${motivo}"
}

echo "EJC — validação consolidada"
echo "Branch: $(git -C "${ROOT}" branch --show-current 2>/dev/null || true)"
echo "Commit: $(git -C "${ROOT}" rev-parse HEAD 2>/dev/null || true)"
echo "Início: $(date -Is)"

if command -v python3 >/dev/null 2>&1; then
  run "Sintaxe Python" bash -lc "cd '${ROOT}/backend' && python3 -m compileall -q app tests"
else
  skip "Sintaxe Python" "python3 não instalado"
fi

if command -v ruff >/dev/null 2>&1; then
  run "Ruff" bash -lc "cd '${ROOT}/backend' && ruff check app tests"
elif [[ -x "${ROOT}/backend/.venv/bin/ruff" ]]; then
  run "Ruff" bash -lc "cd '${ROOT}/backend' && .venv/bin/ruff check app tests"
else
  skip "Ruff" "ruff não está disponível no PATH nem em backend/.venv"
fi

if command -v pytest >/dev/null 2>&1; then
  run "Testes estáticos Parte 10/12" bash -lc "cd '${ROOT}/backend' && pytest -q tests/test_parte10_conferencia_assinatura.py tests/test_parte12_filtros_e_metricas.py"
elif [[ -x "${ROOT}/backend/.venv/bin/pytest" ]]; then
  run "Testes estáticos Parte 10/12" bash -lc "cd '${ROOT}/backend' && .venv/bin/pytest -q tests/test_parte10_conferencia_assinatura.py tests/test_parte12_filtros_e_metricas.py"
else
  skip "Testes estáticos Parte 10/12" "pytest não está disponível"
fi

if [[ "${RUN_DB_TESTS:-0}" == "1" ]]; then
  if command -v pytest >/dev/null 2>&1; then
    run "Testes com PostgreSQL" bash -lc "cd '${ROOT}/backend' && RUN_DB_TESTS=1 pytest -q tests/test_integridade_contadores_dblevel.py"
  elif [[ -x "${ROOT}/backend/.venv/bin/pytest" ]]; then
    run "Testes com PostgreSQL" bash -lc "cd '${ROOT}/backend' && RUN_DB_TESTS=1 .venv/bin/pytest -q tests/test_integridade_contadores_dblevel.py"
  else
    skip "Testes com PostgreSQL" "pytest não está disponível"
  fi
else
  skip "Testes com PostgreSQL" "defina RUN_DB_TESTS=1 e DATABASE_URL de um banco de teste"
fi

if command -v npm >/dev/null 2>&1; then
  run "Instalação frontend reproduzível" bash -lc "cd '${ROOT}/frontend' && npm ci"
  run "TypeScript" bash -lc "cd '${ROOT}/frontend' && npm run lint"
  run "ESLint" bash -lc "cd '${ROOT}/frontend' && npm run lint:eslint"
  run "Vitest" bash -lc "cd '${ROOT}/frontend' && npm test"
  run "Build frontend" bash -lc "cd '${ROOT}/frontend' && npm run build"
else
  skip "Frontend" "npm não instalado"
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  run "Validação docker-compose" bash -lc "cd '${ROOT}' && docker compose config -q"
else
  skip "Validação docker-compose" "Docker Compose não disponível"
fi

echo
echo "===== RESULTADO ====="
echo "Aprovados: ${PASS}"
echo "Falhas:    ${FAIL}"
echo "Pulados:   ${SKIP}"
echo "Log:       ${LOG}"

if [[ ${FAIL} -gt 0 ]]; then
  exit 1
fi
