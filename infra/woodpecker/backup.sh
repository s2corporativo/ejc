#!/usr/bin/env bash
# Backup consistente dos volumes do Woodpecker antes de atualizar/recriar.
# Não copia o .env nem imprime segredos.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

fail() {
  printf 'ERRO: %s\n' "$*" >&2
  exit 1
}

command -v docker >/dev/null 2>&1 || fail "docker ausente"
docker compose version >/dev/null 2>&1 || fail "plugin docker compose ausente"
docker compose config --quiet

BACKUP_ROOT="${WOODPECKER_BACKUP_DIR:-/var/backups/woodpecker}"
case "$BACKUP_ROOT" in
  /|/etc|/opt|/var|/root|/home) fail "diretório de backup amplo/inseguro: $BACKUP_ROOT" ;;
  /*) ;;
  *) fail "WOODPECKER_BACKUP_DIR deve ser caminho absoluto" ;;
esac

umask 077
mkdir -p -- "$BACKUP_ROOT"
chmod 700 -- "$BACKUP_ROOT"

server_container="$(docker compose ps -aq woodpecker-server)"
agent_container="$(docker compose ps -aq woodpecker-agent)"
[ -n "$server_container" ] || fail "contêiner woodpecker-server não existe"
[ -n "$agent_container" ] || fail "contêiner woodpecker-agent não existe"

server_volume="$(
  docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/woodpecker"}}{{.Name}}{{end}}{{end}}' "$server_container"
)"
agent_volume="$(
  docker inspect --format '{{range .Mounts}}{{if eq .Destination "/etc/woodpecker"}}{{.Name}}{{end}}{{end}}' "$agent_container"
)"
[ -n "$server_volume" ] || fail "volume do banco Woodpecker não encontrado"
[ -n "$agent_volume" ] || fail "volume de identidade do agente não encontrado"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
server_archive="woodpecker-server-data-$timestamp.tar.gz"
agent_archive="woodpecker-agent-config-$timestamp.tar.gz"

restart_services() {
  docker compose start woodpecker-server woodpecker-agent >/dev/null 2>&1 || true
}
trap restart_services EXIT

docker compose stop woodpecker-agent woodpecker-server

backup_volume() {
  local volume_name="$1" archive_name="$2"
  docker run --rm     -v "$volume_name:/source:ro"     -v "$BACKUP_ROOT:/backup"     busybox:1.37.0     sh -eu -c 'cd /source; tar -czf "/backup/$1" .' sh "$archive_name"
  [ -s "$BACKUP_ROOT/$archive_name" ] || fail "backup vazio: $archive_name"
  sha256sum "$BACKUP_ROOT/$archive_name" >"$BACKUP_ROOT/$archive_name.sha256"
  chmod 600 "$BACKUP_ROOT/$archive_name" "$BACKUP_ROOT/$archive_name.sha256"
}

backup_volume "$server_volume" "$server_archive"
backup_volume "$agent_volume" "$agent_archive"

docker compose start woodpecker-server woodpecker-agent
trap - EXIT

printf 'Backups concluídos:\n%s\n%s\n'   "$BACKUP_ROOT/$server_archive"   "$BACKUP_ROOT/$agent_archive"
