#!/usr/bin/env bash
# =============================================================================
#  levantamento-pr-p0.sh
#  Coleta a evidencia bruta de um conjunto de PRs abertos e gera:
#    - evidencias/                              saida crua de cada comando (auditavel)
#    - docs/MATRIZ_CONSOLIDACAO_P0_GERADA.md    matriz preenchida com DADOS REAIS
#
#  Este script NAO decide nada. Ele coleta. As colunas de julgamento
#  (correcoes exclusivas, duplicadas, recomendacao) permanecem vazias e
#  exigem analise humana ou do agente sobre a evidencia coletada.
#
#  Uso:
#    bash scripts/governanca/levantamento-pr-p0.sh                  # usa 493 494 495 496 497
#    bash scripts/governanca/levantamento-pr-p0.sh 493 497 501      # PRs especificos
#    EJC_MATRIZ=docs/OUTRA.md bash scripts/governanca/levantamento-pr-p0.sh
#    bash scripts/governanca/levantamento-pr-p0.sh --forcar 493     # sobrescreve matriz existente
#
#  Somente leitura sobre o repositorio: nao cria branch, nao altera codigo,
#  nao faz checkout. Escreve apenas em evidencias/ e no arquivo de matriz.
#
#  ATENCAO: docs/MATRIZ_CONSOLIDACAO_P0.md ja existe e contem analise humana
#  de 2026-07-27. Por isso o destino padrao e um arquivo distinto e o script
#  recusa sobrescrever arquivo existente sem --forcar.
# =============================================================================
set -euo pipefail

FORCAR=0
PRS=()
for ARG in "$@"; do
  case "$ARG" in
    --forcar) FORCAR=1 ;;
    *) PRS+=("$ARG") ;;
  esac
done
[ ${#PRS[@]} -eq 0 ] && PRS=(493 494 495 496 497)

OUT="evidencias"
MATRIZ="${EJC_MATRIZ:-docs/MATRIZ_CONSOLIDACAO_P0_GERADA.md}"
DATA="$(date +%Y-%m-%d)"

falhar() { echo ""; echo "ABORTADO: $1"; exit 1; }

command -v gh >/dev/null 2>&1 || falhar "GitHub CLI (gh) nao encontrado."
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || falhar "execute na raiz do repositorio."
cd "$(git rev-parse --show-toplevel)"

if [ -e "$MATRIZ" ] && [ "$FORCAR" -eq 0 ]; then
  falhar "$MATRIZ ja existe. Use --forcar para sobrescrever ou defina EJC_MATRIZ para outro destino."
fi

mkdir -p "$OUT" docs
echo "Coletando evidencia dos PRs: ${PRS[*]}"
echo "Matriz de destino: $MATRIZ"
echo ""

# --- 1. Inventario geral --------------------------------------------------
gh pr list --state open --limit 100 \
  --json number,title,headRefName,isDraft,additions,deletions,changedFiles \
  > "$OUT/00-inventario.json"
echo "  [->] $OUT/00-inventario.json"

git fetch --quiet origin || true

# --- 2. Por PR ------------------------------------------------------------
for N in "${PRS[@]}"; do
  if ! gh pr view "$N" --json number >/dev/null 2>&1; then
    echo "  [!!] PR $N inacessivel ou inexistente — registrado como ausente"
    echo "{\"numero\":$N,\"estado\":\"inacessivel\"}" > "$OUT/pr-$N.json"
    continue
  fi
  gh pr view "$N" --json number,title,headRefName,baseRefName,isDraft,state,additions,deletions,changedFiles,files,commits,body \
    > "$OUT/pr-$N.json"
  # linha TSV: titulo \t branch \t draft \t arquivos \t adicoes \t remocoes
  gh pr view "$N" --json title,headRefName,isDraft,changedFiles,additions,deletions \
    --jq '[.title, .headRefName, (if .isDraft then "sim" else "nao" end), (.changedFiles|tostring), (.additions|tostring), (.deletions|tostring)] | @tsv' \
    > "$OUT/pr-$N.tsv" 2>/dev/null || true
  gh pr diff "$N" --name-only > "$OUT/pr-$N.files.txt" 2>/dev/null || true
  gh pr diff "$N" > "$OUT/pr-$N.diff" 2>/dev/null || true
  # Caminho real das migrations no EJC: backend/alembic/versions/
  grep -E '^backend/alembic/versions/' "$OUT/pr-$N.files.txt" > "$OUT/pr-$N.migrations.txt" 2>/dev/null || true
  grep -Ei '(^|/)(test_|tests?/|.*\.test\.|.*\.spec\.)' "$OUT/pr-$N.files.txt" > "$OUT/pr-$N.testes.txt" 2>/dev/null || true
  echo "  [->] PR $N coletado ($(wc -l < "$OUT/pr-$N.files.txt" 2>/dev/null || echo 0) arquivos)"
done

# --- 3. Matriz de sobreposicao par a par ----------------------------------
{
  echo "# Sobreposicao de arquivos entre PRs"
  echo ""
  for A in "${PRS[@]}"; do
    for B in "${PRS[@]}"; do
      [ "$A" -ge "$B" ] && continue
      [ -f "$OUT/pr-$A.files.txt" ] && [ -f "$OUT/pr-$B.files.txt" ] || continue
      COMUNS="$(comm -12 <(sort -u "$OUT/pr-$A.files.txt") <(sort -u "$OUT/pr-$B.files.txt"))"
      QTD="$(echo "$COMUNS" | grep -c . || true)"
      echo "## PR $A x PR $B — $QTD arquivo(s) em comum"
      if [ "$QTD" -gt 0 ]; then
        echo '```'
        echo "$COMUNS"
        echo '```'
      fi
      echo ""
    done
  done
} > "$OUT/10-sobreposicao.md"
echo "  [->] $OUT/10-sobreposicao.md"

# --- 4. Conflito real contra main -----------------------------------------
{
  echo "# Teste de merge contra origin/main (somente leitura, sem commit)"
  echo ""
  for N in "${PRS[@]}"; do
    BR="$(cut -f2 "$OUT/pr-$N.tsv" 2>/dev/null || true)"
    [ -z "$BR" ] && { echo "- PR $N: branch nao identificada"; continue; }
    if git merge-tree "$(git merge-base origin/main "origin/$BR" 2>/dev/null || echo HEAD)" origin/main "origin/$BR" 2>/dev/null | grep -q '^<<<<<<<'; then
      echo "- PR $N ($BR): **CONFLITO** com origin/main"
    else
      echo "- PR $N ($BR): sem conflito textual detectado"
    fi
  done
} > "$OUT/20-conflitos.md"
echo "  [->] $OUT/20-conflitos.md"

# --- 5. Geracao da matriz com dados reais ---------------------------------
{
  echo "# MATRIZ DE CONSOLIDACAO — PRs P0"
  echo ""
  echo "> Gerada por \`scripts/governanca/levantamento-pr-p0.sh\` em $DATA a partir de evidencia real."
  echo "> Evidencia bruta em \`evidencias/\`. Colunas de julgamento exigem analise."
  echo ""
  echo "## 1. Dados coletados"
  echo ""
  echo "| PR | Titulo | Branch | Draft | Arquivos | +/- | Migrations | Testes | Conflito c/ main |"
  echo "|---|---|---|---|---|---|---|---|---|"
  for N in "${PRS[@]}"; do
    F="$OUT/pr-$N.tsv"
    if [ ! -s "$F" ]; then
      echo "| $N | (inacessivel) | — | — | — | — | — | — | — |"
      continue
    fi
    IFS=$'\t' read -r T BR DR CF AD DE < "$F"
    T="$(echo "$T" | cut -c1-45)"
    MG="$(grep -c . "$OUT/pr-$N.migrations.txt" 2>/dev/null || echo 0)"
    TS="$(grep -c . "$OUT/pr-$N.testes.txt" 2>/dev/null || echo 0)"
    CO="$(grep "PR $N " "$OUT/20-conflitos.md" | grep -q CONFLITO && echo "SIM" || echo "nao")"
    echo "| $N | $T | \`$BR\` | $DR | $CF | +$AD/-$DE | $MG | $TS | $CO |"
  done
  echo ""
  echo "## 2. Migrations por PR"
  echo ""
  for N in "${PRS[@]}"; do
    echo "### PR $N"
    if [ -s "$OUT/pr-$N.migrations.txt" ]; then
      echo '```'; cat "$OUT/pr-$N.migrations.txt"; echo '```'
    else
      echo "Nenhuma migration."
    fi
    echo ""
  done
  echo "## 3. Sobreposicao de arquivos"
  echo ""
  sed 's/^# .*//' "$OUT/10-sobreposicao.md"
  echo ""
  echo "## 4. Conflitos contra origin/main"
  echo ""
  sed 's/^# .*//' "$OUT/20-conflitos.md"
  echo ""
  echo "## 5. Julgamento — PREENCHIMENTO HUMANO OBRIGATORIO"
  echo ""
  echo "Para cada PR, com referencia explicita ao diff em \`evidencias/pr-<N>.diff\`:"
  echo ""
  echo "| PR | Correcoes exclusivas | Correcoes duplicadas em | Impacto juridico | Impacto LGPD/seguranca | Recomendacao | Justificativa (linha do diff) |"
  echo "|---|---|---|---|---|---|---|"
  for N in "${PRS[@]}"; do echo "| $N | | | | | | |"; done
  echo ""
  echo "Recomendacoes admitidas: \`MANTER\` · \`ABSORVER PARCIALMENTE\` · \`SUBSTITUIR\` · \`FECHAR\`"
  echo ""
  echo "> Vedado preencher por inferencia. Sem leitura do diff, a celula permanece vazia."
  echo ""
  echo "## 6. Ordem de integracao"
  echo ""
  echo "| Ordem | PR | Justificativa | Pre-requisito |"
  echo "|---|---|---|---|"
  for I in 1 2 3 4 5; do echo "| $I | | | |"; done
  echo ""
  echo "Criterio: menor superficie de conflito primeiro; migrations em ordem de head;"
  echo "autenticacao e RBAC antes de funcionalidades dependentes."
  echo ""
  echo "## 7. Decisao final"
  echo ""
  echo "| Item | Conteudo |"
  echo "|---|---|"
  echo "| Data | |"
  echo "| Responsavel | Clovis Jose Soares |"
  echo "| PRs mantidos | |"
  echo "| PRs fechados | |"
  echo "| PRs absorvidos | |"
  echo "| Branch de consolidacao | |"
  echo "| Pendencias remanescentes | |"
} > "$MATRIZ"

echo ""
echo "  [->] $MATRIZ  (secoes 1 a 4 preenchidas com dados reais)"
echo ""
cat <<FIM
============================================================
 CONCLUIDO — coleta
============================================================
Proximo passo: analisar evidencias/pr-<N>.diff e preencher as
secoes 5 e 6 de $MATRIZ. Nenhuma celula pode ser preenchida sem
referencia ao diff.

Preserve evidencias/ ate o encerramento da consolidacao. Os diffs
brutos sao a prova de que a analise nao foi feita por inferencia.
FIM
