#!/usr/bin/env bash
# ── scripts/reanimar_ejc.sh ──────────────────────────────────────────────────
# Diagnostica e reergue o EJC em produção, em fases, cada uma reversível.
#
# POR QUE EXISTE
#
# Em 04/09/2026 a produção estava assim, medido de fora:
#
#     GET /               → 200 em 0,49 s   (SPA estático)
#     GET /api/health     → sem resposta    (0 bytes em 45 s)
#     GET /api/naoexiste  → 504 em 120,58 s (= proxy_read_timeout do nginx)
#
# Rota INEXISTENTE também travava — um 404 não toca banco nem IA. E 504, não
# 502, prova que a porta 8000 aceitava a conexão: container de pé, boot preso.
# Somado a isso, `/opt/ejc/.deploy_last_sha` nunca existiu (commit 100549e):
# nenhum deploy manual jamais rodou, então produção está dezenas de commits e
# ~29 migrations atrás da `main`.
#
# Reerguer isso exige, NESTA ORDEM: ver o log antes de mexer (a causa some no
# restart), destravar a API, só então implantar o código novo, e só por último
# religar as cargas pesadas. Fazer fora de ordem é trocar um sistema mudo por
# um sistema mudo com dados a mais para perder.
#
# ONDE RODAR: na VPS, como root ou com `sudo -n`, a partir de um CHECKOUT GIT
# do repositório (NÃO de dentro de /opt/ejc).
#
#     git fetch origin main && git checkout origin/main
#     bash scripts/reanimar_ejc.sh --diagnostico      # só lê, não muta NADA
#     bash scripts/reanimar_ejc.sh --destravar        # fase 1
#     bash scripts/reanimar_ejc.sh --deploy <SHA>     # fase 2
#     bash scripts/reanimar_ejc.sh --flags            # fase 3
#     bash scripts/reanimar_ejc.sh --embeddings       # fase 4 (a mais pesada)
#
# O QUE ESTE SCRIPT NUNCA FAZ, em nenhuma fase:
#   `docker compose down -v`, `docker volume rm`, `docker system prune`,
#   `rm -rf`, `dropdb`, `alembic downgrade`, `git reset --hard`,
#   `git clean -fd`, nem qualquer escrita direta no banco de produção.
# O deploy é DELEGADO a `scripts/deploy_manual.sh`, que já carrega backup
# obrigatório, mutex, classificação de migration e rollback automático.
# Nunca chame `deploy_vps_safe.sh` direto: lá `RUN_MIGRATIONS` cai no default
# 0 e o deploy fica "verde" com o schema atrasado.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ejc}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${EJC_BASE_URL:-https://ejc.depaulateixeira.adv.br}"
CONTAINER="${EJC_BACKEND_CONTAINER:-ejc_backend}"
ACAO=""
TARGET_SHA=""

log()   { printf '\n\033[1m[reanimar]\033[0m %s\n' "$*"; }
info()  { printf '   %s\n' "$*"; }
aviso() { printf '\n\033[33m[reanimar] ATENÇÃO:\033[0m %s\n' "$*"; }
erro()  { printf '\n\033[31m[reanimar] ERRO:\033[0m %s\n' "$*" >&2; exit 2; }

confirmar() {
  local resposta
  printf '\n>>> %s\n    Digite "sim" para seguir (qualquer outra coisa aborta): ' "$1"
  read -r resposta
  [ "$resposta" = "sim" ] || erro "abortado pelo operador em: $1"
}

usage() { sed -n '2,45p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --diagnostico|--destravar|--flags|--embeddings) ACAO="${1#--}"; shift ;;
    --deploy) ACAO="deploy"; TARGET_SHA="${2:-}"; shift 2 || usage ;;
    -h|--help) usage ;;
    *) erro "argumento desconhecido: $1 (use --help)" ;;
  esac
done
[ -n "$ACAO" ] || usage

# O script vive dentro do checkout e a fase de deploy troca o SHA do checkout.
# Rodar de dentro de /opt/ejc trocaria o script debaixo dos próprios pés.
case "$ROOT" in
  "$APP_DIR"|"$APP_DIR"/*) erro "rode a partir de um checkout git, não de $APP_DIR" ;;
esac

# ── Sondagem HTTP: separa "nginx não alcança" de "backend não responde" ──────
sondar_api() {
  local caminho="$1" limite="${2:-20}" saida
  saida="$(curl -sS -o /dev/null -m "$limite" \
            -w '%{http_code} %{time_total}' "${BASE_URL}${caminho}" 2>/dev/null || echo "000 timeout")"
  printf '   %-22s → HTTP %s\n' "$caminho" "$saida"
  echo "$saida" | awk '{print $1}'
}

interpretar_sonda() {
  local codigo="$1"
  case "$codigo" in
    200) info "✅ backend respondendo." ;;
    502) aviso "502 IMEDIATO = porta 8000 fechada. Container caído ou uvicorn morto." ;;
    504) aviso "504 = nginx conecta e o backend não responde. Boot preso ou workers travados." ;;
    000) aviso "sem resposta dentro do limite — mesmo quadro do 504, só que antes do teto do nginx." ;;
    *)   info "código inesperado ($codigo) — leia o log do container." ;;
  esac
}

# ═════════════════════════ FASE 0 — DIAGNÓSTICO ═════════════════════════════
# SOMENTE LEITURA. Rode SEMPRE antes de qualquer outra fase: o restart apaga o
# rastro da causa, e sem a causa o problema volta.
fase_diagnostico() {
  log "FASE 0 — diagnóstico (somente leitura, nada é alterado)"

  log "1/7 · Sondagem HTTP externa"
  local c_health c_inexistente
  c_health="$(sondar_api /api/health 25)"
  c_inexistente="$(sondar_api /api/naoexiste 25)"
  sondar_api / 15 >/dev/null || true
  interpretar_sonda "$c_health"
  if [ "$c_health" != "200" ] && [ "$c_inexistente" != "200" ]; then
    info "Rota inexistente também não responde → o processo ASGI não atende NADA."
  fi

  log "2/7 · Containers"
  docker ps -a --filter "name=ejc" \
    --format 'table {{.Names}}\t{{.Status}}\t{{.RestartCount}}\t{{.Image}}' 2>/dev/null \
    || aviso "docker ps falhou — sem permissão no socket?"

  log "3/7 · Log do backend — as 80 últimas linhas (AQUI está a causa)"
  info "Procure: a última linha '[EJC] ...' impressa diz onde o boot parou."
  info "Sequência esperada: Banco de dados → Feriados → Suspensões → Cofre → v3.0 iniciado."
  docker logs --tail 80 "$CONTAINER" 2>&1 | sed 's/^/   | /' \
    || aviso "sem log para $CONTAINER"

  log "4/7 · Banco: está aceitando conexão?"
  docker exec ejc_db pg_isready -U "${POSTGRES_USER:-ejc_user}" 2>&1 | sed 's/^/   /' \
    || aviso "pg_isready falhou — o Postgres é a suspeita nº 1 do boot preso."

  log "5/7 · Locks e conexões presas no Postgres"
  docker exec ejc_db psql -U "${POSTGRES_USER:-ejc_user}" -d "${POSTGRES_DB:-ejc_db}" -c \
    "SELECT pid, state, wait_event_type, wait_event, left(query,60) AS query,
            now()-query_start AS duracao
       FROM pg_stat_activity
      WHERE state <> 'idle' ORDER BY query_start LIMIT 15;" 2>&1 | sed 's/^/   /' \
    || aviso "não consegui consultar pg_stat_activity"

  log "6/7 · Disco e memória (a VPS hospeda 6 sistemas)"
  df -h / /var/lib/docker 2>/dev/null | sed 's/^/   /' || true
  free -h 2>/dev/null | sed 's/^/   /' || true
  info "Disco cheio prende o Postgres sem derrubá-lo — é exatamente o quadro do 504."

  log "7/7 · Defasagem do código em produção"
  if [ -f "$APP_DIR/.deployed_sha" ]; then
    info "SHA implantado: $(cat "$APP_DIR/.deployed_sha")"
  else
    aviso "$APP_DIR/.deployed_sha NÃO existe — nenhum deploy manual jamais rodou."
  fi
  git -C "$ROOT" fetch -q origin main 2>/dev/null || true
  info "HEAD de origin/main: $(git -C "$ROOT" rev-parse --short origin/main 2>/dev/null || echo '?')"

  log "FASE 0 concluída. Nada foi alterado."
  info "Guarde a saída acima ANTES de rodar --destravar: o restart apaga o rastro."
}

# ═════════════════════════ FASE 1 — DESTRAVAR ═══════════════════════════════
# Só reinicia o backend. Não recria, não toca em volume, não implanta código.
fase_destravar() {
  log "FASE 1 — destravar a API (restart do backend, sem recriar container)"
  aviso "Rode --diagnostico ANTES. O restart apaga o rastro da causa."
  confirmar "Reiniciar o container $CONTAINER"

  docker restart "$CONTAINER" >/dev/null || erro "restart falhou"
  info "restart disparado; aguardando o boot concluir…"

  local i codigo=""
  for i in $(seq 1 30); do
    sleep 5
    codigo="$(curl -sS -o /dev/null -m 10 -w '%{http_code}' "${BASE_URL}/api/health" 2>/dev/null || echo 000)"
    printf '   tentativa %2d/30 → HTTP %s\n' "$i" "$codigo"
    [ "$codigo" = "200" ] && break
  done

  if [ "$codigo" = "200" ]; then
    log "✅ API respondendo."
    curl -sS -m 10 "${BASE_URL}/api/health" | sed 's/^/   /' || true
    aviso "Isto é PALIATIVO. O código em produção ainda é o antigo, SEM os"
    aviso "timeouts de boot — se a causa persistir, trava de novo. Siga para --deploy."
  else
    aviso "API ainda não responde após ~150 s."
    info "Volte ao log: docker logs --tail 120 $CONTAINER"
    info "A última linha '[EJC] ...' diz o passo que travou."
    info "Se parou logo após 'Banco de dados', o Postgres é a causa (fase 0, passos 4-6)."
  fi
}

# ═════════════════════════ FASE 2 — DEPLOY ══════════════════════════════════
fase_deploy() {
  [ -n "$TARGET_SHA" ] || erro "--deploy exige o SHA: --deploy <commit>"
  log "FASE 2 — implantar $TARGET_SHA"
  info "Delegado a scripts/deploy_manual.sh: backup obrigatório, mutex,"
  info "classificação de migration e rollback automático já vivem lá."

  git -C "$ROOT" fetch -q origin main || erro "git fetch falhou"
  git -C "$ROOT" checkout -q "$TARGET_SHA" || erro "checkout de $TARGET_SHA falhou"

  log "2.1 · Ensaio (--dry-run): confere tudo e NÃO muta produção"
  bash "$ROOT/scripts/deploy_manual.sh" --sha "$TARGET_SHA" --dry-run

  aviso "O ensaio acima passou. A implantação real aplica ~29 migrations pendentes."
  aviso "Se a classificação de migration acusou algo NÃO expand-only, PARE e me chame."
  confirmar "Implantar $TARGET_SHA em produção AGORA"

  bash "$ROOT/scripts/deploy_manual.sh" --sha "$TARGET_SHA"

  log "2.2 · Verificação pós-deploy"
  bash "$ROOT/scripts/post_deploy_check.sh" || aviso "post_deploy_check acusou problema — leia acima."
}

# ── Escrita idempotente no .env de produção ─────────────────────────────────
definir_flag() {
  local chave="$1" valor="$2" arquivo="$APP_DIR/.env"
  [ -f "$arquivo" ] || erro "$arquivo não existe"
  if grep -qE "^${chave}=" "$arquivo"; then
    local atual; atual="$(grep -E "^${chave}=" "$arquivo" | head -1 | cut -d= -f2-)"
    if [ "$atual" = "$valor" ]; then info "$chave já é $valor — nada a fazer"; return; fi
    sed -i "s|^${chave}=.*|${chave}=${valor}|" "$arquivo"
    info "$chave: $atual → $valor"
  else
    printf '%s=%s\n' "$chave" "$valor" >> "$arquivo"
    info "$chave=$valor (acrescentado)"
  fi
}

# ═════════════════════════ FASE 3 — FLAGS ═══════════════════════════════════
# Religa o que está desligado e NÃO consome memória. Embeddings fica de fora
# de propósito — tem fase própria, porque já derrubou a VPS uma vez.
fase_flags() {
  log "FASE 3 — religar flags leves no $APP_DIR/.env"
  local backup="$APP_DIR/.env.bak.$(date +%Y%m%d%H%M%S)"
  cp -p "$APP_DIR/.env" "$backup" || erro "não consegui fazer backup do .env"
  info "backup do .env em: $backup"

  log "3.1 · Backup diário cifrado (hoje NÃO existe nenhum backup offsite)"
  confirmar "Ligar BACKUP_ENABLED=true"
  definir_flag BACKUP_ENABLED true
  aviso "Exige BACKUP_GOOGLE_DRIVE_* ou BACKUP_RCLONE_REMOTE já configurados."
  aviso "Confira na primeira execução do job: sem credencial ele falha e o painel acusa."

  log "3.2 · Auto-reindexação do RAG"
  info "Desligada em 27/08 como contenção do OOM e nunca religada (AUD27-P1-5)."
  info "Só tem efeito depois da FASE 4; ligar agora é no-op seguro."
  confirmar "Ligar RAG_AUTO_REEMBED_ENABLED=true"
  definir_flag RAG_AUTO_REEMBED_ENABLED true

  log "3.3 · E-mail (hoje NENHUM alerta de prazo sai do sistema)"
  info "Sem isto, quem não abrir o EJC não recebe aviso de prazo, audiência ou"
  info "prescrição — e nem e-mail de reset de senha/2FA."
  printf '\n    Configurar SMTP agora? [s/N]: '; local r; read -r r
  if [ "$r" = "s" ] || [ "$r" = "S" ]; then
    local host porta usuario senha
    printf '    SMTP_HOST [smtp.gmail.com]: '; read -r host; host="${host:-smtp.gmail.com}"
    printf '    SMTP_PORT [587]: ';            read -r porta; porta="${porta:-587}"
    printf '    SMTP_USER: ';                  read -r usuario
    printf '    SMTP_PASSWORD (sem eco): ';    read -rs senha; echo
    [ -n "$usuario" ] && [ -n "$senha" ] || erro "usuário e senha são obrigatórios"
    definir_flag SMTP_HOST "$host"; definir_flag SMTP_PORT "$porta"
    definir_flag SMTP_USER "$usuario"; definir_flag SMTP_PASSWORD "$senha"
    definir_flag EMAIL_ENABLED true
    info "SMTP definido. A senha não aparece em ps, histórico ou log."
  else
    info "SMTP pulado — EMAIL_ENABLED segue como está."
  fi

  log "3.4 · WhatsApp de SAÍDA pela Evolution API já instalada nesta VPS"
  info "O vendor Z-API foi removido e o canal ficou sem remetente. A Evolution"
  info "que já recebe webhook passa a enviar também — sem vendor novo."
  aviso "Exige o backend com o código novo (FASE 2). Antes disso, não ligue."
  printf '\n    Configurar envio por WhatsApp agora? [s/N]: '; read -r r
  if [ "$r" = "s" ] || [ "$r" = "S" ]; then
    local url chave instancia
    printf '    EVOLUTION_API_URL [http://evolution_api:8080]: '; read -r url
    url="${url:-http://evolution_api:8080}"
    printf '    EVOLUTION_INSTANCE [ejc-escritorio]: '; read -r instancia
    instancia="${instancia:-ejc-escritorio}"
    printf '    EVOLUTION_API_KEY (sem eco): '; read -rs chave; echo
    [ -n "$chave" ] || erro "a chave da Evolution é obrigatória"
    definir_flag EVOLUTION_API_URL "$url"
    definir_flag EVOLUTION_INSTANCE "$instancia"
    definir_flag EVOLUTION_API_KEY "$chave"
    definir_flag WHATSAPP_ENABLED true
  else
    info "WhatsApp pulado."
  fi

  log "3.5 · Aplicando (restart do backend)"
  confirmar "Reiniciar o backend para as flags valerem"
  docker restart "$CONTAINER" >/dev/null
  sleep 20
  sondar_api /api/health 30 >/dev/null
  info "Se algo quebrou, restaure: cp $backup $APP_DIR/.env && docker restart $CONTAINER"
}

# ═════════════════════════ FASE 4 — EMBEDDINGS ══════════════════════════════
# A carga mais pesada do sistema. Fase separada de propósito.
fase_embeddings() {
  log "FASE 4 — ligar a busca semântica do RAG"
  aviso "LEIA ANTES. Em 27/08/2026 a reindexação do RAG chegou a 10 GB de"
  aviso "anon-rss e disparou o OOM-killer GLOBAL desta VPS, que reiniciou o"
  aviso "container verdelimp-erp: um trabalho do EJC derrubou o sistema de"
  aviso "OUTRA empresa (AUD27-P1-3/P1-4). Hoje há mem_limit de 6 GB no"
  aviso "container, então o estouro fica contido — mas o EJC pode se derrubar"
  aviso "sozinho em laço se a reindexação for solta sem acompanhamento."
  info ""
  info "São ~47.359 chunks sem vetor. A 1ª carga do modelo ONNX baixa ~1 GB."
  info "Rode isto com a VPS ociosa e alguém olhando — nunca no meio do expediente."

  log "4.1 · Memória livre agora"
  free -h | sed 's/^/   /'
  local livre_mb
  livre_mb="$(free -m | awk '/^Mem:/{print $7}')"
  info "disponível: ${livre_mb} MB"
  if [ "${livre_mb:-0}" -lt 2048 ]; then
    aviso "Menos de 2 GB livres. Reindexar agora convida o OOM. Recomendo adiar."
    confirmar "Seguir MESMO ASSIM com menos de 2 GB livres"
  fi

  log "4.2 · Sonda somente-leitura das flags e do estado real do RAG"
  info "Confere dimensão da coluna, modelo e quantos chunks têm vetor."
  docker exec -i "$CONTAINER" python - < "$ROOT/scripts/check_flags_producao.py" \
    | sed 's/^/   /' || aviso "a sonda acusou problema — leia antes de seguir"

  confirmar "Ligar EMBEDDINGS_ENABLED=true"
  definir_flag EMBEDDINGS_ENABLED true
  # Teto de lote: 16 é o valor que conteve o pico de 27/08. Não aumente sem medir.
  definir_flag EMBEDDINGS_BATCH 16
  docker restart "$CONTAINER" >/dev/null
  sleep 20

  log "4.3 · Reindexação em primeiro plano, sob observação"
  info "Preferir isto a esperar o job horário: aqui você vê o consumo subir e"
  info "pode interromper com Ctrl-C. O script é idempotente — reexecutar retoma."
  confirmar "Rodar a reindexação AGORA, acompanhando"
  info "Em OUTRO terminal, deixe rodando:  docker stats $CONTAINER"
  docker exec -it "$CONTAINER" python -m scripts.reembedar_chunks_orfaos \
    || aviso "reindexação interrompida — reexecute esta fase para retomar de onde parou"

  log "4.4 · Conferência"
  docker exec -i "$CONTAINER" python - < "$ROOT/scripts/check_flags_producao.py" | sed 's/^/   /' || true
  info "Meta: knowledge_chunks_com_embedding == knowledge_chunks_total."
}

case "$ACAO" in
  diagnostico) fase_diagnostico ;;
  destravar)   fase_destravar ;;
  deploy)      fase_deploy ;;
  flags)       fase_flags ;;
  embeddings)  fase_embeddings ;;
esac
