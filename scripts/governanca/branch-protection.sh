#!/usr/bin/env bash
# =============================================================================
# branch-protection.sh — alterna SOMENTE os required status checks da main.
#
# Nunca reescreve a proteção completa: reviews, CODEOWNERS, restrictions,
# histórico linear e demais políticas permanecem intocados por construção.
#
# Modos:
#   --contextos          lista checks reportados no HEAD
#   --verificar          lê a proteção de status vigente (default, read-only)
#   --dry-run            mostra política cloud
#   --dry-run-fallback   mostra política fallback local
#   --cloud              aplica os cinco contexts canônicos do Actions
#   --fallback           salva o estado atual e exige EJC Local Full Gate/App
#   --restore            restaura exatamente o snapshot salvo antes do fallback
#
# `--fallback` é ato administrativo protegido e exige autorização #998.
# =============================================================================
set -euo pipefail

REPO="${EJC_REPO:-s2corporativo/ejc}"
BRANCH="${EJC_BRANCH:-main}"
MODO="${1:---verificar}"
FALLBACK_AUTHORIZATION="${EJC_FALLBACK_AUTHORIZATION:-}"
FALLBACK_APP_ID="${EJC_FALLBACK_APP_ID:-}"
STATE_ROOT="${EJC_CI_STATE_ROOT:-${XDG_CACHE_HOME:-${HOME}/.cache}/ejc-ci-fallback}"
BACKUP_FILE="${EJC_BRANCH_PROTECTION_BACKUP:-$STATE_ROOT/required-status-checks-anterior.json}"
API="repos/$REPO/branches/$BRANCH/protection/required_status_checks"

falhar() { printf '\nABORTADO: %s\n' "$1" >&2; exit 1; }
ok() { printf '  [ok] %s\n' "$1"; }
aviso() { printf '  [aviso] %s\n' "$1" >&2; }

command -v gh >/dev/null 2>&1 || falhar "GitHub CLI (gh) não encontrado."
command -v jq >/dev/null 2>&1 || falhar "jq não encontrado."
gh auth status >/dev/null 2>&1 || falhar "gh não autenticado."

canon() {
  realpath -m "$1" 2>/dev/null || printf '%s\n' "$1"
}

# Percorre o caminho bruto, sem canonicalizar antes do teste -L, para não
# mascarar justamente o symlink que precisa ser rejeitado.
assert_no_symlink_component() {
  local path="$1" limit="$2" current parent limit_resolved
  limit_resolved="$(canon "$limit")"
  current="$path"
  case "$current" in
    /*) ;;
    *) current="$PWD/$current" ;;
  esac
  while :; do
    [ ! -L "$current" ] \
      || falhar "snapshot recusado: componente symlink no caminho: $current"
    [ "$(canon "$current")" != "$limit_resolved" ] || break
    parent="$(dirname "$current")"
    [ "$parent" != "$current" ] \
      || falhar "snapshot não está contido em EJC_CI_STATE_ROOT"
    current="$parent"
  done
}

validate_backup_path() {
  local repo_root resolved_repo resolved_state resolved_backup backup_dir
  case "$STATE_ROOT" in
    /*) ;;
    *) falhar "EJC_CI_STATE_ROOT deve ser caminho absoluto" ;;
  esac
  case "$BACKUP_FILE" in
    /*) ;;
    *) falhar "snapshot de branch protection deve usar caminho absoluto" ;;
  esac

  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  [ -n "$repo_root" ] \
    || falhar "não foi possível determinar a raiz do repositório para validar o snapshot"
  resolved_repo="$(canon "$repo_root")"
  resolved_state="$(canon "$STATE_ROOT")"
  resolved_backup="$(canon "$BACKUP_FILE")"

  case "$resolved_backup" in
    "$resolved_state"/*) ;;
    *) falhar "snapshot deve permanecer confinado sob EJC_CI_STATE_ROOT" ;;
  esac
  case "$resolved_backup" in
    "$resolved_repo"|"$resolved_repo"/*)
      falhar "snapshot não pode ser gravado dentro do repositório" ;;
  esac
  case "$resolved_backup" in
    /opt/ejc|/opt/ejc/*)
      falhar "snapshot de branch protection não pode usar /opt/ejc" ;;
  esac

  # Verifica os componentes existentes antes de criar diretórios. `mkdir -p`
  # atravessa symlinks, portanto a checagem precisa antecedê-lo.
  assert_no_symlink_component "$BACKUP_FILE" "$STATE_ROOT"
  backup_dir="$(dirname "$BACKUP_FILE")"
  (umask 077 && mkdir -p "$backup_dir") \
    || falhar "não foi possível criar diretório do snapshot"
  chmod 700 "$backup_dir" 2>/dev/null || true

  # Revalidação reduz a janela TOCTOU e também cobre o caminho recém-criado.
  assert_no_symlink_component "$BACKUP_FILE" "$STATE_ROOT"
  BACKUP_FILE="$(canon "$BACKUP_FILE")"
}

normalize_status_checks() {
  jq -c '{
    strict: (.strict == true),
    checks: (
      if ((.checks // []) | length) > 0 then
        [(.checks // [])[] |
          if .app_id == null then {context: .context}
          else {context: .context, app_id: .app_id}
          end]
      else
        [(.contexts // [])[] | {context: .}]
      end
    )
  }'
}

canonical_for_compare() {
  jq -c '{
    strict: (.strict == true),
    checks: [(.checks // [])[] | {
      context: .context,
      app_id: (if has("app_id") then .app_id else null end)
    }] | sort_by(.context, (.app_id // -1))
  }'
}

get_status_checks() {
  gh api "$API" -H 'Accept: application/vnd.github+json'
}

status_checks_match_payload() {
  local current="$1" payload="$2" expected actual
  expected="$(printf '%s' "$payload" | canonical_for_compare)" || return 1
  actual="$(printf '%s' "$current" | normalize_status_checks | canonical_for_compare)" || return 1
  [ "$actual" = "$expected" ]
}

apply_status_checks() {
  local payload="$1" response current

  # PATCH pode ser aplicado no servidor e a conexão cair antes da resposta.
  # Nesse caso, repetir cegamente/acionar rollback cria um estado ambíguo.
  # Sempre reconciliamos por GET antes de declarar falha.
  if response="$(printf '%s' "$payload" | gh api -X PATCH "$API" \
      -H 'Accept: application/vnd.github+json' --input - 2>/dev/null)"; then
    if status_checks_match_payload "$response" "$payload"; then
      return 0
    fi
    aviso "resposta do PATCH divergiu do estado solicitado; executando read-after-write"
  else
    aviso "PATCH não retornou resposta confiável; verificando estado efetivo no GitHub"
  fi

  current="$(get_status_checks 2>/dev/null)" || {
    aviso "não foi possível reconciliar required status checks após PATCH ambíguo"
    return 1
  }
  if status_checks_match_payload "$current" "$payload"; then
    ok "estado solicitado confirmado por read-after-write"
    return 0
  fi
  aviso "estado efetivo não corresponde ao payload solicitado"
  return 1
}

save_current_status_checks() {
  local current normalized tmp
  validate_backup_path
  [ ! -e "$BACKUP_FILE" ] \
    || falhar "backup de required status checks já existe: $BACKUP_FILE; recuse sobrescrita e finalize/restaure a ativação anterior"
  current="$(get_status_checks 2>/dev/null)" \
    || falhar "não foi possível ler required status checks atuais; nada será alterado"
  normalized="$(printf '%s' "$current" | normalize_status_checks)" \
    || falhar "resposta atual de required status checks inválida"
  tmp="$BACKUP_FILE.tmp.$$"
  umask 077
  jq -n --arg repo "$REPO" --arg branch "$BRANCH" --argjson payload "$normalized" \
    '{schema:1, repo:$repo, branch:$branch, payload:$payload}' > "$tmp"
  chmod 600 "$tmp" 2>/dev/null || true
  mv "$tmp" "$BACKUP_FILE"
  ok "snapshot exato de required status checks salvo em $BACKUP_FILE"
}

restore_saved_status_checks() {
  validate_backup_path
  [ -s "$BACKUP_FILE" ] || falhar "snapshot de required status checks ausente: $BACKUP_FILE"
  local repo branch payload
  repo="$(jq -r '.repo // empty' "$BACKUP_FILE")"
  branch="$(jq -r '.branch // empty' "$BACKUP_FILE")"
  [ "$repo" = "$REPO" ] && [ "$branch" = "$BRANCH" ] \
    || falhar "snapshot pertence a outro repositório/branch"
  payload="$(jq -c '.payload' "$BACKUP_FILE")"
  printf '%s' "$payload" | jq -e '.strict == true and (.checks | type == "array")' >/dev/null \
    || falhar "snapshot de required status checks inválido"
  apply_status_checks "$payload" \
    || falhar "não foi possível restaurar/reconciliar required status checks anteriores"
  ok "required status checks anteriores restaurados exatamente"
}

PAYLOAD_CLOUD="$(jq -cn '{
  strict: true,
  checks: [
    {context:"Backend — suíte completa + schema/RAG (Postgres pgvector)"},
    {context:"Eval — smoke dos gold sets (offline, bloqueante)"},
    {context:"Frontend — testes + typecheck + build"},
    {context:"P0 guard — conflitos e segredos"},
    {context:"Governança — travas de PR"}
  ]
}')"

build_fallback_payload() {
  [[ "$FALLBACK_APP_ID" =~ ^[1-9][0-9]*$ ]] \
    || falhar "modo fallback exige EJC_FALLBACK_APP_ID numérico (>0)"
  jq -cn --argjson app_id "$FALLBACK_APP_ID" '{
    strict: true,
    checks: [{context:"EJC Local Full Gate", app_id:$app_id}]
  }'
}

if [ "$MODO" = "--contextos" ]; then
  SHA="$(gh api "repos/$REPO/commits/$BRANCH" --jq .sha 2>/dev/null)" \
    || falhar "não foi possível ler o HEAD de $BRANCH"
  echo "Checks efetivamente reportados no HEAD de $BRANCH:"
  gh api "repos/$REPO/commits/$SHA/check-runs?per_page=100" \
    --jq '.check_runs[] | [.name, (.app.id|tostring), .conclusion] | @tsv' 2>/dev/null | sort -u || true
  echo "Commit statuses informativos:"
  gh api "repos/$REPO/commits/$SHA/status" --jq '.statuses[].context' 2>/dev/null | sort -u || true
  exit 0
fi

if [ "$MODO" = "--verificar" ]; then
  get_status_checks | normalize_status_checks
  exit 0
fi

case "$MODO" in
  --dry-run)
    echo "Política cloud que seria aplicada somente a required status checks:"
    printf '%s\n' "$PAYLOAD_CLOUD"
    exit 0
    ;;
  --dry-run-fallback)
    echo "Política fallback que seria aplicada somente a required status checks:"
    build_fallback_payload
    exit 0
    ;;
  --cloud)
    apply_status_checks "$PAYLOAD_CLOUD" \
      || falhar "não foi possível aplicar/reconciliar os cinco required checks cloud"
    ok "cinco required checks cloud restaurados; demais proteções não foram tocadas"
    ;;
  --fallback)
    [ "$FALLBACK_AUTHORIZATION" = "998" ] \
      || falhar "modo --fallback exige EJC_FALLBACK_AUTHORIZATION=998"
    save_current_status_checks
    PAYLOAD_FALLBACK="$(build_fallback_payload)"
    if ! apply_status_checks "$PAYLOAD_FALLBACK"; then
      aviso "ativação fallback não pôde ser confirmada; restaurando snapshot anterior"
      restore_saved_status_checks || true
      falhar "não foi possível aplicar/reconciliar proteção fallback"
    fi
    ok "EJC Local Full Gate vinculado ao GitHub App id=$FALLBACK_APP_ID"
    ;;
  --restore)
    restore_saved_status_checks
    ;;
  *)
    falhar "modo inválido: $MODO"
    ;;
esac

cat <<'FIM'

Somente `required_status_checks` é alterado por este script.
Reviews, CODEOWNERS, enforce_admins, restrictions, histórico linear, resolução de
conversas, force-push e deleção permanecem exatamente como já estavam.
FIM