#!/usr/bin/env bash
# ── scripts/monitor_health.sh ────────────────────────────────────────────────
# Cão de guarda de saúde do EJC (cron na VPS). Reinicia backend/frontend quando
# o health local não responde 200.
#
# POR QUE ESTE ARQUIVO FOI REESCRITO EM 04/09/2026
#
# A versão anterior tinha o defeito que a tornava inútil exatamente no cenário
# para o qual existia. Ela sondava assim:
#
#     curl -fsS -o /tmp/ejc_health_api.json -w "%{http_code}" "$LOCAL_API"
#
# SEM `--max-time`. O curl não tem timeout por padrão. Quando o backend TRAVA
# (aceita a conexão TCP e nunca responde — foi o incidente de 04/09: nginx
# devolvendo 504 só depois de 120 s, inclusive para rota inexistente), o curl
# fica pendurado para sempre e o script NUNCA alcança a linha do
# `docker restart`. O cão de guarda ficava preso na mesma armadilha que
# vigiava. Pior: a cada disparo do cron nascia mais um curl eterno, empilhando
# processos e consumindo a VPS — que hospeda outros cinco sistemas.
#
# `-f` agravava: com ele o curl devolve status 22 e string vazia em qualquer
# 4xx/5xx, então "500 constante" e "sem resposta" ficavam indistinguíveis no
# log — e o operador perdia justamente a informação que aponta a causa.
#
# CONTRATO DESTA VERSÃO
#   1. TODA sondagem tem `--max-time`. Sem exceção. Sonda sem teto não é sonda.
#   2. Uma execução por vez (flock). Cron nunca empilha instância.
#   3. Distingue "sem resposta" (000) de "código de erro" — são causas
#      diferentes e o log precisa dizer qual.
#   4. Não reinicia em laço: respeita um intervalo mínimo entre reinícios do
#      mesmo container. Reiniciar de 5 em 5 minutos não conserta banco travado,
#      só esconde o incidente e impede o diagnóstico.
#   5. Antes de reiniciar, guarda as últimas linhas do log do container — o
#      restart apaga o rastro, e sem o rastro o problema volta.
set -euo pipefail

LOG_FILE="${LOG_FILE:-/var/log/ejc_health_monitor.log}"
LOCAL_API="${LOCAL_API:-http://127.0.0.1:8000/api/health}"
LOCAL_FRONTEND="${LOCAL_FRONTEND:-http://127.0.0.1:8080/}"
# Teto por sondagem. Curto de propósito: o health é um SELECT 1, e a questão
# aqui é "responde?", não "responde rápido?". 10 s já é generoso.
TIMEOUT="${HEALTH_TIMEOUT:-10}"
# Intervalo mínimo entre reinícios do MESMO container (segundos). 15 min por
# padrão: tempo de o container subir e de um humano ver o alerta.
COOLDOWN="${HEALTH_RESTART_COOLDOWN:-900}"
ESTADO_DIR="${HEALTH_STATE_DIR:-/var/lib/ejc-health}"
LOCK_FILE="${HEALTH_LOCK_FILE:-/var/lock/ejc_health_monitor.lock}"
# Onde guardar o log do container antes de reiniciá-lo.
FORENSE_DIR="${HEALTH_FORENSICS_DIR:-/var/log/ejc-health-forense}"

log() { echo "[$(date '+%F %T')] $*" >> "$LOG_FILE"; }

# ── Instância única ─────────────────────────────────────────────────────────
# Sem isto, um backend travado geraria uma instância nova a cada disparo do
# cron. `-n` = não espera: se já há uma rodando, esta sai em silêncio.
if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    log "já há uma verificação em andamento — saindo (isto é normal durante um incidente)"
    exit 0
  fi
fi

mkdir -p "$ESTADO_DIR" "$FORENSE_DIR" 2>/dev/null || true

# ── Sondagem com teto obrigatório ───────────────────────────────────────────
# Sem `-f`: queremos o código real (500 é diagnóstico diferente de 000).
# `%{http_code}` devolve 000 quando não houve resposta HTTP alguma.
#
# SEM `|| echo 000`: em falha de conexão ou timeout o curl JÁ imprime `000` por
# causa do `-w` E sai com status != 0, então o `||` acrescentava um segundo
# valor e o resultado capturado virava `000000` (reproduzido contra uma porta
# local fechada). O `case` de `descrever` perdia o ramo `000` e o log anunciava
# um código HTTP inexistente em vez do diagnóstico "SEM RESPOSTA" prometido —
# justamente no cenário para o qual este arquivo existe. Achado da revisão do PR.
sondar() {
  local saida
  saida="$(curl -sS -o /dev/null --max-time "$TIMEOUT" -w '%{http_code}' "$1" 2>/dev/null || true)"
  # Normaliza qualquer saída inesperada (vazia, ou mais de um código) para o
  # primeiro token de 3 dígitos; sem correspondência, 000.
  saida="$(printf '%s' "$saida" | grep -oE '^[0-9]{3}' | head -1 || true)"
  printf '%s' "${saida:-000}"
}

descrever() {
  case "$1" in
    200) echo "ok" ;;
    000) echo "SEM RESPOSTA em ${TIMEOUT}s (travado ou porta fechada)" ;;
    5*)  echo "erro de servidor HTTP $1 (processo vivo, requisição falhando)" ;;
    *)   echo "HTTP $1" ;;
  esac
}

# ── Reinício com trava de repetição e coleta de rastro ──────────────────────
reiniciar() {
  local container="$1" motivo="$2"
  local marca="$ESTADO_DIR/${container}.ultimo_restart"
  local agora; agora="$(date +%s)"

  if [ -f "$marca" ]; then
    local anterior; anterior="$(cat "$marca" 2>/dev/null || echo 0)"
    local decorrido=$(( agora - anterior ))
    if [ "$decorrido" -lt "$COOLDOWN" ]; then
      log "$container: $motivo — NÃO reiniciando (último restart há ${decorrido}s, mínimo ${COOLDOWN}s)."
      log "$container: reinício repetido não conserta causa externa (banco travado, disco cheio). INTERVENÇÃO HUMANA NECESSÁRIA."
      return 1
    fi
  fi

  # O restart apaga o log em memória do processo. Guardar ANTES é o que
  # permite descobrir a causa depois — sem isto, cada restart destrói a prova.
  local destino="$FORENSE_DIR/${container}-$(date +%Y%m%d%H%M%S).log"
  docker logs --tail 200 "$container" > "$destino" 2>&1 || true
  log "$container: log pré-restart salvo em $destino"

  log "$container: $motivo — reiniciando."
  if docker restart "$container" >/dev/null 2>&1; then
    echo "$agora" > "$marca"
  else
    log "$container: FALHA ao reiniciar."
    return 1
  fi
  return 0
}

# ── Verificação ─────────────────────────────────────────────────────────────
api_code="$(sondar "$LOCAL_API")"
front_code="$(sondar "$LOCAL_FRONTEND")"

if [ "$api_code" != "200" ]; then
  if reiniciar ejc_backend "API $(descrever "$api_code")"; then
    # Espera o boot: com os timeouts de startup o lifespan termina em poucos
    # segundos mesmo degradado, mas o processo ainda precisa subir.
    sleep 20
    api_retry="$(sondar "$LOCAL_API")"
    log "API após restart: $(descrever "$api_retry")"
    [ "$api_retry" = "200" ] || log "API SEGUE FORA após restart — a causa é externa ao container. Verifique banco, disco e memória."
  fi
fi

if [ "$front_code" != "200" ]; then
  reiniciar ejc_frontend "Frontend $(descrever "$front_code")" || true
fi

if [ "$api_code" = "200" ] && [ "$front_code" = "200" ]; then
  log "OK api=200 frontend=200"
fi
