#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${APP_DIR:-/opt/ejc}"
REPORT_DIR="${EJC_MAINT_REPORT_DIR:-/var/lib/ejc-maintenance}"
mkdir -p "$REPORT_DIR"
cd "$APP_DIR"

log(){ printf '[ejc-weekly] %s\n' "$*"; }
git fetch --prune origin 'refs/heads/main:refs/remotes/origin/main'
MAIN_SHA="$(git rev-parse origin/main)"
DEPLOYED="$(tr -d '\r\n' < .deployed_sha 2>/dev/null || true)"
HEALTH_SHA="$(curl -fsS --connect-timeout 5 --max-time 15 https://ejc.depaulateixeira.adv.br/api/health | python3 -c 'import json,sys;print(json.load(sys.stdin).get("commit",""))')"

log "main=$MAIN_SHA deployed=$DEPLOYED health=$HEALTH_SHA"
[ "$MAIN_SHA" = "$DEPLOYED" ] || { log "ALERTA: main != .deployed_sha"; exit 2; }
[ "$MAIN_SHA" = "$HEALTH_SHA" ] || { log "ALERTA: main != produção"; exit 2; }

python3 scripts/branch_hygiene.py --manifest "$REPORT_DIR/branches.csv"
git worktree prune
docker container prune -f --filter until=168h
docker builder prune -af --filter until=168h
docker image prune -f --filter until=168h

if command -v graphify >/dev/null 2>&1; then
  GRAPHIFY_MAX_WORKERS=1 graphify update "$APP_DIR" --force --no-cluster >/var/log/ejc-graphify-weekly.log 2>&1 \
    || log "AVISO: graphify update falhou; ver /var/log/ejc-graphify-weekly.log"
fi

usage="$(df -P / | awk 'NR==2 {gsub("%","",$5); print $5}')"
log "uso_disco=${usage}%"
[ "$usage" -lt 85 ] || { log "ALERTA: disco >=85%"; exit 2; }
log "saneamento semanal concluído"
