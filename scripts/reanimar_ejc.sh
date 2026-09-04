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
# ONDE RODAR: na VPS, a partir de um CHECKOUT GIT do repositório (NÃO de dentro
# de /opt/ejc). As fases que editam o .env de produção exigem ROOT — elas leem
# e escrevem $APP_DIR/.env diretamente e conferem a permissão antes de agir.
#
#     git fetch origin main && git checkout origin/main
#     bash scripts/reanimar_ejc.sh --diagnostico      # só lê, não muta NADA
#     bash scripts/reanimar_ejc.sh --destravar        # fase 1
#     bash scripts/reanimar_ejc.sh --deploy <SHA>     # fase 2
#     bash scripts/reanimar_ejc.sh --ligar-tudo       # fase 3 — RELIGA TUDO
#     bash scripts/reanimar_ejc.sh --embeddings       # fase 4 (a mais pesada)
#
# `--ligar-tudo` religa, de uma vez, tudo que deve ser religado, e diz o motivo
# do que NÃO religa. Três gates ficam de fora por padrão porque ligá-los cria
# passivo jurídico ou violação de licença — `--assumir-riscos` liga também.
# `--flags` continua existindo como subconjunto conservador de `--ligar-tudo`.
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

ASSUMIR_RISCOS=0

while [ $# -gt 0 ]; do
  case "$1" in
    --diagnostico|--destravar|--flags|--embeddings|--ligar-tudo) ACAO="${1#--}"; shift ;;
    --deploy) ACAO="deploy"; TARGET_SHA="${2:-}"; shift 2 || usage ;;
    --assumir-riscos) ASSUMIR_RISCOS=1; shift ;;
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

# As fases que editam o .env de produção leem e escrevem $APP_DIR/.env
# DIRETAMENTE, sem passar por sudo. O cabeçalho antes dizia que um operador
# não-root com `sudo -n` bastava — não basta: ele satisfaz a precondição
# documentada, consegue rodar o deploy_manual.sh e falha na primeira cópia do
# .env, no meio do religamento. Em vez de espalhar sudo por cada operação de
# arquivo (mais superfície, mais chance de erro), a exigência fica EXPLÍCITA e
# é conferida antes de qualquer trabalho. Achado da revisão do PR.
exigir_acesso_ao_env() {
  [ -f "$APP_DIR/.env" ] || erro "$APP_DIR/.env não existe — ambiente não provisionado?"
  if [ ! -r "$APP_DIR/.env" ] || [ ! -w "$APP_DIR/.env" ]; then
    erro "sem permissão de leitura/escrita em $APP_DIR/.env (usuário atual: $(id -un)).
    Esta fase precisa rodar como root:  sudo bash scripts/reanimar_ejc.sh $*"
  fi
}

# ── Sondagem HTTP: separa "nginx não alcança" de "backend não responde" ──────
# A linha legível vai para STDERR e SÓ o código sai em stdout. A versão
# anterior imprimia as duas no mesmo stdout, então `c="$(sondar_api ...)"`
# capturava o diagnóstico JUNTO com o código: `interpretar_sonda` recebia um
# valor multilinha e caía sempre no ramo "código inesperado", inclusive quando
# o backend respondia 200. Achado da revisão do PR.
sondar_api() {
  local caminho="$1" limite="${2:-20}" saida codigo
  # Sem `|| echo`: em falha o curl já imprime `000` por causa do -w; acrescentar
  # outro valor produziria `000000` (o mesmo defeito estava em monitor_health).
  saida="$(curl -sS -o /dev/null -m "$limite" \
            -w '%{http_code} %{time_total}' "${BASE_URL}${caminho}" 2>/dev/null || true)"
  [ -n "$saida" ] || saida="000 (sem resposta em ${limite}s)"
  printf '   %-22s → HTTP %s\n' "$caminho" "$saida" >&2
  codigo="$(printf '%s' "$saida" | awk '{print $1}')"
  echo "${codigo:-000}"
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

  # O alvo PRECISA estar integrado à main. `git checkout <sha>` aceita qualquer
  # commit já presente no checkout — inclusive um commit de feature que nunca
  # foi revisado — e o deploy_manual.sh só confere que o HEAD bate com o SHA
  # pedido, não a procedência dele. Sem esta trava, "--deploy <sha>" implanta
  # código não revisado em produção com uma confirmação genérica.
  # `merge-base --is-ancestor` aceita commit ANTIGO da main (rollback continua
  # possível) e recusa qualquer coisa fora dela. Achado da revisão do PR.
  if ! git -C "$ROOT" merge-base --is-ancestor "$TARGET_SHA" origin/main 2>/dev/null; then
    erro "$TARGET_SHA não é ancestral de origin/main — recuso implantar código
    não integrado. Se o objetivo é rollback, use um commit que ESTEVE na main.
    Se é código novo, mescle o PR primeiro."
  fi
  info "✅ $TARGET_SHA confirmado como ancestral de origin/main"

  git -C "$ROOT" checkout -q "$TARGET_SHA" || erro "checkout de $TARGET_SHA falhou"

  log "2.1 · Ensaio (--dry-run): confere tudo e NÃO muta produção"
  bash "$ROOT/scripts/deploy_manual.sh" --sha "$TARGET_SHA" --dry-run

  aviso "O ensaio acima passou. A implantação real aplica ~29 migrations pendentes."
  aviso "Se a classificação de migration acusou algo NÃO expand-only, PARE e me chame."
  confirmar "Implantar $TARGET_SHA em produção AGORA"

  bash "$ROOT/scripts/deploy_manual.sh" --sha "$TARGET_SHA"

  log "2.2 · Verificação pós-deploy"
  # Falha aqui é FALHA da fase. A versão anterior usava `|| aviso`, que
  # convertia qualquer reprovação do post_deploy_check (readiness, rotas
  # externas, containers, login, compilação de módulo crítico) em saída zero —
  # um operador de incidente, ou uma automação, leria "deploy concluído" sobre
  # uma produção parcialmente quebrada. Achado da revisão do PR.
  if ! bash "$ROOT/scripts/post_deploy_check.sh"; then
    erro "post_deploy_check REPROVOU — a produção NÃO está validada. Leia a saída
    acima, corrija, e rode a verificação de novo:
        bash scripts/post_deploy_check.sh
    O deploy_manual.sh já tem rollback próprio; se ele não disparou, o código
    novo está no ar e reprovando a checagem."
  fi
  info "✅ verificação pós-deploy aprovada."
}

# ── Escrita idempotente no .env de produção ─────────────────────────────────
# Nomes cujo VALOR nunca pode ser impresso: senha, chave, token, segredo.
# A revisão do PR pegou a versão anterior imprimindo `$atual → $valor` para
# SMTP_PASSWORD, EVOLUTION_API_KEY, DATAJUD_API_KEY e VAPID_PRIVATE_KEY — ou
# seja, rodar a recuperação despejava credencial no terminal e em qualquer log
# de incidente capturado. Aqui só o NOME da chave e o fato de ter mudado saem.
_e_segredo() {
  case "$1" in
    *PASSWORD*|*SENHA*|*SECRET*|*_KEY|*_KEYS|*APIKEY*|*API_KEY*|*TOKEN*|*DSN*) return 0 ;;
    *) return 1 ;;
  esac
}

definir_flag() {
  local chave="$1" valor="$2" arquivo="$APP_DIR/.env"
  [ -f "$arquivo" ] || erro "$arquivo não existe"

  local mostrado="$valor"
  if _e_segredo "$chave"; then mostrado="(valor não exibido)"; fi

  local atual="" existe=0
  if grep -qE "^${chave}=" "$arquivo"; then
    existe=1
    atual="$(grep -E "^${chave}=" "$arquivo" | head -1 | cut -d= -f2-)"
    if [ "$atual" = "$valor" ]; then
      info "$chave já está no valor desejado — nada a fazer"
      return
    fi
  fi

  # Escrita LITERAL. A versão anterior usava `sed -i "s|^K=.*|K=$valor|"`, que
  # interpreta o valor como programa sed: `&` vira a linha inteira casada, `\`
  # escapa, e `|` encerra a expressão. Senha de SMTP e chave de API contêm
  # esses caracteres com frequência — o resultado seria credencial corrompida
  # em produção, ou o script abortando no meio do religamento.
  # awk compara por prefixo exato (sem regex) e recebe chave/valor por ambiente,
  # então nada no valor é interpretado.
  local tmp
  tmp="$(mktemp "${TMPDIR:-/tmp}/ejc-env.XXXXXX")" || erro "mktemp falhou"
  chmod 600 "$tmp" 2>/dev/null || true
  if ! EJC_CHAVE="$chave" EJC_VALOR="$valor" awk '
        BEGIN { k = ENVIRON["EJC_CHAVE"]; v = ENVIRON["EJC_VALOR"]; achou = 0 }
        substr($0, 1, length(k) + 1) == k "=" { if (!achou) { print k "=" v; achou = 1 }; next }
        { print }
        END { if (!achou) print k "=" v }
      ' "$arquivo" > "$tmp"; then
    rm -f "$tmp"; erro "falha ao reescrever $arquivo (nada foi alterado)"
  fi
  # `cat >` em vez de `mv`: preserva inode, dono e permissões do .env original.
  cat "$tmp" > "$arquivo" || { rm -f "$tmp"; erro "falha ao gravar $arquivo"; }
  rm -f "$tmp"

  if [ "$existe" = "1" ]; then
    info "$chave alterado → $mostrado"
  else
    info "$chave=$mostrado (acrescentado)"
  fi
}

# ── Aplicar mudança de .env: RECRIAR, não reiniciar ─────────────────────────
# O Docker fixa o ambiente de um container no momento da CRIAÇÃO. `docker
# restart` reinicia o processo dentro do container existente e NÃO relê o
# `env_file` do Compose. A versão anterior deste script usava `docker restart`
# depois de editar o .env — ou seja, gravava tudo certo e não ligava NADA, com
# o agravante de parecer ter funcionado. Achado da revisão do PR.
aplicar_env() {
  log "Aplicando o .env (recriando backend e worker — restart não relê env_file)"
  if ! (cd "$APP_DIR" && docker compose up -d --no-deps --force-recreate backend worker); then
    aviso "recriação via compose falhou; tentando só o backend"
    (cd "$APP_DIR" && docker compose up -d --no-deps --force-recreate backend) \
      || erro "não consegui recriar os serviços — o .env NÃO está em vigor"
  fi
}

# Espera o backend responder 200 e devolve não-zero se não responder.
aguardar_saudavel() {
  local tentativas="${1:-20}" i codigo=""
  for i in $(seq 1 "$tentativas"); do
    sleep 5
    codigo="$(curl -sS -o /dev/null -m 10 -w '%{http_code}' "${BASE_URL}/api/health" 2>/dev/null || true)"
    codigo="${codigo:-000}"
    printf '   tentativa %2d/%d → HTTP %s\n' "$i" "$tentativas" "$codigo" >&2
    [ "$codigo" = "200" ] && { echo 200; return 0; }
  done
  echo "${codigo:-000}"
  return 1
}

# ═════════════════════════ FASE 3 — FLAGS ═══════════════════════════════════
# Religa o que está desligado e NÃO consome memória. Embeddings fica de fora
# de propósito — tem fase própria, porque já derrubou a VPS uma vez.
fase_flags() {
  exigir_acesso_ao_env
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

  log "3.5 · Aplicando"
  confirmar "Recriar backend e worker para as flags valerem"
  aplicar_env
  # Resultado CONFERIDO, não descartado: a versão anterior sondava e jogava o
  # código fora, então a fase saía com status 0 mesmo com o backend em 500/504.
  if ! aguardar_saudavel 20 >/dev/null; then
    aviso "Backend NÃO respondeu 200 após aplicar as flags. Restaurando o .env."
    cat "$backup" > "$APP_DIR/.env" && aplicar_env
    erro "flags revertidas — investigue o log antes de tentar de novo"
  fi
  info "✅ backend saudável com as flags novas."
  info "Reverter mesmo assim: cat $backup > $APP_DIR/.env && (cd $APP_DIR && docker compose up -d --no-deps --force-recreate backend worker)"
}

# ═════════════════════════ FASE 4 — EMBEDDINGS ══════════════════════════════
# A carga mais pesada do sistema. Fase separada de propósito.
fase_embeddings() {
  exigir_acesso_ao_env
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
  # Recriar, não reiniciar: sem isto o container seguiria com
  # EMBEDDINGS_ENABLED=false e a reindexação abortaria sem processar nada.
  aplicar_env
  aguardar_saudavel 20 >/dev/null \
    || erro "backend não voltou saudável — não vou reindexar contra um sistema quebrado"

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

# ═══════════════════ LIGAR TUDO — o que deve mesmo ser ligado ═══════════════
#
# "Ligar tudo" literalmente é a instrução errada, e vale dizer por quê antes de
# executar: parte do que está desligado NÃO é desleixo, é contenção deliberada.
# Três desses gates, se ligados, criam passivo jurídico ou de licença — e um
# sistema que emite documento com cálculo não homologado não é "200% operante",
# é 200% exposto.
#
# Esta fase divide o mundo em quatro:
#   A. liga sozinho, sem credencial nenhuma;
#   B. liga assim que você digitar a credencial (é AQUI que está a maior parte
#      do que falta — é tarefa de credencial, não de código);
#   C. pesado, fase própria (--embeddings);
#   D. não liga sem decisão sua, com o motivo escrito.
fase_ligar_tudo() {
  exigir_acesso_ao_env
  log "LIGAR TUDO — religando o que deve ser religado"
  local backup="$APP_DIR/.env.bak.$(date +%Y%m%d%H%M%S)"
  cp -p "$APP_DIR/.env" "$backup" || erro "não consegui fazer backup do .env"
  info "backup do .env em: $backup"
  info "reverter tudo: cat $backup > $APP_DIR/.env && (cd $APP_DIR && docker compose up -d --no-deps --force-recreate backend worker)"

  # ── GRUPO A — sem credencial externa ──────────────────────────────────────
  log "GRUPO A · Liga agora, sem depender de ninguém"

  info "Push (PWA): as chaves VAPID são geradas localmente — não há vendor."
  if grep -qE '^VAPID_PUBLIC_KEY=.+' "$APP_DIR/.env"; then
    info "VAPID já configurada — mantendo a chave existente (trocar derruba as"
    info "inscrições já feitas nos navegadores)."
    definir_flag PUSH_ENABLED true
  else
    local vapid
    if vapid="$(docker exec -i "$CONTAINER" python - < "$ROOT/scripts/gen_vapid.py" 2>/dev/null)"; then
      local pub priv
      pub="$(echo "$vapid"  | grep '^VAPID_PUBLIC_KEY='  | cut -d= -f2-)"
      priv="$(echo "$vapid" | grep '^VAPID_PRIVATE_KEY=' | cut -d= -f2-)"
      if [ -n "$pub" ] && [ -n "$priv" ]; then
        definir_flag VAPID_PUBLIC_KEY "$pub"
        definir_flag VAPID_PRIVATE_KEY "$priv"
        definir_flag PUSH_ENABLED true
        info "chaves VAPID geradas e gravadas (a privada não é impressa aqui)."
      else
        aviso "gen_vapid não devolveu o par esperado — PUSH segue desligado."
      fi
    else
      aviso "não consegui rodar gen_vapid no container — PUSH segue desligado."
    fi
  fi

  info "Cache de resposta de IA e rate limit distribuído: o Redis já sobe neste"
  info "stack; ambos degradam sozinhos se ele cair."
  definir_flag AI_RESPONSE_CACHE_ENABLED true
  definir_flag RATE_LIMIT_REDIS_ENABLED true

  info "Qualidade da peça: autocrítica adversarial e pesquisa por questão."
  info "Custam tokens a mais e melhoram a minuta — nenhum risco jurídico."
  definir_flag PECAS_AUTOCRITICA_ENABLED true
  definir_flag PECAS_PESQUISA_QUESTOES_ENABLED true

  info "Auto-reindexação do RAG (só tem efeito após a fase --embeddings)."
  definir_flag RAG_AUTO_REEMBED_ENABLED true

  info "Busca web de verificação: usa a chave Anthropic que já existe e só é"
  info "anexada a chamadas que JÁ passaram pela sanitização do gateway."
  definir_flag AI_WEB_SEARCH_ENABLED true

  # ── GRUPO B — depende de credencial que só você tem ───────────────────────
  log "GRUPO B · Depende de credencial — é aqui que mora a maior parte do que falta"
  info "Cada item abaixo é uma pergunta. Enter em branco = pula e segue."

  printf '\n  [1/4] SMTP — sem isto NENHUM alerta de prazo sai por e-mail,\n'
  printf '        e nem o e-mail de reset de senha/2FA.\n'
  printf '        Configurar? [s/N]: '; local r; read -r r
  if [ "$r" = "s" ] || [ "$r" = "S" ]; then
    local host porta usuario senha
    printf '    SMTP_HOST [smtp.gmail.com]: '; read -r host; host="${host:-smtp.gmail.com}"
    printf '    SMTP_PORT [587]: ';            read -r porta; porta="${porta:-587}"
    printf '    SMTP_USER: ';                  read -r usuario
    printf '    SMTP_PASSWORD (sem eco): ';    read -rs senha; echo
    if [ -n "$usuario" ] && [ -n "$senha" ]; then
      definir_flag SMTP_HOST "$host";     definir_flag SMTP_PORT "$porta"
      definir_flag SMTP_USER "$usuario";  definir_flag SMTP_PASSWORD "$senha"
      definir_flag EMAIL_ENABLED true
      definir_flag RELATORIO_DONO_ENABLED true
      info "e-mail ligado; relatório semanal do dono ligado junto (depende dele)."
    else
      aviso "usuário/senha vazios — e-mail segue desligado."
    fi
  fi

  printf '\n  [2/4] WhatsApp pela Evolution API (já instalada nesta VPS).\n'
  printf '        Configurar? [s/N]: '; read -r r
  if [ "$r" = "s" ] || [ "$r" = "S" ]; then
    local url chave instancia
    printf '    EVOLUTION_API_URL [http://evolution_api:8080]: '; read -r url
    url="${url:-http://evolution_api:8080}"
    printf '    EVOLUTION_INSTANCE [ejc-escritorio]: '; read -r instancia
    instancia="${instancia:-ejc-escritorio}"
    printf '    EVOLUTION_API_KEY (sem eco): '; read -rs chave; echo
    if [ -n "$chave" ]; then
      definir_flag EVOLUTION_API_URL "$url"
      definir_flag EVOLUTION_INSTANCE "$instancia"
      definir_flag EVOLUTION_API_KEY "$chave"
      definir_flag WHATSAPP_ENABLED true
    else
      aviso "chave vazia — WhatsApp segue desligado."
    fi
  fi

  printf '\n  [3/4] Backup diário cifrado. HOJE NÃO EXISTE NENHUM BACKUP OFFSITE.\n'
  printf '        Exige BACKUP_GOOGLE_DRIVE_* ou BACKUP_RCLONE_REMOTE já configurados.\n'
  printf '        Ligar BACKUP_ENABLED? [s/N]: '; read -r r
  if [ "$r" = "s" ] || [ "$r" = "S" ]; then
    definir_flag BACKUP_ENABLED true
    aviso "Confira a PRIMEIRA execução do job: sem credencial ele falha, e agora"
    aviso "o painel acusa (antes registrava 'ok' para backup que não aconteceu)."
  fi

  printf '\n  [4/4] DataJud/CNJ — sem isto a movimentação processual NUNCA atualiza\n'
  printf '        e o cliente não recebe aviso de andamento novo.\n'
  printf '        Tem a chave da API pública do CNJ? [s/N]: '; read -r r
  if [ "$r" = "s" ] || [ "$r" = "S" ]; then
    local dj
    printf '    DATAJUD_API_KEY (sem eco): '; read -rs dj; echo
    if [ -n "$dj" ]; then
      definir_flag DATAJUD_API_KEY "$dj"
      definir_flag DATAJUD_ENABLED true
      definir_flag DATAJUD_SYNC_ENABLED true
      definir_flag AI_GROUNDING_DATAJUD_ENABLED true
      info "DataJud ligado: consulta, sync diário e grounding de IA."
    else
      aviso "chave vazia — DataJud segue desligado."
    fi
  fi

  # ── GRUPO D — decisão sua, com o motivo na mesa ───────────────────────────
  log "GRUPO D · NÃO ligados — cada um com o motivo"

  printf '\n  • PECAS_DEMONSTRATIVO_CALCULADORA_ENABLED — MANTIDO DESLIGADO.\n'
  printf '    As regras das calculadoras não foram homologadas (fonte/vigência/\n'
  printf '    revisor). Ligar faz o sistema emitir DOCUMENTO com aparência\n'
  printf '    oficial sobre cálculo possivelmente errado, que circula fora do\n'
  printf '    escritório. É passivo jurídico, não funcionalidade.\n'
  printf '  • RAG_RERANK_ENABLED — MANTIDO DESLIGADO.\n'
  printf '    O único reranker multilíngue suportado nesta versão tem licença\n'
  printf '    CC-BY-NC-4.0: uso comercial é violação de licença. Ligar num\n'
  printf '    escritório de advocacia é infração, não melhoria.\n'
  printf '  • AI_AGENT_ENABLED — MANTIDO DESLIGADO.\n'
  printf '    Libera write-tools da IA (criar prazo fatal, nota, kit documental)\n'
  printf '    antes da homologação do HITL. IA gravando prazo sozinha é o risco\n'
  printf '    que o sistema inteiro existe para evitar.\n'
  if [ "$ASSUMIR_RISCOS" = "1" ]; then
    aviso "--assumir-riscos presente: os TRÊS acima serão ligados."
    confirmar "Ligar os três gates de risco jurídico/licença acima"
    definir_flag PECAS_DEMONSTRATIVO_CALCULADORA_ENABLED true
    definir_flag RAG_RERANK_ENABLED true
    definir_flag AI_AGENT_ENABLED true
  else
    info "Para ligá-los mesmo assim: reexecute com --assumir-riscos."
  fi

  printf '\n  Decisões de negócio (pergunto, não decido por você):\n'
  printf '  • Régua de cobrança AUTOMÁTICA ao cliente (d-3/d+1/d+7/d+15 +\n'
  printf '    escalada). Manda mensagem ao seu cliente sem ninguém revisar.\n'
  printf '    Ligar? [s/N]: '; read -r r
  if [ "$r" = "s" ] || [ "$r" = "S" ]; then definir_flag COBRANCA_ENABLED true; else info "COBRANCA_ENABLED mantido desligado."; fi

  # Portão PRÓPRIO de backup: este é o único item da fase que destrói dado.
  # O backup do .env feito no começo não recupera rascunho nem upload apagado,
  # e o operador pode ter acabado de PULAR a configuração de backup logo acima.
  # Achado da revisão do PR: habilitar isto sem prova de restauração testada é
  # ligar um hard delete agendado sem rede de segurança.
  printf '  • Expurgo LGPD da Entrada Única — apaga rascunho abandonado.\n'
  printf '    HARD DELETE IRREVERSÍVEL, agendado para 03:50 todo dia. Não fazê-lo\n'
  printf '    é passivo LGPD; fazê-lo sem backup restaurável é perda de dado.\n'
  printf '    Ligar? [s/N]: '; read -r r
  if [ "$r" = "s" ] || [ "$r" = "S" ]; then
    printf '\n    Antes de ligar, responda com honestidade:\n'
    printf '    Existe backup RECENTE do banco e dos uploads, e a restauração\n'
    printf '    dele já foi TESTADA (não apenas gerada)?\n'
    printf '    Digite "restauracao-testada" para confirmar: '
    local prova; read -r prova
    if [ "$prova" = "restauracao-testada" ]; then
      definir_flag ENTRADA_EXPURGO_ENABLED true
      info "expurgo ligado — a primeira execução é às 03:50."
      aviso "Confira o resultado da PRIMEIRA execução no painel de jobs antes de"
      aviso "considerar o expurgo estabilizado."
    else
      info "sem confirmação de restauração testada — ENTRADA_EXPURGO_ENABLED mantido desligado."
      info "Rode scripts/backup.sh, teste o restore, e reexecute esta fase."
    fi
  else
    info "ENTRADA_EXPURGO_ENABLED mantido desligado."
  fi

  printf '  • Verificação de PERTINÊNCIA da citação (confere se a autoridade\n'
  printf '    citada SUSTENTA a tese, não só se existe). Custa uma chamada de IA\n'
  printf '    por citação. O código pede base de legislação/súmulas abrangente\n'
  printf '    antes — o que só se resolve depois da fase --embeddings.\n'
  printf '    Ligar? [s/N]: '; read -r r
  if [ "$r" = "s" ] || [ "$r" = "S" ]; then definir_flag PERTINENCIA_ENABLED true; else info "PERTINENCIA_ENABLED mantido desligado."; fi

  printf '  • Transcrição de áudio/vídeo (envia mídia a provedor externo).\n'
  printf '    Ligar? [s/N]: '; read -r r
  if [ "$r" = "s" ] || [ "$r" = "S" ]; then definir_flag AUDIO_TRANSCRIPTION_ENABLED true; else info "AUDIO_TRANSCRIPTION_ENABLED mantido desligado."; fi

  log "Aplicando"
  confirmar "Recriar backend e worker para tudo isto valer"
  aplicar_env
  local codigo
  if ! codigo="$(aguardar_saudavel 20)"; then
    interpretar_sonda "$codigo"
    aviso "Backend NÃO respondeu 200 após o religamento. Restaurando o .env."
    cat "$backup" > "$APP_DIR/.env" && aplicar_env
    erro "religamento revertido — investigue o log antes de tentar de novo"
  fi
  info "✅ backend saudável com tudo religado."

  log "Conferência final — flags EFETIVAS dentro do processo"
  docker exec -i "$CONTAINER" python - < "$ROOT/scripts/check_flags_producao.py" | sed 's/^/   /' || true

  log "FALTA AINDA: bash scripts/reanimar_ejc.sh --embeddings"
  info "É a única peça pesada, e a que faz a busca semântica do RAG sair do zero."
  info "Reverter tudo desta fase: cat $backup > $APP_DIR/.env && (cd $APP_DIR && docker compose up -d --no-deps --force-recreate backend worker)"
}

case "$ACAO" in
  diagnostico) fase_diagnostico ;;
  ligar-tudo)  fase_ligar_tudo ;;
  destravar)   fase_destravar ;;
  deploy)      fase_deploy ;;
  flags)       fase_flags ;;
  embeddings)  fase_embeddings ;;
esac
