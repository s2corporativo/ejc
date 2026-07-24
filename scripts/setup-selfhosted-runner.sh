#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Instala ou recupera o GitHub Actions runner self-hosted do EJC na VPS.
#
# Uso, como root:
#   sudo RUNNER_TOKEN="xxxxx" scripts/setup-selfhosted-runner.sh
#
# O token é temporário e deve ser obtido diretamente em:
# GitHub → Settings → Actions → Runners → New self-hosted runner.
# Nunca registre o token em arquivo, issue, commit ou log.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/s2corporativo/ejc}"
RUNNER_TOKEN="${RUNNER_TOKEN:-${1:-}}"
RUNNER_NAME="${RUNNER_NAME:-ejc-vps}"
RUNNER_LABELS="${RUNNER_LABELS:-self-hosted,ejc-vps}"
RUNNER_USER="${RUNNER_USER:-ghrunner}"
RUNNER_HOME="${RUNNER_HOME:-/opt/actions-runner}"
RUNNER_VERSION="${RUNNER_VERSION:-}" # vazio = busca a última release
RUNNER_START_ATTEMPTS="${RUNNER_START_ATTEMPTS:-15}"
RUNNER_START_INTERVAL="${RUNNER_START_INTERVAL:-2}"

SERVICE_NAME=""

die() { printf '\033[1;31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }
log() { printf '\n\033[1;36m[runner-setup]\033[0m %s\n' "$*"; }
ok() { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }

[ "$(id -u)" = "0" ] || die "Rode como root (sudo)."
[ -n "$RUNNER_TOKEN" ] || die "Defina RUNNER_TOKEN no ambiente; não grave o token em arquivo ou log."

case "$(uname -m)" in
  x86_64 | amd64) ARCH=x64 ;;
  aarch64 | arm64) ARCH=arm64 ;;
  *) die "arquitetura não suportada: $(uname -m)" ;;
esac

service_name_from_file() {
  if [ -s "$RUNNER_HOME/.service" ]; then
    tr -d '\r\n' < "$RUNNER_HOME/.service"
  fi
}

stop_and_uninstall_service() {
  [ -x "$RUNNER_HOME/svc.sh" ] || return 0

  SERVICE_NAME="$(service_name_from_file)"
  if [ -n "$SERVICE_NAME" ] || [ -f "$RUNNER_HOME/.service" ]; then
    log "Parando e desinstalando o serviço existente antes da reconfiguração…"
    (cd "$RUNNER_HOME" && ./svc.sh stop) >/dev/null 2>&1 || true
    (cd "$RUNNER_HOME" && ./svc.sh uninstall) >/dev/null 2>&1 || true
  fi
}

remove_local_registration() {
  rm -f \
    "$RUNNER_HOME/.runner" \
    "$RUNNER_HOME/.credentials" \
    "$RUNNER_HOME/.credentials_rsaparams"
}

wait_for_active_service() {
  local attempt
  SERVICE_NAME="$(service_name_from_file)"
  [ -n "$SERVICE_NAME" ] || die "svc.sh não registrou o nome do serviço em $RUNNER_HOME/.service."

  systemctl enable "$SERVICE_NAME" >/dev/null 2>&1 || true
  systemctl restart "$SERVICE_NAME"

  for ((attempt = 1; attempt <= RUNNER_START_ATTEMPTS; attempt++)); do
    if systemctl is-active --quiet "$SERVICE_NAME"; then
      return 0
    fi
    sleep "$RUNNER_START_INTERVAL"
  done

  journalctl -u "$SERVICE_NAME" -n 80 --no-pager >&2 || true
  die "serviço $SERVICE_NAME não ficou ativo após ${RUNNER_START_ATTEMPTS} tentativas."
}

# ── 1. Dependências nativas do CI, deploy e runner ────────────────────────────
log "Instalando dependências nativas…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  curl tar jq ca-certificates sudo git rsync \
  postgresql-client libmagic1 poppler-utils tesseract-ocr \
  libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0

if ! command -v docker >/dev/null 2>&1; then
  log "Docker ausente — instalando pelo instalador oficial…"
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null 2>&1 || true

if ! command -v node >/dev/null 2>&1; then
  log "Node ausente — instalando Node 20…"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi
ok "Dependências prontas"

# ── 2. Usuário do runner ──────────────────────────────────────────────────────
if ! id "$RUNNER_USER" >/dev/null 2>&1; then
  log "Criando usuário $RUNNER_USER…"
  useradd -m -s /bin/bash "$RUNNER_USER"
fi
usermod -aG docker "$RUNNER_USER" 2>/dev/null || true

# Compatibilidade com os workflows atuais. A redução desta permissão deve ser
# tratada em mudança separada, após eliminar os `sudo` genéricos dos workflows.
echo "$RUNNER_USER ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/99-ghrunner
chmod 440 /etc/sudoers.d/99-ghrunner

# ── 3. Binário do runner ──────────────────────────────────────────────────────
if [ -z "$RUNNER_VERSION" ]; then
  RUNNER_VERSION="$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest \
    | jq -r '.tag_name' | sed 's/^v//')"
  [ -n "$RUNNER_VERSION" ] && [ "$RUNNER_VERSION" != "null" ] || RUNNER_VERSION="2.328.0"
fi

log "Instalando GitHub Actions runner v$RUNNER_VERSION ($ARCH) em $RUNNER_HOME…"
mkdir -p "$RUNNER_HOME"
TARBALL="actions-runner-linux-${ARCH}-${RUNNER_VERSION}.tar.gz"
if [ ! -f "$RUNNER_HOME/config.sh" ]; then
  curl -fsSL -o "/tmp/$TARBALL" \
    "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${TARBALL}"
  tar xzf "/tmp/$TARBALL" -C "$RUNNER_HOME"
  rm -f "/tmp/$TARBALL"
fi
chown -R "$RUNNER_USER:$RUNNER_USER" "$RUNNER_HOME"

# ── 4. Recuperação idempotente e registro ─────────────────────────────────────
stop_and_uninstall_service

if [ -f "$RUNNER_HOME/.runner" ]; then
  log "Removendo o registro anterior…"
  if ! sudo -u "$RUNNER_USER" bash -c \
    "cd '$RUNNER_HOME' && ./config.sh remove --token '$RUNNER_TOKEN'" \
    >/dev/null 2>&1; then
    log "Remoção remota não concluída; limpando somente o registro local parado."
    remove_local_registration
  fi
fi

log "Registrando o runner no repositório…"
sudo -u "$RUNNER_USER" bash -c "cd '$RUNNER_HOME' && ./config.sh \
  --url '$REPO_URL' --token '$RUNNER_TOKEN' \
  --name '$RUNNER_NAME' --labels '$RUNNER_LABELS' \
  --unattended --replace"

# ── 5. Serviço systemd e prova de saúde ───────────────────────────────────────
log "Instalando e iniciando o serviço…"
(cd "$RUNNER_HOME" && ./svc.sh install "$RUNNER_USER")
wait_for_active_service

(cd "$RUNNER_HOME" && ./svc.sh status) || true
ok "Runner '$RUNNER_NAME' ativo no systemd (labels: $RUNNER_LABELS)."
echo "Confirme também no GitHub que o runner aparece online e ocioso."
