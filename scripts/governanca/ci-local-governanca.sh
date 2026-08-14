#!/usr/bin/env bash
# Reproduz as travas objetivas de .github/workflows/governanca.yml fora do Actions.
# O script executado é o root of trust do controlador; EJC_GOV_SOURCE_ROOT aponta
# para o snapshot do PR que será apenas lido, nunca executado por este processo.
# Complexidade: O(B) sobre bytes dos arquivos alterados.
set -euo pipefail
umask 077

TRUST_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ROOT="${EJC_GOV_SOURCE_ROOT:-$TRUST_ROOT}"
ROOT="$(cd "$ROOT" && pwd -P)"
cd "$ROOT"
BASE="${EJC_GOV_BASE:-origin/main}"
REQUIRE_PR="${EJC_GOV_REQUIRE_PR:-1}"
TMP="$(mktemp)"
trap 'rm -f "$TMP" "$TMP.grep.err"' EXIT

fail() { echo "[governanca-local] ERRO: $*" >&2; exit 1; }
warn() { echo "[governanca-local] AVISO: $*" >&2; }
ok() { echo "[governanca-local] ok: $*"; }

case "$(realpath "$ROOT" 2>/dev/null || printf '%s' "$ROOT")" in
  /opt/ejc|/opt/ejc/*) fail "source root recusado em /opt/ejc (produção)" ;;
esac
[ "${APP_ENV:-}" != "production" ] && [ "${EJC_ENV:-}" != "production" ] || fail "ambiente de produção ativo"
[ -e "$ROOT/.git" ] || fail "source root não é checkout/worktree Git"

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
ROOT_OF_TRUST='scripts/(ci-local\.sh|ci-fallback[^/]*\.sh|ci-worker-isolation\.sh|github-app-auth\.sh|ci_evidence\.py|ci_activation_journal\.py|governanca/(branch-protection|ci-local-governanca)\.sh)'
PADRAO_SENSIVEL="^(\\.github/workflows/|\\.claude/|${ROOT_OF_TRUST}|backend/app/core/(security|config|auth|permissions)[^/]*\\.py|backend/app/routers/(auth|users|uploads?|documents?|api_keys)[^/]*\\.py|frontend/src/(stores/auth|pages/(Login|Configurar2FA|AccountSecurity)))"
PADRAO_GOV="^(CLAUDE\\.md|AGENTS\\.md|\\.claude/|\\.github/workflows/governanca\\.yml|docs/GOVERNANCA_IA\\.md|docs/GOVERNANCA_FASE2\\.md|docs/FLUXO_DE_DESENVOLVIMENTO\\.md|docs/CI_SEM_GITHUB\\.md|${ROOT_OF_TRUST})"
PADROES='(AKIA[0-9A-Z]{16})|(-----BEGIN [A-Z ]*PRIVATE KEY-----)|(sk-[A-Za-z0-9]{20,})|(github_pat_[A-Za-z0-9_]{20,})|(ghp_[A-Za-z0-9]{30,})|(gho_[A-Za-z0-9]{30,})|(ghu_[A-Za-z0-9]{30,})|(ghs_[A-Za-z0-9]{30,})|(ghr_[A-Za-z0-9]{30,})|(xox[baprs]-[A-Za-z0-9-]{10,})'
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

  # Varre o blob do HEAD, não o worktree, para detectar segredos commitados
  # independentemente de alterações locais não commitadas.
  if ! git cat-file -e HEAD:"$f" 2>/dev/null; then
    continue
  fi
  if [ "$(git cat-file -t HEAD:"$f" 2>/dev/null)" != "blob" ]; then
    continue
  fi
  set +e
  git show HEAD:"$f" | grep -EIn "$PADROES" >/dev/null 2>"$TMP.grep.err"
  rc=$?
  set -e
  case "$rc" in
    0) echo "[governanca-local] possível segredo: $f" >&2; ACHOU=1 ;;
    1) : ;;
    *) cat "$TMP.grep.err" >&2 || true; fail "falha ao varrer possível segredo em caminho alterado" ;;
  esac
  : > "$TMP.grep.err"
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
  EVIDENCE_DIR="${EJC_CI_STATE_ROOT:-${XDG_CACHE_HOME:-${HOME}/.cache}/ejc-ci-fallback}/security-auditor-evidence"
  HEAD_SHA="$(git rev-parse HEAD)"
  EVIDENCE_FILE="$EVIDENCE_DIR/$HEAD_SHA.json"
  CONTROLLER_UID="$(id -u)"

  [ -d "$EVIDENCE_DIR" ] || fail "mudança sensível sem diretório de evidência autenticada do security-auditor"
  [ ! -L "$EVIDENCE_DIR" ] || fail "diretório de evidência do security-auditor não pode ser symlink"
  [ "$(stat -c '%u' "$EVIDENCE_DIR" 2>/dev/null || printf 'invalid')" = "$CONTROLLER_UID" ] \
    || fail "diretório de evidência do security-auditor não pertence ao controlador"
  [ $((8#$(stat -c '%a' "$EVIDENCE_DIR" 2>/dev/null || printf '777') & 8#022)) -eq 0 ] \
    || fail "diretório de evidência do security-auditor é gravável por grupo/outros"

  [ -f "$EVIDENCE_FILE" ] && [ ! -L "$EVIDENCE_FILE" ] \
    || fail "mudança sensível sem evidência autenticada de security-auditor vinculada ao HEAD SHA"
  [ "$(stat -c '%u' "$EVIDENCE_FILE" 2>/dev/null || printf 'invalid')" = "$CONTROLLER_UID" ] \
    || fail "evidência do security-auditor não pertence ao controlador"
  [ $((8#$(stat -c '%a' "$EVIDENCE_FILE" 2>/dev/null || printf '777') & 8#022)) -eq 0 ] \
    || fail "evidência do security-auditor é gravável por grupo/outros"

  EVIDENCE_SHA="$(jq -r '.head_sha // ""' "$EVIDENCE_FILE" 2>/dev/null || true)"
  EVIDENCE_RESULT="$(jq -r '.result // ""' "$EVIDENCE_FILE" 2>/dev/null || true)"
  EVIDENCE_ISSUER="$(jq -r '.issuer // ""' "$EVIDENCE_FILE" 2>/dev/null || true)"
  [ "$EVIDENCE_SHA" = "$HEAD_SHA" ] \
    || fail "evidência de security-auditor com SHA divergente (esperado $HEAD_SHA, encontrado $EVIDENCE_SHA)"
  [ "$EVIDENCE_RESULT" = "completed" ] \
    || fail "security-auditor não concluído com resultado positivo para o HEAD SHA"
  [ "$EVIDENCE_ISSUER" = "security-auditor" ] \
    || fail "evidência não emitida pela identidade security-auditor"
  ok "security-auditor evidenciado de forma fail-closed para SHA $HEAD_SHA"
fi

if [ "$GOV_CHANGED" -eq 1 ] && [ "$FUNCTIONAL_CHANGED" -eq 1 ]; then
  warn "PR mistura governança/CI e código funcional; revisão de escopo reforçada necessária"
fi

ok "branch de origem: ${BRANCH:-detached}"
ok "Governança local aprovada contra source root explícito"
