#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

fail() { echo "FAIL: $*" >&2; exit 1; }

legacy=(
  scripts/deploy.sh
  scripts/deploy-vps.sh
  scripts/atualizar-vps.sh
  scripts/vps_setup.sh
  scripts/legacy_script_guard.sh
)

for rel in "${legacy[@]}"; do
  [ ! -e "$ROOT/$rel" ] || fail "$rel voltou ao repositório; use o caminho canônico de deploy"
done

if grep -Fq './scripts/atualizar-vps.sh' "$ROOT/docs/DEPLOY-VPS.md"; then
  fail "docs/DEPLOY-VPS.md ainda referencia atualizar-vps.sh"
fi

grep -Fq 'scripts/deploy_manual.sh' "$ROOT/docs/DEPLOY-VPS.md" || fail "docs/DEPLOY-VPS.md perdeu o caminho manual canônico"
grep -Fq 'ejc-deploy-approved.sh' "$ROOT/docs/DEPLOY-VPS.md" || fail "docs/DEPLOY-VPS.md perdeu o gate de deploy aprovado"

echo "OK: scripts legados removidos e caminhos canônicos preservados"
