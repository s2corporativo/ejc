#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HELPER="$ROOT/scripts/legacy_script_guard.sh"
fail() { printf 'legacy guard test: %s\n' "$*" >&2; exit 1; }

for rel in scripts/deploy.sh scripts/deploy-vps.sh scripts/atualizar-vps.sh scripts/vps_setup.sh; do
  out="$(mktemp)"
  err="$(mktemp)"
  set +e
  env -u EJC_LEGACY_SCRIPT_OK bash "$ROOT/$rel" >"$out" 2>"$err"
  rc=$?
  set -e
  [ "$rc" -eq 64 ] || fail "$rel retornou rc=$rc sem opt-in; esperado 64"
  grep -Fq '[legacy-guard] BLOQUEADO:' "$err" || fail "$rel não emitiu bloqueio explícito"
  rm -f "$out" "$err"
done

optin="$(EJC_LEGACY_SCRIPT_OK=1 bash -c 'source "$1"; ejc_legacy_script_guard "fixture" "replacement"; printf OPTIN_OK' _ "$HELPER" 2>/dev/null)"
[ "$optin" = 'OPTIN_OK' ] || fail 'helper não libera opt-in explícito'

grep -Fq 'Woodpecker self-hosted' "$ROOT/README.md" || fail 'README ainda não declara o CI oficial'
if grep -Fq './scripts/atualizar-vps.sh' "$ROOT/docs/DEPLOY-VPS.md"; then
  fail 'runbook ativo ainda recomenda atualizar-vps.sh'
fi
printf 'legacy deploy guards: 4 scripts bloqueados antes de qualquer mutação; documentação ativa saneada.\n'
