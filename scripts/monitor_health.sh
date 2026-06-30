#!/usr/bin/env bash
# Monitor de saúde do EJC (cron). Verifica API + frontend, reinicia o container
# que cair, e — se continuar fora do ar após o reinício — ALERTA por e-mail
# (independente do app, via curl+SMTP lendo credenciais do .env). Avisa também
# quando o sistema RECUPERA. Cooldown evita spam de alertas.
set -euo pipefail

LOG_FILE="${LOG_FILE:-/var/log/ejc_health_monitor.log}"
LOCAL_API="${LOCAL_API:-http://127.0.0.1:8000/api/health}"
LOCAL_FRONTEND="${LOCAL_FRONTEND:-http://127.0.0.1:8080/}"
ENV_FILE="${ENV_FILE:-/opt/ejc/.env}"
STATE_DOWN="/tmp/ejc_health_down.flag"          # existe = sistema marcado como CAÍDO
STATE_LAST_ALERT="/tmp/ejc_health_last_alert"   # epoch do último alerta enviado
ALERT_COOLDOWN_S="${ALERT_COOLDOWN_S:-3600}"    # no máximo 1 alerta/hora

log() { echo "[$(date '+%F %T')] $*" >> "$LOG_FILE"; }

# Lê UMA variável do .env sem sourcear o arquivo inteiro (mais seguro).
# `|| true` no fim: variável ausente (grep sem match) NÃO pode matar o script
# sob `set -euo pipefail` — retorna vazio e segue.
envval() {
  grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | sed 's/^"//; s/"$//; s/^'"'"'//; s/'"'"'$//' || true
}

# Envia e-mail de alerta via SMTP (STARTTLS na 587). Falha silenciosa (só loga).
send_alert() {
  local assunto="$1" corpo="$2"
  local host port user pass rcpt msg
  host="$(envval SMTP_HOST)"; port="$(envval SMTP_PORT)"
  user="$(envval SMTP_USER)"; pass="$(envval SMTP_PASSWORD)"
  rcpt="$(envval ALERT_EMAIL)"; [ -z "$rcpt" ] && rcpt="$user"
  if [ -z "$host" ] || [ -z "$user" ] || [ -z "$pass" ]; then
    log "Alerta NAO enviado: SMTP ausente no .env (defina SMTP_* e opcional ALERT_EMAIL)"
    return 0
  fi
  msg="$(mktemp)"
  {
    echo "From: EJC Monitor <$user>"
    echo "To: $rcpt"
    echo "Subject: $assunto"
    echo "Content-Type: text/plain; charset=UTF-8"
    echo
    printf '%b\n' "$corpo"
    echo
    echo "-- Monitor automatico do EJC ($(hostname))"
  } > "$msg"
  if curl --silent --show-error --ssl-reqd "smtp://${host}:${port:-587}" \
       --mail-from "$user" --mail-rcpt "$rcpt" \
       --user "${user}:${pass}" --upload-file "$msg" >> "$LOG_FILE" 2>&1; then
    log "Alerta enviado a $rcpt: $assunto"
  else
    log "FALHA ao enviar alerta a $rcpt"
  fi
  rm -f "$msg"
}

# true (0) se já passou o cooldown desde o último alerta.
pode_alertar() {
  local agora last
  agora="$(date +%s)"
  last="$(cat "$STATE_LAST_ALERT" 2>/dev/null || echo 0)"
  if [ $(( agora - last )) -ge "$ALERT_COOLDOWN_S" ]; then
    echo "$agora" > "$STATE_LAST_ALERT"
    return 0
  fi
  return 1
}

# Modo de teste: `monitor_health.sh test-alert` só dispara um e-mail de teste e sai
# (sem checar saúde nem reiniciar nada). Use para validar a entrega de e-mail.
if [ "${1:-}" = "test-alert" ]; then
  send_alert "[EJC] Teste de alerta do monitor" \
    "Este e um e-mail de TESTE do monitor de saude do EJC.\nSe voce recebeu, os alertas automaticos estao funcionando."
  echo "Teste disparado — verifique o log ($LOG_FILE) e a caixa de entrada."
  exit 0
fi

api_code="$(curl -fsS -o /tmp/ejc_health_api.json -w "%{http_code}" "$LOCAL_API" 2>/dev/null || true)"
front_code="$(curl -fsS -o /tmp/ejc_health_front.html -w "%{http_code}" "$LOCAL_FRONTEND" 2>/dev/null || true)"

api_final="$api_code"
if [ "$api_code" != "200" ]; then
  log "API health falhou: HTTP ${api_code:-sem_resposta}. Reiniciando ejc_backend."
  docker restart ejc_backend >/dev/null 2>&1 || log "Falha ao reiniciar ejc_backend"
  sleep 10
  api_final="$(curl -fsS -o /tmp/ejc_health_api_retry.json -w "%{http_code}" "$LOCAL_API" 2>/dev/null || true)"
  log "API apos restart: HTTP ${api_final:-sem_resposta}"
fi

front_final="$front_code"
if [ "$front_code" != "200" ]; then
  log "Frontend health falhou: HTTP ${front_code:-sem_resposta}. Reiniciando ejc_frontend."
  docker restart ejc_frontend >/dev/null 2>&1 || log "Falha ao reiniciar ejc_frontend"
  sleep 10
  front_final="$(curl -fsS -o /dev/null -w "%{http_code}" "$LOCAL_FRONTEND" 2>/dev/null || true)"
fi

if [ "$api_final" = "200" ] && [ "$front_final" = "200" ]; then
  log "OK api=200 frontend=200"
  # Recuperou após uma queda registrada → avisa e limpa o estado.
  if [ -f "$STATE_DOWN" ]; then
    send_alert "[EJC] Sistema RECUPERADO" \
      "O EJC voltou ao normal (API e frontend = 200) apos uma indisponibilidade."
    rm -f "$STATE_DOWN"
  fi
else
  marca="api=${api_final:-sem_resposta} frontend=${front_final:-sem_resposta}"
  log "AINDA INDISPONIVEL apos restart: $marca"
  touch "$STATE_DOWN"
  if pode_alertar; then
    send_alert "[EJC] Sistema INDISPONIVEL" \
      "O EJC continua fora do ar mesmo apos o reinicio automatico.\nStatus: ${marca}\nDominio: https://ejc.depaulateixeira.adv.br\n\nAcoes: na VPS, rode 'docker ps' e 'docker logs ejc_backend --tail 50'."
  fi
fi
