#!/usr/bin/env bash
# ── Deploy manual do EJC, sem GitHub Actions ─────────────────────────────────
#
# POR QUE ESTE SCRIPT EXISTE
#
# O deploy do EJC nunca dependeu tecnicamente do GitHub Actions: o runner está
# instalado DENTRO da VPS e toda a lógica mora em scripts deste repositório
# (`deploy_workflow_transaction.sh` → `deploy_vps_safe.sh`). O Actions é o
# gatilho, não o mecanismo — e `deploy_workflow_transaction.sh` já prevê
# execução fora dele (`RUN_ID="${GITHUB_RUN_ID:-manual}"`).
#
# O problema é que DOIS passos críticos existiam SÓ dentro do YAML do
# `deploy-vps.yml`: o pré-voo e a classificação de migrations. Quem rodasse
# `deploy_vps_safe.sh` na mão pularia os dois — e `RUN_MIGRATIONS` cairia no
# default 0, subindo código novo contra schema antigo, em silêncio.
#
# Este script porta esses dois passos para cá. Ele NÃO afrouxa nenhuma trava:
#   • pré-voo idêntico (workspace confiável, /opt/ejc, ejc_db no ar, sudo -n);
#   • classificação de migration pelo MESMO `check_migration_compatibility.py`,
#     com o mesmo bloqueio quando a migration pendente não é expand-only;
#   • mesma transação sob mutex host-level, com backup pré-deploy OBRIGATÓRIO,
#     health-poll e rollback automático;
#   • mesma idempotência por SHA (`/opt/ejc/.deployed_sha`).
#
# QUANDO USAR: cota do Actions esgotada, incidente na plataforma, ou qualquer
# situação em que a esteira não aloca runner. NÃO é atalho para pular revisão:
# o SHA implantado deve ser um commit já integrado à `main`.
#
# ONDE RODAR: na própria VPS, a partir de um checkout do SHA aprovado, com um
# usuário que tenha `sudo -n` e acesso ao socket do Docker.
#
#   git fetch origin main && git checkout <SHA>
#   bash scripts/deploy_manual.sh --sha <SHA> --dry-run   # confere e não muta
#   bash scripts/deploy_manual.sh --sha <SHA>             # implanta
#
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ejc}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_SHA=""
DRY_RUN=0
RUN_SEEDS="${RUN_SEEDS:-0}"

log()  { printf '[deploy-manual] %s\n' "$*"; }
fail() { printf '[deploy-manual] ERRO: %s\n' "$*" >&2; exit 2; }

usage() {
  cat >&2 <<'USAGE'
uso: deploy_manual.sh --sha <commit> [--dry-run] [--run-seeds]

  --sha <commit>  SHA que se pretende implantar. O checkout atual PRECISA estar
                  exatamente nele — a conferência é o que garante que se
                  implanta o que se pensa estar implantando.
  --dry-run       executa pré-voo e classificação de migration e PARA antes de
                  qualquer mutação. Use sempre na primeira vez.
  --run-seeds     reingere o corpus RAG após o deploy (equivale ao input
                  `run_seeds` do workflow). Default: não.
USAGE
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --sha)        TARGET_SHA="${2:-}"; shift 2 || usage ;;
    --dry-run)    DRY_RUN=1; shift ;;
    --run-seeds)  RUN_SEEDS=1; shift ;;
    -h|--help)    usage ;;
    *)            fail "argumento desconhecido: $1" ;;
  esac
done
[ -n "$TARGET_SHA" ] || usage

cd "$ROOT"

# ── 1. Pré-voo — paridade com o passo homônimo do deploy-vps.yml ─────────────
erros=0
reprovar() { printf '[deploy-manual] PRÉ-VOO: %s\n' "$1" >&2; erros=1; }

dono="$(stat -c %u "$ROOT" 2>/dev/null || echo desconhecido)"
if [ "$dono" = "$(id -u)" ] || [ "$dono" = "0" ]; then
  if head_local="$(git -c safe.directory="$ROOT" rev-parse HEAD 2>&1)"; then
    [ "$head_local" = "$TARGET_SHA" ] ||
      reprovar "checkout está em '$head_local', esperado '$TARGET_SHA'"
  else
    reprovar "git rev-parse HEAD falhou — $head_local"
  fi
else
  reprovar "workspace pertence ao uid '$dono', nem ao usuário atual nem a root"
fi

[ -d "$APP_DIR" ] || reprovar "$APP_DIR não existe ou não é diretório"
[ -f "$APP_DIR/.env" ] || reprovar "$APP_DIR/.env ausente ou ilegível"
docker ps --format '{{.Names}}' 2>/dev/null | grep -qx ejc_db ||
  reprovar "container ejc_db fora do ar, ou sem acesso ao socket do Docker"
command -v python3 >/dev/null || reprovar "python3 ausente no PATH"
command -v rsync   >/dev/null || reprovar "rsync ausente no PATH"
command -v flock   >/dev/null || reprovar "flock ausente no PATH"
command -v sudo    >/dev/null || reprovar "sudo ausente no PATH"
sudo -n true >/dev/null 2>&1 || reprovar "sudo não disponível em modo não interativo"
[ -f scripts/deploy_lock.sh ] || reprovar "scripts/deploy_lock.sh ausente"
[ -f scripts/deploy_workflow_transaction.sh ] || reprovar "scripts/deploy_workflow_transaction.sh ausente"

# Gate de vigência do RAG: se o marker de ativação existe, o .env precisa estar
# canonicamente em true. Mesma checagem do workflow, mesmo motivo — não tocar
# produção com o gate de vigência ambíguo.
activated_marker="$APP_DIR/data/.rag_vigencia_activated_v1"
if sudo -n test -f "$activated_marker"; then
  total="$(sudo -n grep -c '^RAG_EXIGIR_VIGENCIA_VERIFICADA=' "$APP_DIR/.env" || true)"
  verdadeiro="$(sudo -n grep -c '^RAG_EXIGIR_VIGENCIA_VERIFICADA=true$' "$APP_DIR/.env" || true)"
  { [ "$total" = "1" ] && [ "$verdadeiro" = "1" ]; } ||
    reprovar "marker de ativação existe, mas o gate de vigência não está canonicamente true"
fi

[ "$erros" -eq 0 ] || fail "pré-voo reprovado; nada foi tocado em produção"
log "Pré-voo aprovado — HEAD $TARGET_SHA, $APP_DIR e runtime presentes."

# ── 2. Idempotência por SHA ─────────────────────────────────────────────────
ultimo=""
sudo -n test -f "$APP_DIR/.deployed_sha" && ultimo="$(sudo -n cat "$APP_DIR/.deployed_sha")" || true
if [ "$ultimo" = "$TARGET_SHA" ]; then
  log "SHA $TARGET_SHA já implantado no último deploy bem-sucedido; nada a fazer."
  exit 0
fi

# ── 3. Classificação de migrations — o passo que só existia no YAML ─────────
revisoes="$(docker exec ejc_db sh -lc \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atq -c "SELECT version_num FROM alembic_version ORDER BY version_num"' \
  | tr -d '\r')"
quantas="$(printf '%s\n' "$revisoes" | sed '/^$/d' | wc -l | tr -d ' ')"
[ "$quantas" -eq 1 ] || fail "produção deve ter exatamente uma revisão Alembic; encontradas $quantas"
revisao_atual="$(printf '%s\n' "$revisoes" | sed '/^$/d' | head -1)"

politica="$(mktemp)"
trap 'rm -f "$politica"' EXIT
set +e
python3 scripts/check_migration_compatibility.py \
  --versions-dir backend/alembic/versions \
  --current-revision "$revisao_atual" \
  --output "$politica"
rc=$?
set -e
cat "$politica"

[ "$rc" -ne 2 ] || fail "grafo Alembic inválido ou revisão atual desconhecida"
[ "$rc" -ne 1 ] || fail "migration pendente NÃO é expand-only; deploy bloqueado (mesma regra do workflow)"

pendentes="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pending_count"])' "$politica")"
if [ "$pendentes" -gt 0 ]; then
  RUN_MIGRATIONS=1; MIGRATIONS_BACKWARD_COMPATIBLE=1
else
  RUN_MIGRATIONS=0; MIGRATIONS_BACKWARD_COMPATIBLE=0
fi
log "Revisão em produção: $revisao_atual · migrations pendentes: $pendentes · RUN_MIGRATIONS=$RUN_MIGRATIONS"

if [ "$DRY_RUN" = "1" ]; then
  log "--dry-run: parando aqui. NADA foi mutado em produção."
  exit 0
fi

# ── 4. Transação mutável, idêntica à do workflow ────────────────────────────
# RUNNER_TEMP é exigido por deploy_workflow_transaction.sh para guardar o
# arquivo de fase; fora do Actions ele não existe, então criamos um.
if [ -z "${RUNNER_TEMP:-}" ]; then
  RUNNER_TEMP="$(mktemp -d)"
  trap 'rm -f "$politica"; rm -rf "$RUNNER_TEMP"' EXIT
fi

log "Iniciando transação sob mutex host-level (backup obrigatório, health e rollback ativos)."
TARGET_SHA="$TARGET_SHA" \
RUNNER_TEMP="$RUNNER_TEMP" \
RUN_MIGRATIONS="$RUN_MIGRATIONS" \
MIGRATIONS_BACKWARD_COMPATIBLE="$MIGRATIONS_BACKWARD_COMPATIBLE" \
RUN_SEEDS="$RUN_SEEDS" \
REQUIRE_PREDEPLOY_BACKUP=1 \
  bash scripts/deploy_workflow_transaction.sh

# ── 5. Verificação pós-deploy ───────────────────────────────────────────────
curl -fsS http://127.0.0.1:8000/api/health >/dev/null ||
  fail "health local reprovou APÓS o deploy — confira o rollback automático"
log "Health local OK. Deploy manual do SHA $TARGET_SHA concluído."
