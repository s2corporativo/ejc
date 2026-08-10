#!/usr/bin/env bash
# Reproduz as travas objetivas de .github/workflows/governanca.yml fora do Actions.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
BASE="${EJC_GOV_BASE:-origin/main}"
REQUIRE_PR="${EJC_GOV_REQUIRE_PR:-1}"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

fail() { echo "[governanca-local] ERRO: $*" >&2; exit 1; }
warn() { echo "[governanca-local] AVISO: $*" >&2; }
ok() { echo "[governanca-local] ok: $*"; }

case "$(realpath "$ROOT" 2>/dev/null || printf '%s' "$ROOT")" in
  /opt/ejc|/opt/ejc/*) fail "recusado em /opt/ejc (produção)" ;;
esac
[ "${APP_ENV:-}" != "production" ] && [ "${EJC_ENV:-}" != "production" ] || fail "ambiente de produção ativo"

git rev-parse --verify "$BASE" >/dev/null 2>&1 || fail "base $BASE ausente; atualize o clone antes da validação"
git diff --name-only -z "$BASE...HEAD" > "$TMP" || fail "não foi possível enumerar arquivos alterados"
[ -s "$TMP" ] || fail "nenhum arquivo alterado em relação a $BASE"

BRANCH="$(git branch --show-current || true)"
[ "$BRANCH" != "main" ] && [ "$BRANCH" != "master" ] || fail "branch de origem protegida"

MIGRATION_CHANGED=0
RESERVATION_CHANGED=0
SENSITIVE_CHANGED=0
GOV_CHANGED=0
FUNCTIONAL_CHANGED=0
PADRAO_SENSIVEL='^(\.github/workflows/|\.claude/|scripts/(ci-local\.sh|ci-fallback[^/]*\.sh|governanca/(branch-protection|ci-local-governanca)\.sh)|backend/app/core/(security|config|auth|permissions)[^/]*\.py|backend/app/routers/(auth|users|uploads?|documents?|api_keys)[^/]*\.py|frontend/src/(stores/auth|pages/(Login|Configurar2FA|AccountSecurity)))'
PADRAO_GOV='^(CLAUDE\.md|AGENTS\.md|\.claude/|\.github/workflows/governanca\.yml|docs/GOVERNANCA_IA\.md|docs/GOVERNANCA_FASE2\.md|docs/FLUXO_DE_DESENVOLVIMENTO\.md|scripts/(ci-local\.sh|ci-fallback[^/]*\.sh|governanca/(branch-protection|ci-local-governanca)\.sh))'

PADROES='(AKIA[0-9A-Z]{16})|(-----BEGIN [A-Z ]*PRIVATE KEY-----)|(sk-[A-Za-z0-9]{20,})|(ghp_[A-Za-z0-9]{30,})|(xox[baprs]-[A-Za-z0-9-]{10,})'
ACHOU=0
while IFS= read -r -d '' f; do
  case "$f" in
    backend/alembic/versions/*) MIGRATION_CHANGED=1 ;;
    backend/alembic/MIGRATION_RESERVATIONS.md) RESERVATION_CHANGED=1 ;;
  esac
  [[ "$f" =~ $PADRAO_SENSIVEL ]] && SENSITIVE_CHANGED=1 || true
  [[ "$f" =~ $PADRAO_GOV ]] && GOV_CHANGED=1 || true
  case "$f" in backend/app/*|frontend/src/*) FUNCTIONAL_CHANGED=1;; esac

  case "$f" in
    .env.example|*/.env.example) ;;
    .env*|*/.env*) echo "[governanca-local] .env proibido: $f" >&2; ACHOU=1 ;;
  esac

  [ -f "$f" ] || continue
  if ! grep -EIn "$PADROES" -- "$f" >/dev/null 2>"$TMP.grep.err"; then
    rc=$?
    if [ "$rc" -ne 1 ]; then
      cat "$TMP.grep.err" >&2 || true
      fail "falha ao varrer possível segredo em caminho alterado"
    fi
  else
    echo "[governanca-local] possível segredo: $f" >&2
    ACHOU=1
  fi
  rm -f "$TMP.grep.err"
done < "$TMP"

if [ "$MIGRATION_CHANGED" -eq 1 ] && [ "$RESERVATION_CHANGED" -ne 1 ]; then
  fail "migration alterada sem atualizar MIGRATION_RESERVATIONS.md"
fi
ok "reserva de migration"
[ "$ACHOU" -eq 0 ] || fail "possível segredo/.env versionado"
ok "ausência de segredo aparente"

PR_BODY="${EJC_PR_BODY:-}"
PR_NUMBER="${EJC_PR_NUMBER:-}"
if [ -z "$PR_BODY" ] && command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  if [ -n "$PR_NUMBER" ]; then
    PR_BODY="$(gh pr view "$PR_NUMBER" --json body --jq .body 2>/dev/null || true)"
  elif [ -n "$BRANCH" ]; then
    PR_NUMBER="$(gh pr view "$BRANCH" --json number --jq .number 2>/dev/null || true)"
    [ -z "$PR_NUMBER" ] || PR_BODY="$(gh pr view "$PR_NUMBER" --json body --jq .body 2>/dev/null || true)"
  fi
fi

if [ "$REQUIRE_PR" = "1" ]; then
  [ -n "$PR_NUMBER" ] || fail "PR não localizado; gate promovível exige PR registrado"
  [ -n "$PR_BODY" ] || fail "corpo do PR vazio/indisponível"
  for secao in "Issue vinculada" "Solução" "Testes executados" "Riscos residuais" "Rollback"; do
    printf '%s' "$PR_BODY" | grep -qi -- "$secao" || fail "seção ausente no PR: $secao"
  done
  printf '%s' "$PR_BODY" | grep -Eq '#[0-9]+' || fail "PR sem Issue vinculada"
  ok "descrição do PR completa"
else
  warn "modo pre-push: descrição do PR não exigida"
fi

if [ "$SENSITIVE_CHANGED" -eq 1 ]; then
  printf '%s' "$PR_BODY" | grep -qi 'security-auditor: executado' || fail "mudança sensível sem registro literal 'security-auditor: executado'"
  ok "security-auditor registrado"
fi

if [ "$GOV_CHANGED" -eq 1 ] && [ "$FUNCTIONAL_CHANGED" -eq 1 ]; then
  warn "PR mistura governança/CI e código funcional; revisão de escopo reforçada necessária"
fi

ok "branch de origem: ${BRANCH:-detached}"
ok "Governança local aprovada"
