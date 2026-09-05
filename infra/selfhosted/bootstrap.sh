#!/usr/bin/env bash
set -Eeuo pipefail

# Orquestrador idempotente da automacao S2 na VPS.
# Por padrao instala apenas componentes seguros/preparatorios.
# Deploys e smoke de producao exigem opt-in explicito por variavel:
#   ACTIVATE_DEPLOYS=1 ACTIVATE_SMOKE=1 bash infra/selfhosted/bootstrap.sh

[ "$(id -u)" = "0" ] || { echo "[bootstrap] execute como root" >&2; exit 2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AUTOMATION_ROOT=/opt/s2-automation
KUMA_DIR="$AUTOMATION_ROOT/uptime-kuma"
ACTIVATE_DEPLOYS="${ACTIVATE_DEPLOYS:-0}"
ACTIVATE_SMOKE="${ACTIVATE_SMOKE:-0}"

case "$ACTIVATE_DEPLOYS" in 0|1) ;; *) echo "ACTIVATE_DEPLOYS deve ser 0 ou 1" >&2; exit 2;; esac
case "$ACTIVATE_SMOKE" in 0|1) ;; *) echo "ACTIVATE_SMOKE deve ser 0 ou 1" >&2; exit 2;; esac

log() { printf '[bootstrap] %s\n' "$*"; }
warn() { printf '[bootstrap] AVISO: %s\n' "$*" >&2; }
fail() { printf '[bootstrap] ERRO: %s\n' "$*" >&2; exit 2; }

command -v docker >/dev/null 2>&1 || fail "Docker ausente"
docker compose version >/dev/null 2>&1 || fail "Docker Compose ausente"
command -v systemctl >/dev/null 2>&1 || fail "systemd/systemctl ausente"

[ -x "$ROOT/infra/host-automation/install.sh" ] || fail "installer do gate central ausente"
[ -x "$ROOT/infra/renovate/install.sh" ] || fail "installer do Renovate ausente"
[ -f "$ROOT/infra/monitoring/uptime-kuma/docker-compose.yml" ] || fail "Compose do Uptime Kuma ausente"

install -d -m 755 "$AUTOMATION_ROOT" /etc/s2-automation

log "1/5 — instalando/atualizando gate central Woodpecker"
bash "$ROOT/infra/host-automation/install.sh"

log "2/5 — instalando/atualizando Renovate self-hosted"
bash "$ROOT/infra/renovate/install.sh"

log "3/5 — instalando/atualizando Uptime Kuma local"
install -d -m 755 "$KUMA_DIR"
install -m 644 "$ROOT/infra/monitoring/uptime-kuma/docker-compose.yml" "$KUMA_DIR/docker-compose.yml"
(
  cd "$KUMA_DIR"
  docker compose config --quiet
  docker compose pull
  docker compose up -d
  docker compose ps
)

log "4/5 — verificando ativacao de deploys host-level"
if [ "$ACTIVATE_DEPLOYS" = "1" ]; then
  [ -x "$ROOT/infra/host-automation/install-ejc-deploy.sh" ] || fail "installer EJC deploy ausente"
  bash "$ROOT/infra/host-automation/install-ejc-deploy.sh"

  if [ -x /opt/s2licit/scripts/install-approved-service.sh ]; then
    bash /opt/s2licit/scripts/install-approved-service.sh
  else
    warn "S2 Licit: /opt/s2licit/scripts/install-approved-service.sh ausente; merge/sincronize a main antes de ativar"
  fi

  if [ -x /opt/verdelimp-erp/deploy/contabo/install-approved-service.sh ]; then
    bash /opt/verdelimp-erp/deploy/contabo/install-approved-service.sh
  else
    warn "Verdelimp: installer host-level ausente em /opt/verdelimp-erp; merge/sincronize a main antes de ativar"
  fi
else
  log "deploys NAO ativados (padrao seguro). Use ACTIVATE_DEPLOYS=1 somente apos Woodpecker verde e credenciais root-only configuradas."
fi

log "5/5 — verificando smoke autenticado do S2 Licit"
if [ "$ACTIVATE_SMOKE" = "1" ]; then
  if [ -x /opt/s2licit/scripts/install-smoke-service.sh ]; then
    bash /opt/s2licit/scripts/install-smoke-service.sh
  else
    warn "S2 Licit: installer do smoke ausente; merge/sincronize a main antes de ativar"
  fi
else
  log "smoke NAO ativado (padrao seguro). Use ACTIVATE_SMOKE=1 depois de configurar a conta dedicada root-only."
fi

log "Resumo de servicos"
systemctl is-enabled s2-renovate.timer 2>/dev/null || true
systemctl is-active s2-renovate.timer 2>/dev/null || true
systemctl is-enabled ejc-deploy-approved.timer 2>/dev/null || true
systemctl is-active ejc-deploy-approved.timer 2>/dev/null || true
systemctl is-enabled s2licit-production-smoke.timer 2>/dev/null || true
systemctl is-active s2licit-production-smoke.timer 2>/dev/null || true
(
  cd "$KUMA_DIR"
  docker compose ps
) || true

cat <<'EOF'

[bootstrap] Preparacao concluida.
- Segredos permanecem fora do Git, em /etc/s2-automation, root-only.
- O Woodpecker continua sem privilegio de producao nos pipelines de PR.
- Uptime Kuma local nao substitui um monitor externo para queda total da VPS.
- Nao faça merge de PR com ci/woodpecker pendente ou falhando.
EOF
