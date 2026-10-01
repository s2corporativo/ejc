#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FREEZE_UNTIL="${EJC_FINANCE_FREEZE_UNTIL:-2026-10-08}"
TODAY="${EJC_FINANCE_FREEZE_DATE_OVERRIDE:-$(date -u +%F)}"

if [ "${EJC_FINANCE_FREEZE_OVERRIDE:-0}" = "1" ]; then
  echo "FINANCE FREEZE: override explícito ativo."
  exit 0
fi
if [[ "$TODAY" > "$FREEZE_UNTIL" ]]; then
  echo "FINANCE FREEZE: janela encerrada em $FREEZE_UNTIL; skip."
  exit 0
fi

TARGET="${CI_COMMIT_TARGET_BRANCH:-main}"
git fetch --quiet origin "refs/heads/$TARGET:refs/remotes/origin/$TARGET" || true
BASE="origin/$TARGET"
if [ -n "${CI_PREV_COMMIT_SHA:-}" ] && git cat-file -e "${CI_PREV_COMMIT_SHA}^{commit}" 2>/dev/null; then
  BASE="$CI_PREV_COMMIT_SHA"
elif [ -n "${CI_COMMIT_BEFORE:-}" ] && git cat-file -e "${CI_COMMIT_BEFORE}^{commit}" 2>/dev/null; then
  BASE="$CI_COMMIT_BEFORE"
fi

mapfile -t CHANGED < <(
  git diff --name-only "$BASE"...HEAD -- \
    'backend/app/routers/financeiro/**' \
    'backend/app/routers/fees.py' \
    'backend/app/routers/despesas.py' \
    'backend/app/routers/partner_withdrawals.py' \
    'backend/app/services/finance_*' \
    'backend/app/services/fee_ledger.py' \
    'frontend/src/pages/Financeiro*.tsx' \
    'frontend/src/pages/Honorarios.tsx' \
    'frontend/src/pages/Despesas*.tsx' \
    'frontend/src/pages/Comissoes.tsx' \
    'frontend/src/lib/financeiro.ts' \
    'frontend/src/types/financeiro.ts'
)

if [ "${#CHANGED[@]}" -eq 0 ]; then
  echo "FINANCE FREEZE: núcleo financeiro não alterado."
  exit 0
fi

mapfile -t SUBJECTS < <(git log --format='%s' "$BASE"..HEAD)
if [ "${#SUBJECTS[@]}" -eq 0 ]; then
  SUBJECTS=("$(git log -1 --format='%s' HEAD)")
fi

allowed='^(fix|test|docs|perf|sec|security|a11y|chore)(\([^)]*\))?:'
for subject in "${SUBJECTS[@]}"; do
  if ! [[ "$subject" =~ $allowed ]]; then
    echo "FINANCE FREEZE BLOQUEOU: '$subject'" >&2
    echo "Até $FREEZE_UNTIL, o Financeiro aceita apenas correção, teste, segurança, desempenho, acessibilidade, documentação ou manutenção." >&2
    echo "Para decisão explícita excepcional: EJC_FINANCE_FREEZE_OVERRIDE=1." >&2
    printf '  - %s\n' "${CHANGED[@]}" >&2
    exit 1
  fi
done

echo "FINANCE FREEZE: alterações de estabilização permitidas até $FREEZE_UNTIL."
