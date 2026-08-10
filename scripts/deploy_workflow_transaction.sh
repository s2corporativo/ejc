#!/usr/bin/env bash
# Executa a seção MUTÁVEL do workflow de produção sob um único mutex host-level:
# rsync → owner/mode do .env → deploy_vps_safe.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${APP_DIR:-/opt/ejc}"
RUN_ID="${GITHUB_RUN_ID:-manual}"
RUN_ATTEMPT="${GITHUB_RUN_ATTEMPT:-0}"
RUNNER_TEMP_SAFE="${RUNNER_TEMP:-}"
[ -n "$RUNNER_TEMP_SAFE" ] || { echo "[deploy-tx] RUNNER_TEMP ausente" >&2; exit 2; }
[ -d "$RUNNER_TEMP_SAFE" ] || { echo "[deploy-tx] RUNNER_TEMP inexistente" >&2; exit 2; }
STATE_FILE="${EJC_DEPLOY_TX_STATE_FILE:-$RUNNER_TEMP_SAFE/ejc-deploy-tx-${RUN_ID}-${RUN_ATTEMPT}.state}"

fail() {
  printf '[deploy-tx] ERRO: %s\n' "$*" >&2
  exit 2
}

canon() {
  realpath -m -- "$1"
}

command -v realpath >/dev/null 2>&1 || fail "realpath ausente"
command -v rsync >/dev/null 2>&1 || fail "rsync ausente"
command -v sudo >/dev/null 2>&1 || fail "sudo ausente"
[ -f "$ROOT/scripts/deploy_lock.sh" ] || fail "scripts/deploy_lock.sh ausente no checkout aprovado"

runner_canon="$(canon "$RUNNER_TEMP_SAFE")"
state_canon="$(canon "$STATE_FILE")"
[[ "$state_canon" == "$runner_canon/"* ]] || fail "arquivo de fase deve permanecer sob RUNNER_TEMP"
[ ! -L "$STATE_FILE" ] || fail "arquivo de fase não pode ser symlink"

write_phase() {
  local phase="$1" tmp="$STATE_FILE.tmp.$$"
  case "$phase" in
    pre_sync|sync_started|sync_completed|deploy_completed) ;;
    *) fail "fase inválida: $phase" ;;
  esac
  umask 077
  printf '%s\n' "$phase" > "$tmp"
  mv -f -- "$tmp" "$STATE_FILE"
}

write_phase pre_sync

# shellcheck source=deploy_lock.sh
source "$ROOT/scripts/deploy_lock.sh"
lock_rc=0
ejc_deploy_lock_acquire "$APP_DIR" || lock_rc=$?
case "$lock_rc" in
  0) ;;
  75)
    echo "[deploy-tx] outro deploy detém o mutex host-level; produção não foi tocada" >&2
    exit 75
    ;;
  *) fail "não foi possível adquirir mutex host-level" ;;
esac

write_phase sync_started
sudo -n rsync -a --delete \
  --exclude '.git/' \
  --exclude '.env' --exclude '.env.*' \
  --exclude '**/.env' --exclude '**/.env.*' \
  --exclude '.deployed_sha' \
  --exclude 'uploads/' --exclude 'backups/' \
  --exclude 'logs/' --exclude 'data/' --exclude 'storage/' \
  --exclude 'secrets/' --exclude 'certs/' --exclude 'tmp/' \
  --exclude 'node_modules/' --exclude 'frontend/node_modules/' \
  --exclude 'frontend/dist/' --exclude 'graphify-out/' \
  --exclude 'vps-tools/' --exclude '*.log' \
  "$ROOT/" "$APP_DIR/"
write_phase sync_completed

# O .env é preservado pelo rsync e deve permanecer legível apenas pelo runner
# dedicado (root continua tendo acesso por privilégio do SO).
sudo -n chown "$(id -u):$(id -g)" "$APP_DIR/.env"
sudo -n chmod 600 "$APP_DIR/.env"
[ "$(stat -c %a "$APP_DIR/.env")" = "600" ] || fail ".env não ficou 0600"
[ "$(stat -c %u:%g "$APP_DIR/.env")" = "$(id -u):$(id -g)" ] \
  || fail ".env não ficou sob o usuário/grupo do runner"

# EJC_DEPLOY_LOCK_FD=9 foi exportado pelo helper; o filho revalida que o FD
# herdado aponta para o MESMO inode/path e executa flock -n no próprio FD.
cd "$APP_DIR"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-0}" \
MIGRATIONS_BACKWARD_COMPATIBLE="${MIGRATIONS_BACKWARD_COMPATIBLE:-0}" \
RUN_SEEDS="${RUN_SEEDS:-0}" \
REQUIRE_PREDEPLOY_BACKUP="${REQUIRE_PREDEPLOY_BACKUP:-1}" \
bash scripts/deploy_vps_safe.sh

write_phase deploy_completed
printf '[deploy-tx] transação concluída para %s\n' "${TARGET_SHA:-sha-indisponível}"
