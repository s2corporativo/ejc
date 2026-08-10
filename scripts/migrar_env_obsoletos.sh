#!/usr/bin/env bash
# migrar_env_obsoletos.sh — ajusta valores OBSOLETOS num .env já existente.
#
# Garantias:
# - só altera chaves/valores antigos conhecidos;
# - idempotente;
# - exige backup antes da primeira escrita;
# - standalone cria backup timestamped owner-only;
# - callers transacionais podem fornecer --backup-path para reutilizar snapshot
#   já existente, desde que ele seja seguro e byte-a-byte igual ao estado atual;
# - nunca imprime valores secretos.
set -euo pipefail

ENV_FILE=".env"
ENV_FILE_SET=0
DRY_RUN=0
BACKUP_PATH=""

fail() {
  printf 'migrar_env: ERRO: %s\n' "$*" >&2
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --backup-path)
      [ "$#" -ge 2 ] || fail "--backup-path exige um caminho"
      [ -z "$BACKUP_PATH" ] || fail "--backup-path informado mais de uma vez"
      BACKUP_PATH="$2"
      shift 2
      ;;
    --*)
      fail "opção desconhecida: $1"
      ;;
    *)
      [ "$ENV_FILE_SET" -eq 0 ] || fail "apenas um arquivo .env pode ser informado"
      ENV_FILE="$1"
      ENV_FILE_SET=1
      shift
      ;;
  esac
done

if [ ! -f "$ENV_FILE" ]; then
  echo "migrar_env: ${ENV_FILE} não existe — nada a migrar."
  exit 0
fi
[ ! -L "$ENV_FILE" ] || fail "arquivo .env não pode ser symlink"

canon() {
  realpath -m -- "$1"
}

validate_backup_path() {
  [ -n "$BACKUP_PATH" ] || return 0
  command -v realpath >/dev/null 2>&1 || fail "realpath ausente"
  command -v stat >/dev/null 2>&1 || fail "stat ausente"
  command -v cmp >/dev/null 2>&1 || fail "cmp ausente"

  local env_canon backup_canon parent perm perm_dec
  env_canon="$(canon "$ENV_FILE")"
  backup_canon="$(canon "$BACKUP_PATH")"
  [ "$backup_canon" != "$env_canon" ] || fail "backup externo não pode ser o próprio .env"
  parent="$(dirname "$backup_canon")"
  [ -d "$parent" ] || fail "diretório do backup externo não existe: $parent"
  [ ! -L "$parent" ] || fail "diretório do backup externo não pode ser symlink"

  if [ -e "$BACKUP_PATH" ]; then
    [ -f "$BACKUP_PATH" ] || fail "backup externo existente não é arquivo regular"
    [ ! -L "$BACKUP_PATH" ] || fail "backup externo não pode ser symlink"
    perm="$(stat -c %a -- "$BACKUP_PATH")"
    [[ "$perm" =~ ^[0-7]{3,4}$ ]] || fail "permissão do backup externo inválida"
    perm_dec=$((8#$perm))
    (( (perm_dec & 077) == 0 )) || fail "backup externo é legível por grupo/outros"
    cmp -s -- "$ENV_FILE" "$BACKUP_PATH" \
      || fail "backup externo existente não corresponde ao estado atual do .env"
  fi
}

validate_backup_path
BACKUP_FEITO=0

backup_uma_vez() {
  [ "$BACKUP_FEITO" = "1" ] && return 0

  local destino
  if [ -n "$BACKUP_PATH" ]; then
    destino="$BACKUP_PATH"
    if [ -e "$destino" ]; then
      # validate_backup_path já provou segurança + identidade byte-a-byte.
      echo "migrar_env: snapshot transacional externo validado."
      BACKUP_FEITO=1
      return 0
    fi
  else
    destino="${ENV_FILE}.bak.$(date +%Y%m%d%H%M%S)"
  fi

  [ ! -e "$destino" ] || fail "destino de backup já existe inesperadamente"
  (umask 077 && cp -- "$ENV_FILE" "$destino")
  chmod 600 -- "$destino"
  [ ! -L "$destino" ] || fail "backup criado como symlink inesperadamente"
  cmp -s -- "$ENV_FILE" "$destino" || fail "backup criado não corresponde ao .env"
  echo "migrar_env: backup de rollback criado com permissão restrita."
  BACKUP_FEITO=1
}

escapar_padrao() {
  printf '%s' "$1" | sed 's/[][\.*^$\/|&]/\\&/g'
}

migrar_valor() {
  local chave="$1" antigo="$2" novo="$3" motivo="$4"
  local antigo_re novo_esc
  antigo_re="$(escapar_padrao "$antigo")"
  if ! grep -qE "^${chave}=${antigo_re}[[:space:]]*$" "$ENV_FILE"; then
    return 0
  fi
  if [ "$DRY_RUN" = "1" ]; then
    echo "migrar_env: [dry-run] ${chave} seria migrada para ${novo} (${motivo})"
    return 0
  fi

  backup_uma_vez
  novo_esc="$(printf '%s' "$novo" | sed 's/[\/|&]/\\&/g')"
  sed -i -E "s|^${chave}=${antigo_re}[[:space:]]*$|${chave}=${novo_esc}|" "$ENV_FILE"
  echo "migrar_env: ${chave} migrada para ${novo} (${motivo})"
}

GROQ_MODELO_DEPRECIADO="llama-3.3-70b-versatile"
GROQ_MODELO_ATUAL="openai/gpt-oss-120b"
migrar_valor "GROQ_MODEL" "$GROQ_MODELO_DEPRECIADO" "$GROQ_MODELO_ATUAL" \
  "modelo Groq depreciado"
migrar_valor "GROQ_MODEL_LARGE" "$GROQ_MODELO_DEPRECIADO" "$GROQ_MODELO_ATUAL" \
  "modelo Groq depreciado"

if grep -qE '^AI_AGENT_ENABLED=true[[:space:]]*$' "$ENV_FILE"; then
  echo "migrar_env: ATENÇÃO — AI_AGENT_ENABLED=true (agente de IA com"
  echo "            ferramentas de ESCRITA habilitado). A auditoria de"
  echo "            2026-07-26 recomenda false até a homologação do HITL."
fi

if [ "$BACKUP_FEITO" = "0" ] && [ "$DRY_RUN" = "0" ]; then
  echo "migrar_env: nenhum valor obsoleto encontrado — ${ENV_FILE} preservado."
fi
exit 0
