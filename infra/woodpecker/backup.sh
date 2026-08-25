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

# Renderiza em arquivo privado para validar o contrato sem imprimir segredos.
rendered_compose="$(mktemp)"
chmod 600 -- "$rendered_compose"
cleanup_rendered() {
  rm -f -- "$rendered_compose"
}
trap cleanup_rendered EXIT
docker compose config >"$rendered_compose"

compose_value() {
  local key="$1"
  awk -v key="$key" '
    $1 == key ":" {
      sub(/^[^:]+:[[:space:]]*/, "")
      print
      exit
    }
  ' "$rendered_compose"
}

agent_secret="$(compose_value WOODPECKER_AGENT_SECRET)"
grpc_secret="$(compose_value WOODPECKER_GRPC_SECRET)"
[ -n "$agent_secret" ] || fail "WOODPECKER_AGENT_SECRET não chegou ao compose renderizado"
[ -n "$grpc_secret" ] || fail "WOODPECKER_GRPC_SECRET não chegou ao compose renderizado"
[ "$agent_secret" != "$grpc_secret" ] \
  || fail "WOODPECKER_AGENT_SECRET e WOODPECKER_GRPC_SECRET devem ser diferentes"

cleanup_rendered
trap - EXIT

BACKUP_ROOT="${WOODPECKER_BACKUP_DIR:-/var/backups/woodpecker}"
case "$BACKUP_ROOT" in
  /|/etc|/opt|/var|/root|/home|/tmp|/usr) fail "diretório de backup amplo/inseguro: $BACKUP_ROOT" ;;
  /etc/*|/root/*|/home/*|/tmp/*|/usr/*|/bin/*|/sbin/*|/lib/*|/lib64/*|/boot/*|/dev/*|/proc/*|/sys/*|/run/*)
    fail "diretório de backup em árvore insegura: $BACKUP_ROOT"
    ;;
  /*) ;;
  *) fail "WOODPECKER_BACKUP_DIR deve ser caminho absoluto" ;;
esac
[ "$(basename -- "$BACKUP_ROOT")" = "woodpecker" ] \
  || fail "use um diretório dedicado terminado em /woodpecker"
normalized_backup_root="$(realpath -m -- "$BACKUP_ROOT")"
[ "$normalized_backup_root" = "$BACKUP_ROOT" ] \
  || fail "diretório de backup não pode conter symlink ou travessia: $BACKUP_ROOT"

umask 077
if [ -e "$BACKUP_ROOT" ]; then
  [ -d "$BACKUP_ROOT" ] || fail "destino de backup não é diretório"
  [ ! -L "$BACKUP_ROOT" ] || fail "destino de backup não pode ser symlink"
  [ "$(stat -c '%u' -- "$BACKUP_ROOT")" = "$(id -u)" ] \
    || fail "destino de backup pertence a outro usuário"
  [ "$(stat -c '%a' -- "$BACKUP_ROOT")" = "700" ] \
    || fail "destino existente deve ter permissão 700"
else
  mkdir -p -- "$BACKUP_ROOT"
  chmod 700 -- "$BACKUP_ROOT"
fi

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

verify_volume=""
cleanup_on_exit() {
  if [ -n "$verify_volume" ]; then
    docker volume rm "$verify_volume" >/dev/null 2>&1 || true
  fi
  docker compose start woodpecker-server woodpecker-agent >/dev/null 2>&1 || true
}
trap cleanup_on_exit EXIT

docker compose stop woodpecker-agent woodpecker-server

backup_volume() {
  local volume_name="$1" archive_name="$2"
  docker run --rm \
    -v "$volume_name:/source:ro" \
    -v "$BACKUP_ROOT:/backup" \
    busybox:1.37.0 \
    sh -eu -c 'cd /source; tar -czf "/backup/$1" .' sh "$archive_name"
  [ -s "$BACKUP_ROOT/$archive_name" ] || fail "backup vazio: $archive_name"
  sha256sum "$BACKUP_ROOT/$archive_name" >"$BACKUP_ROOT/$archive_name.sha256"
  chmod 600 "$BACKUP_ROOT/$archive_name" "$BACKUP_ROOT/$archive_name.sha256"
  sha256sum -c -- "$BACKUP_ROOT/$archive_name.sha256" >/dev/null
  tar -tzf "$BACKUP_ROOT/$archive_name" >/dev/null
}

verify_restore() {
  local archive_name="$1"
  verify_volume="$(docker volume create)"
  docker run --rm \
    -v "$verify_volume:/restore" \
    -v "$BACKUP_ROOT:/backup:ro" \
    busybox:1.37.0 \
    sh -eu -c 'cd /restore; tar -xzf "/backup/$1"' sh "$archive_name"
  docker volume rm "$verify_volume" >/dev/null
  verify_volume=""
}

backup_volume "$server_volume" "$server_archive"
backup_volume "$agent_volume" "$agent_archive"
verify_restore "$server_archive"
verify_restore "$agent_archive"

git_head="$(git -C "$SCRIPT_DIR/../.." rev-parse HEAD 2>/dev/null || printf 'indisponivel')"
server_image_ref="$(docker inspect --format '{{.Config.Image}}' "$server_container")"
server_image_id="$(docker inspect --format '{{.Image}}' "$server_container")"
agent_image_ref="$(docker inspect --format '{{.Config.Image}}' "$agent_container")"
agent_image_id="$(docker inspect --format '{{.Image}}' "$agent_container")"
manifest="woodpecker-backup-$timestamp.manifest"
printf '%s\n' \
  "created_utc=$timestamp" \
  "git_head=$git_head" \
  "server_archive=$server_archive" \
  "server_volume=$server_volume" \
  "server_image_ref=$server_image_ref" \
  "server_image_id=$server_image_id" \
  "agent_archive=$agent_archive" \
  "agent_volume=$agent_volume" \
  "agent_image_ref=$agent_image_ref" \
  "agent_image_id=$agent_image_id" \
  >"$BACKUP_ROOT/$manifest"
sha256sum "$BACKUP_ROOT/$manifest" >"$BACKUP_ROOT/$manifest.sha256"
chmod 600 "$BACKUP_ROOT/$manifest" "$BACKUP_ROOT/$manifest.sha256"
sha256sum -c -- "$BACKUP_ROOT/$manifest.sha256" >/dev/null

docker compose start woodpecker-server woodpecker-agent
trap - EXIT

printf 'Backups verificados e manifesto criado:\n%s\n%s\n%s\n' \
  "$BACKUP_ROOT/$server_archive" \
  "$BACKUP_ROOT/$agent_archive" \
  "$BACKUP_ROOT/$manifest"
