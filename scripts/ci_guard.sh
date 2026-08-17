#!/usr/bin/env bash
set -euo pipefail

# EJC release guard
# Bloqueia regressões P0 antes de build/deploy:
# - marcadores de merge no código versionado;
# - arquivos .env/backup de segredo versionados;
# - arquivos temporários críticos que não devem entrar em release.

fail=0

echo "[EJC CI] Verificando marcadores de conflito de merge..."
if git grep -n -E '^(<<<<<<<{7,}|>>>>>>>{7,})' -- \
  ':!**/node_modules/**' \
  ':!**/.venv/**' \
  ':!**/site-packages/**' \
  ':!**/dist/**' \
  ':!frontend/dist/**' \
  ':!coverage/**' \
  ':!htmlcov/**'; then
  echo "::error::Marcadores de conflito encontrados. Resolva semanticamente antes do merge."
  fail=1
fi

echo "[EJC CI] Verificando arquivos de ambiente/segredos versionados..."
tracked_env_files="$(git ls-files | grep -E '(^|/)\.env($|\.)|\.env\.bak|vps-tools/\.env$' | grep -v -E '(^|/)\.env\.example$' || true)"
if [[ -n "${tracked_env_files}" ]]; then
  echo "::error::Arquivos de ambiente/segredo estão versionados. Remova da árvore e rotacione credenciais afetadas."
  printf '%s\n' "${tracked_env_files}"
  fail=1
fi

echo "[EJC CI] Verificando backups/resíduos críticos em release..."
tracked_release_residue="$(git ls-files | grep -E '(^_QUARENTENA/|^_dead_code/|^_deploy_e2e1/|\.bak$|\.old$|\.orig$|^graphify-out/)' || true)"
if [[ -n "${tracked_release_residue}" ]]; then
  echo "::warning::Resíduos de desenvolvimento encontrados na árvore. Saneie antes do release final."
  printf '%s\n' "${tracked_release_residue}"
fi

if [[ "${fail}" -ne 0 ]]; then
  echo "[EJC CI] Gate P0 falhou."
  exit 1
fi

echo "[EJC CI] Gate P0 aprovado."
