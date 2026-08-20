#!/usr/bin/env bash
set -euo pipefail

# EJC release guard
# Bloqueia regressões P0 antes de build/deploy:
# - marcadores de merge no código versionado;
# - arquivos .env/backup de segredo versionados;
# - arquivos temporários críticos que não devem entrar em release.

fail=0

echo "[EJC CI] Verificando marcadores de conflito de merge..."
# Marcadores padrão do Git usam sete caracteres. O padrão anterior aplicava o
# quantificador apenas ao último caractere; a primeira correção, por sua vez,
# aceitou `={7,}` e confundiu separadores decorativos longos com conflitos.
# Aqui aceitamos os marcadores reais: abertura/fechamento, base do diff3 e o
# separador central EXATAMENTE `=======`.
if git grep -n -E '^(<<<<<<<|>>>>>>>|\|\|\|\|\|\|\|)([[:space:]].*)?$|^=======$' -- \
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

# Senhas hardcoded em prosa/scripts: literais de 8+ caracteres com maiúscula, minúscula e dígito
# atribuídos a constantes com nome de senha (PWD|SENHA|PASSWORD|*_QA_*) ou após rótulos
# "Senha:"/"password:". Permitidos apenas se todos os matches estiverem na allowlist de falsos
# positivos documentados (ex.: constantes SAMPLE/PLACEHOLDER explícitas).
SENHAS_ALLOW_FILES='(\.claude/skills/|backend/tests/test_vault_router\.py|backend/tests/test_vault_testers\.py|qa/e2e/README\.md|backend/scripts/purga_dados_homologacao\.py|ci_guard\.sh|scripts/ingestao_rag\.sh|scripts/restore\.sh|\.md:)' 
SENHAS_ALVO="$(git grep -n -E '(^| )([A-Z_]*[A-Za-z]*(PWD|SENHA|PASSWORD)[A-Za-z]*|[A-Z_]+QA[A-Z_]*) *= *["\x27][^"\x27"]{8,}["\x27]' -- ':!**/node_modules/**' ':!**/.venv/**' ':!**/site-packages/**' ':!**/dist/**' ':!frontend/dist/**' 2>/dev/null || true)"
SENHAS_ROTULO="$(git grep -n -E '[Ss]enha *: *[^[:space:]]{8,}|password *: *["\x27][^"\x27"]{8,}["\x27]' -- ':!**/node_modules/**' ':!**/.venv/**' ':!**/site-packages/**' ':!**/dist/**' ':!frontend/dist/**' ':!**/.claude/skills/**' ':!qa/e2e/README.md' 2>/dev/null || true)"
if [[ -n "${SENHAS_ALVO}" ]]; then
  # Só falha se houver match FORA da allowlist
  fora_allow="$(echo "${SENHAS_ALVO}" | grep -vE "${SENHAS_ALLOW_FILES}" || true)"
  if [[ -n "${fora_allow}" ]]; then
    echo "::error::Possível senha hardcoded em código versionado. Use variável de ambiente (ex.: EJC_QA_PASSWORD)."
    printf '%s\n' "${fora_allow}"
    fail=1
  fi
fi
if [[ -n "${SENHAS_ROTULO}" ]]; then
  fora_allow="$(echo "${SENHAS_ROTULO}" | grep -vE "${SENHAS_ALLOW_FILES}" || true)"
  if [[ -n "${fora_allow}" ]]; then
    echo "::error::Possível senha em prosa em arquivo versionado. Rotacione e remova o literal."
    printf '%s\n' "${fora_allow}"
    fail=1
  fi
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
