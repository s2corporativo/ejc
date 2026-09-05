#!/usr/bin/env bash
set -euo pipefail

IMAGE="${RENOVATE_IMAGE:-ghcr.io/renovatebot/renovate:44.39.3}"
CONFIG_DIR="${RENOVATE_CONFIG_DIR:-/opt/s2-automation/renovate}"
ENV_FILE="${RENOVATE_ENV_FILE:-/etc/s2-automation/renovate.env}"
CONFIG_FILE="$CONFIG_DIR/config.js"

fail() { printf '[renovate] ERRO: %s\n' "$*" >&2; exit 2; }

command -v docker >/dev/null 2>&1 || fail "docker ausente"
[ -f "$CONFIG_FILE" ] || fail "config ausente: $CONFIG_FILE"
[ -f "$ENV_FILE" ] || fail "credenciais ausentes: $ENV_FILE"

mode="$(stat -c '%a' "$ENV_FILE")"
owner="$(stat -c '%u' "$ENV_FILE")"
[ "$owner" = "0" ] || fail "$ENV_FILE deve pertencer a root"
case "$mode" in
  600|640) ;;
  *) fail "$ENV_FILE deve usar modo 600 ou 640; atual=$mode" ;;
esac

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
[ -n "${RENOVATE_TOKEN:-}" ] || fail "RENOVATE_TOKEN vazio"
[ "$RENOVATE_TOKEN" != "TROCAR" ] || fail "RENOVATE_TOKEN ainda e placeholder"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker pull "$IMAGE"
fi

exec docker run --rm \
  --name s2-renovate \
  --env-file "$ENV_FILE" \
  -e RENOVATE_CONFIG_FILE=/opt/renovate/config.js \
  -v "$CONFIG_FILE:/opt/renovate/config.js:ro" \
  "$IMAGE"
