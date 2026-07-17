#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Instala um GitHub Actions RUNNER SELF-HOSTED no VPS do EJC — a computação do CI
# passa a ser do SEU servidor (GitHub Actions minutes = 0), mantendo os checks de
# PR do GitHub. Roda a MESMA ci.yml, só que de graça.
#
# Rode UMA vez, como root, no VPS:
#   sudo RUNNER_TOKEN="xxxxx" scripts/setup-selfhosted-runner.sh
#
# O RUNNER_TOKEN (curto, ~1h) vem de:
#   GitHub → repo s2corporativo/ejc → Settings → Actions → Runners →
#   "New self-hosted runner" → Linux → copie o token do passo "./config.sh … --token XXXX"
#
# Idempotente: reexecutar reconfigura/atualiza o runner (usa --replace).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/s2corporativo/ejc}"
RUNNER_TOKEN="${RUNNER_TOKEN:-${1:-}}"
RUNNER_NAME="${RUNNER_NAME:-ejc-vps}"
RUNNER_LABELS="${RUNNER_LABELS:-self-hosted,ejc-vps}"
RUNNER_USER="${RUNNER_USER:-ghrunner}"
RUNNER_HOME="${RUNNER_HOME:-/opt/actions-runner}"
RUNNER_VERSION="${RUNNER_VERSION:-}"   # vazio = busca a última release

die() { printf '\033[1;31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }
log() { printf '\n\033[1;36m[runner-setup]\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }

[ "$(id -u)" = "0" ] || die "Rode como root (sudo)."
[ -n "$RUNNER_TOKEN" ] || die "Defina RUNNER_TOKEN (repo → Settings → Actions → Runners → New self-hosted runner)."

# ── Arquitetura ──────────────────────────────────────────────────────────────
case "$(uname -m)" in
  x86_64|amd64) ARCH=x64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) die "arquitetura não suportada: $(uname -m)" ;;
esac

# ── 1. Dependências nativas do CI (mesmas do ci.yml) + Docker + Node + utils ──
log "Instalando dependências nativas (apt)…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  curl tar jq ca-certificates sudo git \
  postgresql-client libmagic1 poppler-utils tesseract-ocr \
  libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0

# Docker (necessário para os service containers do CI — ex.: pgvector/pgvector).
if ! command -v docker >/dev/null 2>&1; then
  log "Docker ausente — instalando via get.docker.com…"
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null 2>&1 || true

# Node 20 (o job de frontend usa setup-node@v4, que baixa sozinho; instalamos o
# npm base para robustez e para o hook/CI local funcionarem no host).
if ! command -v node >/dev/null 2>&1; then
  log "Node ausente — instalando Node 20 (nodesource)…"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi
ok "Dependências prontas"

# ── 2. Usuário do runner (não-root) + grupos ─────────────────────────────────
if ! id "$RUNNER_USER" >/dev/null 2>&1; then
  log "Criando usuário $RUNNER_USER…"
  useradd -m -s /bin/bash "$RUNNER_USER"
fi
usermod -aG docker "$RUNNER_USER" 2>/dev/null || true
# ci.yml usa `sudo apt-get` num step → sudo SEM senha p/ o runner (repo privado,
# só colaboradores disparam workflows; risco controlado).
echo "$RUNNER_USER ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/99-ghrunner
chmod 440 /etc/sudoers.d/99-ghrunner

# ── 3. Baixa o runner do GitHub Actions ──────────────────────────────────────
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

# ── 4. Configura (não-interativo) ────────────────────────────────────────────
log "Registrando o runner no repositório…"
# Se já estava configurado, remove antes (idempotência).
if [ -f "$RUNNER_HOME/.runner" ]; then
  sudo -u "$RUNNER_USER" bash -c "cd '$RUNNER_HOME' && ./config.sh remove --token '$RUNNER_TOKEN'" >/dev/null 2>&1 || true
fi
sudo -u "$RUNNER_USER" bash -c "cd '$RUNNER_HOME' && ./config.sh \
  --url '$REPO_URL' --token '$RUNNER_TOKEN' \
  --name '$RUNNER_NAME' --labels '$RUNNER_LABELS' \
  --unattended --replace"

# ── 5. Instala como serviço systemd (sobe no boot, reinicia sozinho) ─────────
log "Instalando como serviço…"
( cd "$RUNNER_HOME" && ./svc.sh install "$RUNNER_USER" && ./svc.sh start )

ok "Runner '$RUNNER_NAME' online (labels: $RUNNER_LABELS)."
echo
echo "Próximo passo: no repositório, os workflows já apontam para 'self-hosted'"
echo "(ver docs/RUNNER_SELFHOSTED.md). Faça um push/PR de teste — o CI roda AQUI,"
echo "sem consumir minutos do GitHub. Status: ( cd $RUNNER_HOME && ./svc.sh status )"
