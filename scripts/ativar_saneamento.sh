#!/usr/bin/env bash
# ── scripts/ativar_saneamento.sh ─────────────────────────────────────────────
# Coloca o módulo de saneamento (Issue #1319, migration 154) em produção.
#
# Roda as três tarefas que faltam, na ordem em que dependem uma da outra:
#
#   1. DATAJUD_ENABLED=true no $APP_DIR/.env       (antes do deploy, para o
#      deploy já subir com a flag ligada e poupar um restart)
#   2. deploy manual: --dry-run, PARA para revisão humana, depois implanta
#      (aplica a migration 154)
#   3. chave do DataJud no Cofre de Credenciais    (cifrada, versionada,
#      aplica overlay na mesma requisição — sem restart)
#   4. primeira varredura                          (sem ela o módulo fica
#      permanentemente vazio)
#
# POR QUE UM SCRIPT: o deploy_manual.sh exige que o checkout esteja
# exatamente no SHA alvo e este arquivo vive DENTRO desse checkout — trocar
# de SHA no meio da execução mudaria o script debaixo dos próprios pés. Por
# isso ele se copia para um diretório temporário e se re-executa de lá antes
# de tocar no git (ver reexecutar_fora_do_checkout).
#
# Uso, na VPS, a partir do checkout git (NÃO de /opt/ejc):
#
#   git fetch origin main
#   bash scripts/ativar_saneamento.sh                 # SHA = origin/main
#   bash scripts/ativar_saneamento.sh --sha <commit>  # SHA explícito
#   bash scripts/ativar_saneamento.sh --so-varredura  # só a etapa 4
#
# NADA de segredo em argumento nem em variável de ambiente: e-mail, senha e
# chave do DataJud são lidos do terminal (a senha e a chave sem eco) e nunca
# aparecem em `ps`, no histórico do shell ou em log.
#
# Idempotente: reexecutar não duplica nada. O deploy pula por SHA já
# implantado, o .env não ganha linha repetida e o cofre versiona a chave.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ejc}"
BASE_URL="${EJC_BASE_URL:-https://ejc.depaulateixeira.adv.br}"
TARGET_SHA=""
SO_VARREDURA=0
TIPO_VARREDURA="${TIPO_VARREDURA:-completa}"
LIMITE_DATAJUD="${LIMITE_DATAJUD:-50}"

log()  { printf '\n\033[1m[ativar-saneamento]\033[0m %s\n' "$1"; }
erro() { printf '\n\033[31m[ativar-saneamento] ERRO:\033[0m %s\n' "$1" >&2; exit 1; }

confirmar() {
  # Confirmação explícita antes de cada passo irreversível. Só "sim" segue:
  # um Enter distraído ou um "s" não devem implantar em produção.
  local resposta
  printf '\n>>> %s\n    Digite "sim" para seguir (qualquer outra coisa aborta): ' "$1"
  read -r resposta
  [ "$resposta" = "sim" ] || erro "abortado pelo operador em: $1"
}

usage() {
  sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --sha)           TARGET_SHA="${2:-}"; shift 2 || usage ;;
    --so-varredura)  SO_VARREDURA=1; shift ;;
    -h|--help)       usage ;;
    *)               erro "argumento desconhecido: $1 (use --help)" ;;
  esac
done

# ── Re-execução fora do checkout ─────────────────────────────────────────────
# O passo 2 faz `git checkout` no repositório onde este arquivo mora. Se
# continuássemos executando de lá, o bash leria o resto do script de um
# arquivo que acabou de ser trocado. Copiamos para um tempdir e re-exec.
reexecutar_fora_do_checkout() {
  local copia
  copia="$(mktemp -d)/ativar_saneamento.sh"
  cp "$0" "$copia"
  export ATIVAR_SANEAMENTO_CHECKOUT="$PWD"
  export ATIVAR_SANEAMENTO_REEXEC=1
  exec bash "$copia" ${TARGET_SHA:+--sha "$TARGET_SHA"} $([ "$SO_VARREDURA" = 1 ] && echo --so-varredura)
}

if [ "${ATIVAR_SANEAMENTO_REEXEC:-0}" != "1" ]; then
  git rev-parse --git-dir >/dev/null 2>&1 \
    || erro "rode a partir do checkout git do EJC (não de $APP_DIR)"
  [ "$(cd "$(git rev-parse --show-toplevel)" && pwd)" != "$APP_DIR" ] \
    || erro "este é $APP_DIR (destino do deploy), não o checkout de origem"
  reexecutar_fora_do_checkout
fi

CHECKOUT="${ATIVAR_SANEAMENTO_CHECKOUT:?}"
cd "$CHECKOUT"

# ── Credenciais: lidas do terminal, nunca de argumento ───────────────────────
ler_credenciais() {
  # `|| erro` em cada read: sem isso, stdin fechado (cron, pipe, nohup) faria
  # o set -e abortar em silêncio, sem dizer que o script precisa de terminal.
  [ -t 0 ] || erro "este script é interativo (lê senha do terminal) — rode numa sessão com TTY"
  printf 'E-mail do superadmin: '
  read -r EJC_EMAIL || erro "entrada interrompida ao ler o e-mail"
  [ -n "$EJC_EMAIL" ] || erro "e-mail vazio"
  printf 'Senha (sem eco): '
  read -rs EJC_SENHA || erro "entrada interrompida ao ler a senha"
  echo
  [ -n "$EJC_SENHA" ] || erro "senha vazia"
}

# Extrai um campo do JSON com python3 (já exigido pelo deploy_manual.sh), sem
# depender de jq — que pode não estar instalado.
json_campo() {
  python3 -c '
import json,sys
try:
    d = json.load(sys.stdin)
except Exception as e:
    print(f"__ERRO__ resposta não é JSON: {e}", end=""); sys.exit(0)
v = d.get(sys.argv[1])
print(v if v is not None else f"__ERRO__ {d}", end="")
' "$1"
}

autenticar() {
  log "Autenticando em $BASE_URL"
  local corpo resposta
  # A senha entra via stdin do python3 para não passar por linha de comando.
  corpo="$(EJC_EMAIL="$EJC_EMAIL" EJC_SENHA="$EJC_SENHA" python3 -c '
import json,os
print(json.dumps({"email": os.environ["EJC_EMAIL"], "password": os.environ["EJC_SENHA"]}))')"
  resposta="$(curl -sS -X POST "$BASE_URL/api/auth/login" \
    -H "Content-Type: application/json" --data-binary "$corpo")"
  TOKEN="$(printf '%s' "$resposta" | json_campo access_token)"
  case "$TOKEN" in
    __ERRO__*) erro "login falhou: ${TOKEN#__ERRO__ }" ;;
  esac
  log "Autenticado (token de ${#TOKEN} caracteres)."
}

# ── Tarefa 1: flag do DataJud no .env de produção ────────────────────────────
tarefa_env() {
  log "TAREFA 1/4 — DATAJUD_ENABLED no $APP_DIR/.env"
  sudo -n test -f "$APP_DIR/.env" || erro "$APP_DIR/.env ausente ou sem sudo não interativo"

  if sudo -n grep -q '^DATAJUD_ENABLED=true$' "$APP_DIR/.env"; then
    log "já está true — nada a fazer."
    return
  fi
  confirmar "Ligar DATAJUD_ENABLED=true em $APP_DIR/.env (backup .env.bak-<data> antes)"
  sudo -n cp "$APP_DIR/.env" "$APP_DIR/.env.bak-$(date +%Y%m%d%H%M%S)"
  if sudo -n grep -q '^DATAJUD_ENABLED=' "$APP_DIR/.env"; then
    sudo -n sed -i 's/^DATAJUD_ENABLED=.*/DATAJUD_ENABLED=true/' "$APP_DIR/.env"
  else
    printf 'DATAJUD_ENABLED=true\n' | sudo -n tee -a "$APP_DIR/.env" >/dev/null
  fi
  sudo -n grep -q '^DATAJUD_ENABLED=true$' "$APP_DIR/.env" \
    || erro "não consegui gravar DATAJUD_ENABLED=true"
  log "OK. O deploy a seguir já sobe com a flag ligada (sem restart extra)."
}

# ── Tarefa 2: deploy manual (aplica a migration 154) ─────────────────────────
tarefa_deploy() {
  log "TAREFA 2/4 — deploy manual"
  git fetch origin main
  [ -n "$TARGET_SHA" ] || TARGET_SHA="$(git rev-parse origin/main)"
  git merge-base --is-ancestor "$TARGET_SHA" origin/main \
    || erro "SHA $TARGET_SHA não está integrado à main — o runbook exige SHA da main"

  if sudo -n test -f "$APP_DIR/.deploy_last_sha" \
     && [ "$(sudo -n cat "$APP_DIR/.deploy_last_sha")" = "$TARGET_SHA" ]; then
    log "SHA $TARGET_SHA já implantado — pulando (idempotente)."
    return
  fi

  log "Alvo: $TARGET_SHA"
  git checkout --quiet "$TARGET_SHA"

  log "Pré-voo e classificação da migration (--dry-run: NADA é mutado)"
  bash scripts/deploy_manual.sh --sha "$TARGET_SHA" --dry-run

  cat <<'AVISO'

  ────────────────────────────────────────────────────────────────────────
  LEIA A SAÍDA ACIMA antes de responder. O deploy real só deve seguir se:

    * o pré-voo foi aprovado (sem linhas "PRÉ-VOO:");
    * a migration 154 foi classificada como expand-only / compatível.

  Classificação destrutiva ou pré-voo reprovado => responda qualquer coisa
  menos "sim" e leve a saída para análise. O módulo de saneamento só CRIA
  o schema `saneamento`; nenhuma tabela existente é alterada.
  ────────────────────────────────────────────────────────────────────────
AVISO
  confirmar "Implantar $TARGET_SHA em produção (backup e rollback automáticos pelo script)"
  bash scripts/deploy_manual.sh --sha "$TARGET_SHA"
  log "Deploy concluído."
}

# ── Tarefa 3: chave do DataJud no Cofre de Credenciais ───────────────────────
tarefa_cofre() {
  log "TAREFA 3/4 — chave do DataJud no Cofre de Credenciais"
  local estado
  estado="$(curl -sS "$BASE_URL/api/cofre-credenciais" \
    -H "Authorization: Bearer $TOKEN" \
    | python3 -c '
import json,sys
try:
    for p in json.load(sys.stdin):
        if p.get("provider_key") == "datajud":
            for c in p.get("campos", []):
                if c.get("field_key") == "DATAJUD_API_KEY":
                    print(c.get("estado", "?"), end=""); sys.exit(0)
    print("ausente", end="")
except Exception:
    print("indeterminado", end="")')"

  if [ "$estado" = "configurada" ]; then
    log "já configurada no cofre — pulando. (Para trocar a chave, use a UI:"
    log "Configurações -> Cofre de Credenciais -> DataJud.)"
    return
  fi

  printf '\nChave PÚBLICA do DataJud/CNJ (sem eco).\n'
  printf 'Fonte oficial: https://datajud-wiki.cnj.jus.br/api-publica/acesso/\n'
  printf 'Chave: '
  read -rs DATAJUD_KEY || erro "entrada interrompida ao ler a chave"
  echo
  [ -n "$DATAJUD_KEY" ] || erro "chave vazia"

  local corpo resposta overlay
  corpo="$(DATAJUD_KEY="$DATAJUD_KEY" EJC_SENHA="$EJC_SENHA" python3 -c '
import json,os
print(json.dumps({"valor": os.environ["DATAJUD_KEY"],
                  "senha_atual": os.environ["EJC_SENHA"]}))')"
  resposta="$(curl -sS -X POST \
    "$BASE_URL/api/cofre-credenciais/datajud/DATAJUD_API_KEY" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" --data-binary "$corpo")"
  unset DATAJUD_KEY

  overlay="$(printf '%s' "$resposta" | json_campo overlay_aplicado)"
  case "$overlay" in
    True|true) log "Chave cifrada e aplicada em memória (overlay_aplicado=true)." ;;
    False|false)
      log "AVISO: gravada, mas overlay_aplicado=false — o valor está no banco"
      log "porém ainda não propagado ao processo. O worker de sync reconcilia;"
      log "se a consulta ao DataJud falhar, reexecute esta etapa." ;;
    *) erro "resposta inesperada do cofre: ${overlay#__ERRO__ }" ;;
  esac
}

# ── Tarefa 4: primeira varredura ─────────────────────────────────────────────
tarefa_varredura() {
  log "TAREFA 4/4 — primeira varredura (tipo=$TIPO_VARREDURA, limite_datajud=$LIMITE_DATAJUD)"
  cat <<AVISO

  A varredura le a base real de processos. tipo=dedup nao usa rede;
  datajud/completa consultam o CNJ com rate limit (DATAJUD_RATE_LIMIT_RPS,
  padrao 5 req/s) e no maximo $LIMITE_DATAJUD numeros CNJ nesta execucao.

  A varredura NUNCA decide nada: ela apenas popula as filas de excecao,
  duplicata e indicativo. Fusao de casos e encerramento seguem exigindo
  decisao de advogado, com autor e timestamp gravados no banco.
AVISO
  confirmar "Acionar POST /api/saneamento/varredura"

  local corpo resposta
  corpo="$(TIPO="$TIPO_VARREDURA" LIM="$LIMITE_DATAJUD" python3 -c '
import json,os
print(json.dumps({"tipo": os.environ["TIPO"],
                  "limite_datajud": int(os.environ["LIM"])}))')"
  resposta="$(curl -sS -X POST "$BASE_URL/api/saneamento/varredura" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" --data-binary "$corpo")"

  printf '\n%s\n' "$resposta" | python3 -m json.tool 2>/dev/null \
    || printf '\n%s\n' "$resposta"
  log "Confira 'processados' e 'falhas' de cada execução acima."
  log "As filas ficam em: GET $BASE_URL/api/saneamento/{excecoes,duplicatas,indicativos}"
}

# ── Orquestração ─────────────────────────────────────────────────────────────
log "Módulo de saneamento — ativação em produção"
log "Checkout: $CHECKOUT | Produção: $APP_DIR | API: $BASE_URL"

if [ "$SO_VARREDURA" = "1" ]; then
  ler_credenciais; autenticar; tarefa_varredura
else
  ler_credenciais
  tarefa_env
  tarefa_deploy
  # Autentica DEPOIS do deploy: o restart invalidaria um token obtido antes,
  # e a rota /api/saneamento/varredura só existe no código recém-implantado.
  autenticar
  tarefa_cofre
  tarefa_varredura
fi

unset EJC_SENHA
log "Concluído. Verificação rápida:"
log "  curl -s $BASE_URL/api/saneamento/tpu/cobertura -H \"Authorization: Bearer \$TOKEN\""
log "  sudo cat $APP_DIR/.deploy_last_sha"
