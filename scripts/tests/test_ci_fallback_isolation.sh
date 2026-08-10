#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FALLBACK="$ROOT/scripts/ci-fallback.sh"
SETUP="$ROOT/scripts/setup-ci-fallback-runner.sh"
WORKFLOW="$ROOT/.github/workflows/ci-fallback-selfhosted.yml"

fail() {
  echo "[ci-fallback-test] FALHA: $*" >&2
  exit 1
}

bash -n "$FALLBACK"
bash -n "$SETUP"

if APP_ENV=production EJC_CI_GUARD_ONLY=1 bash "$FALLBACK" >/dev/null 2>&1; then
  fail "fallback aceitou APP_ENV=production"
fi

grep -q '/opt/ejc/.env' "$FALLBACK" || fail "fallback não bloqueia marcador .env de produção"
grep -q '/opt/ejc/.deployed_sha' "$FALLBACK" || fail "fallback não bloqueia marcador de deploy"
grep -q 'ejc_backend' "$FALLBACK" || fail "fallback não bloqueia container produtivo"
grep -q 'ejc_db' "$FALLBACK" || fail "fallback não bloqueia banco produtivo"

grep -q 'ejc-ci-isolado' "$SETUP" || fail "runner dedicado sem label de isolamento"
grep -q 'ejc-ci-isolado' "$WORKFLOW" || fail "workflow não exige label de isolamento"
grep -q 'head_repository.full_name' "$WORKFLOW" || fail "workflow não valida repositório de origem"
grep -q 'com_steps' "$WORKFLOW" || fail "workflow não distingue falha pré-step de falha real"

if grep -Eq 'NOPASSWD[[:space:]]*:[[:space:]]*ALL|NOPASSWD:ALL' "$SETUP"; then
  fail "bootstrap concedeu sudo administrativo irrestrito"
fi

# O token só pode ser aceito por ambiente/argumento e o registro automático
# precisa suportar token temporário obtido da API sem gravá-lo no repositório.
grep -q 'RUNNER_TOKEN' "$SETUP" || fail "bootstrap sem token temporário"
grep -q 'GH_TOKEN_LOCAL' "$SETUP" || fail "bootstrap sem opção de registro automático via GH_TOKEN"
grep -q 'registration-token' "$SETUP" || fail "bootstrap não solicita token temporário pela API"

# O fallback precisa cobrir, no mínimo, as mesmas famílias dos gates oficiais.
for marcador in \
  'scripts/ci_guard.sh' \
  'test_backup_wrapper.sh' \
  'test_deploy_rollback.sh' \
  'generate_architecture_inventory.py' \
  'alembic upgrade head' \
  'cov-fail-under=65' \
  'app.eval.run_eval --smoke' \
  'npm run format:check' \
  'npm run test -- --reporter=dot' \
  'npm audit --audit-level=high' \
  'npm run lint:eslint' \
  'npm run test:responsive' \
  'restore_drill.py'
do
  grep -q -- "$marcador" "$FALLBACK" || fail "gate ausente do fallback: $marcador"
done

echo "[ci-fallback-test] OK — isolamento, detecção pré-step e cobertura dos gates preservados."
