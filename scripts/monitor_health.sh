#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="${LOG_FILE:-/var/log/ejc_health_monitor.log}"
LOCAL_API="${LOCAL_API:-http://127.0.0.1:8000/api/health}"
LOCAL_FRONTEND="${LOCAL_FRONTEND:-http://127.0.0.1:8080/}"

log() {
  echo "[$(date '+%F %T')] $*" >> "$LOG_FILE"
}

api_code="$(curl -fsS -o /tmp/ejc_health_api.json -w "%{http_code}" "$LOCAL_API" 2>/dev/null || true)"
front_code="$(curl -fsS -o /tmp/ejc_health_front.html -w "%{http_code}" "$LOCAL_FRONTEND" 2>/dev/null || true)"

if [ "$api_code" != "200" ]; then
  log "API health falhou: HTTP ${api_code:-sem_resposta}. Reiniciando ejc_backend."
  docker restart ejc_backend >/dev/null 2>&1 || log "Falha ao reiniciar ejc_backend"
  sleep 10
  api_code2="$(curl -fsS -o /tmp/ejc_health_api_retry.json -w "%{http_code}" "$LOCAL_API" 2>/dev/null || true)"
  log "API apos restart: HTTP ${api_code2:-sem_resposta}"
fi

if [ "$front_code" != "200" ]; then
  log "Frontend health falhou: HTTP ${front_code:-sem_resposta}. Reiniciando ejc_frontend."
  docker restart ejc_frontend >/dev/null 2>&1 || log "Falha ao reiniciar ejc_frontend"
fi

if [ "$api_code" = "200" ] && [ "$front_code" = "200" ]; then
  log "OK api=200 frontend=200"
fi
