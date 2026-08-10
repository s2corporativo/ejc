#!/usr/bin/env bash
# Instala um runner self-hosted DEDICADO ao CI fallback do EJC.
# Deve rodar apenas em máquina/VM separada da produção.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/s2corporativo/ejc}"
RUNNER_TOKEN="${RUNNER_TOKEN:-${1:-}}"
GH_TOKEN_LOCAL="${GH_TOKEN:-}"
RUNNER_NAME="${RUNNER_NAME:-ejc-ci-fallback}"
RUNNER_LABELS="${RUNNER_LABELS:-self-hosted,linux,ejc-ci,ejc-ci-isolado}"
RUNNER_USER="${RUNNER_USER:-ejcci}"
RUNNER_HOME="${RUNNER_HOME:-/opt/ejc-ci-runner}"
RUNNER_VERSION="${RUNNER_VERSION:-}"
PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/ejc-ci-browsers}"
RUNNER_START_ATTEMPTS="${RUNNER_START_ATTEMPTS:-20}"
RUNNER_START_INTERVAL="${RUNNER_START_INTERVAL:-2}"
SERVICE_NAME=""

log() { printf '\n\033[1;36m[ejc-ci-runner]\033[0m %s\n' "$*"; }
ok() { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" = "0" ] || die "Rode o bootstrap como root."
[ "${APP_ENV:-}" != "production" ] || die "APP_ENV=production: host recusado."
[ ! -e /opt/ejc/.env ] || die "/opt/ejc/.env detectado: não instalar CI em produção."
[ ! -e /opt/ejc/.deployed_sha ] || die "/opt/ejc/.deployed_sha detectado: não instalar CI em produção."
if [ -d /opt/ejc ] && [ -f /opt/ejc/docker-compose.yml ]; then
  die "/opt/ejc parece instalação do EJC produtivo; use outra máquina/VM."
fi
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  for nome in ejc_backend ejc_db ejc_frontend ejc_worker; do
    if docker ps --format '{{.Names}}' | grep -qx "$nome"; then
      die "container produtivo $nome detectado; use outro host."
    fi
  done
fi

case "$(uname -m)" in
  x86_64|amd64) ARCH=x64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) die "arquitetura não suportada: $(uname -m)" ;;
esac

# Para operação autônoma, um GH_TOKEN com permissão administrativa de Actions
# pode gerar o token temporário de registro sem copiar segredo para arquivo/log.
# RUNNER_TOKEN continua aceito como opção de bootstrap pontual.
if [ -z "$RUNNER_TOKEN" ] && [ -n "$GH_TOKEN_LOCAL" ]; then
  REPO_SLUG="${REPO_URL#https://github.com/}"
  REPO_SLUG="${REPO_SLUG%.git}"
  log "Obtendo token temporário de registro pela API do GitHub…"
  RUNNER_TOKEN="$(curl -fsSL -X POST \
    -H 'Accept: application/vnd.github+json' \
    -H "Authorization: Bearer $GH_TOKEN_LOCAL" \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    "https://api.github.com/repos/${REPO_SLUG}/actions/runners/registration-token" \
    | jq -r '.token // empty')"
fi
[ -n "$RUNNER_TOKEN" ] || die "Defina RUNNER_TOKEN temporário ou GH_TOKEN com permissão para registrar runner; nunca grave o token em arquivo ou log."

service_name_from_file() {
  [ -s "$RUNNER_HOME/.service" ] && tr -d '\r\n' < "$RUNNER_HOME/.service" || true
}

stop_and_uninstall_service() {
  [ -x "$RUNNER_HOME/svc.sh" ] || return 0
  SERVICE_NAME="$(service_name_from_file)"
  if [ -n "$SERVICE_NAME" ] || [ -f "$RUNNER_HOME/.service" ]; then
    (cd "$RUNNER_HOME" && ./svc.sh stop) >/dev/null 2>&1 || true
    (cd "$RUNNER_HOME" && ./svc.sh uninstall) >/dev/null 2>&1 || true
  fi
}

remove_local_registration() {
  rm -f "$RUNNER_HOME/.runner" "$RUNNER_HOME/.credentials" "$RUNNER_HOME/.credentials_rsaparams"
}

wait_for_active_service() {
  local tentativa
  SERVICE_NAME="$(service_name_from_file)"
  [ -n "$SERVICE_NAME" ] || die "nome do serviço não registrado."
  systemctl enable "$SERVICE_NAME" >/dev/null 2>&1 || true
  systemctl restart "$SERVICE_NAME"
  for ((tentativa=1; tentativa<=RUNNER_START_ATTEMPTS; tentativa++)); do
    systemctl is-active --quiet "$SERVICE_NAME" && return 0
    sleep "$RUNNER_START_INTERVAL"
  done
  journalctl -u "$SERVICE_NAME" -n 80 --no-pager >&2 || true
  die "serviço do runner não ficou ativo."
}

log "Instalando dependências do host dedicado"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  curl tar jq ca-certificates git sudo \
  python3 python3-venv python3-pip \
  postgresql-client libmagic1 poppler-utils tesseract-ocr \
  libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
  libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
  libxrandr2 libgbm1 libasound2

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null

if ! command -v node >/dev/null 2>&1 || [ "$(node -p 'Number(process.versions.node.split(`.`)[0])')" -lt 22 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

if ! id "$RUNNER_USER" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "$RUNNER_USER"
fi
usermod -aG docker "$RUNNER_USER"

# Não existe sudo NOPASSWD para o usuário do CI. O host é preparado uma vez
# como root; os jobs subsequentes rodam sem privilégio administrativo.
rm -f "/etc/sudoers.d/99-${RUNNER_USER}" 2>/dev/null || true

log "Pré-instalando Chromium do Playwright em caminho compartilhado"
mkdir -p "$PLAYWRIGHT_BROWSERS_PATH"
chown -R "$RUNNER_USER:$RUNNER_USER" "$PLAYWRIGHT_BROWSERS_PATH"
sudo -u "$RUNNER_USER" env PLAYWRIGHT_BROWSERS_PATH="$PLAYWRIGHT_BROWSERS_PATH" \
  npx -y playwright@1.56.1 install chromium >/dev/null

if [ -z "$RUNNER_VERSION" ]; then
  RUNNER_VERSION="$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest | jq -r '.tag_name' | sed 's/^v//')"
  [ -n "$RUNNER_VERSION" ] && [ "$RUNNER_VERSION" != "null" ] || RUNNER_VERSION="2.328.0"
fi

log "Instalando GitHub Actions runner v$RUNNER_VERSION"
mkdir -p "$RUNNER_HOME"
TARBALL="actions-runner-linux-${ARCH}-${RUNNER_VERSION}.tar.gz"
if [ ! -x "$RUNNER_HOME/config.sh" ]; then
  curl -fsSL -o "/tmp/$TARBALL" \
    "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${TARBALL}"
  tar xzf "/tmp/$TARBALL" -C "$RUNNER_HOME"
  rm -f "/tmp/$TARBALL"
fi
chown -R "$RUNNER_USER:$RUNNER_USER" "$RUNNER_HOME"

stop_and_uninstall_service
if [ -f "$RUNNER_HOME/.runner" ]; then
  if ! sudo -u "$RUNNER_USER" bash -c \
    "cd '$RUNNER_HOME' && ./config.sh remove --token '$RUNNER_TOKEN'" >/dev/null 2>&1; then
    remove_local_registration
  fi
fi

log "Registrando runner dedicado"
sudo -u "$RUNNER_USER" bash -c "cd '$RUNNER_HOME' && ./config.sh \
  --url '$REPO_URL' --token '$RUNNER_TOKEN' \
  --name '$RUNNER_NAME' --labels '$RUNNER_LABELS' \
  --work '_work' --unattended --replace"

(cd "$RUNNER_HOME" && ./svc.sh install "$RUNNER_USER")
wait_for_active_service
(cd "$RUNNER_HOME" && ./svc.sh status) || true
ok "Runner '$RUNNER_NAME' ativo, isolado e sem sudo administrativo."
