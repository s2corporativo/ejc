#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT/scripts/setup-selfhosted-runner.sh"

fail() {
  echo "[runner-setup-test] FALHA: $*" >&2
  exit 1
}

line_of() {
  local pattern="$1"
  grep -nE "$pattern" "$SCRIPT" | head -1 | cut -d: -f1
}

bash -n "$SCRIPT"

# Dependências usadas pelo deploy precisam ser instaladas pelo bootstrap.
grep -Eq 'git rsync|rsync.*postgresql-client' "$SCRIPT" || \
  fail "rsync não é instalado pelo bootstrap"

# A reconfiguração não pode ocorrer enquanto o serviço antigo está ativo.
grep -q './svc.sh stop' "$SCRIPT" || fail "serviço existente não é parado"
grep -q './svc.sh uninstall' "$SCRIPT" || fail "serviço existente não é desinstalado"
grep -q 'remove_local_registration' "$SCRIPT" || \
  fail "não há fallback local para registro inconsistente"

stop_call="$(line_of '^stop_and_uninstall_service$')"
old_registration="$(line_of '^if \[ -f "\$RUNNER_HOME/\.runner" \]; then$')"
new_registration="$(line_of '^sudo -u "\$RUNNER_USER" bash -c "cd.*config\.sh')"
service_install="$(line_of '^\(cd "\$RUNNER_HOME" && \./svc\.sh install')"
health_check="$(line_of '^wait_for_active_service$')"

[ -n "$stop_call" ] || fail "chamada de parada não encontrada"
[ -n "$old_registration" ] || fail "tratamento do registro anterior não encontrado"
[ -n "$new_registration" ] || fail "novo registro não encontrado"
[ -n "$service_install" ] || fail "instalação do serviço não encontrada"
[ -n "$health_check" ] || fail "prova de saúde não encontrada"

[ "$stop_call" -lt "$old_registration" ] || \
  fail "registro anterior é manipulado antes de parar o serviço"
[ "$old_registration" -lt "$new_registration" ] || \
  fail "novo registro ocorre antes de tratar o registro anterior"
[ "$new_registration" -lt "$service_install" ] || \
  fail "serviço é instalado antes do novo registro"
[ "$service_install" -lt "$health_check" ] || \
  fail "saúde é verificada antes da instalação do serviço"

# Não basta executar `svc.sh start`: o systemd deve ficar realmente ativo.
grep -q 'systemctl is-active --quiet' "$SCRIPT" || \
  fail "atividade real do serviço não é validada"
grep -q 'journalctl -u.*-n 80' "$SCRIPT" || \
  fail "falha de inicialização não publica diagnóstico local"
grep -q 'RUNNER_START_ATTEMPTS' "$SCRIPT" || \
  fail "não há limite configurável de tentativas"

# Evita regressão para mensagem de sucesso sem prova de saúde.
if grep -q "Runner .* online" "$SCRIPT"; then
  fail "script voltou a afirmar online sem prova remota"
fi

echo "[runner-setup-test] OK — recuperação idempotente, dependências e prova de saúde preservadas."
