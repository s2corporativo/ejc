#!/usr/bin/env bash
# status_check.sh — valida docs/PLANO_MESTRE_STATUS.md como a fonte única de
# status do plano-mestre EJC. Sem isto o checklist vira só mais um documento
# desatualizado: este script é o enforcement, chamado por
# `scripts/ci-local.sh required`.
#
# Regras impostas (recusa com código != 0 e mensagem no stderr):
#   1. Toda linha de dados da tabela principal tem um ID não-vazio e único.
#   2. `status` pertence ao enum fechado: pendente, em-andamento, mesclado,
#      em-prod, verificado.
#   3. Todo item com status mesclado/em-prod/verificado tem a coluna PR
#      preenchida (nem vazia, nem travessão "—").
#
# Uso:
#   scripts/status_check.sh              # valida e sai 0/1
#   scripts/status_check.sh --resumo     # valida e imprime contagem por status/fase
#   scripts/status_check.sh --arquivo X  # valida outro arquivo (usado nos testes)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARQUIVO="$ROOT/docs/PLANO_MESTRE_STATUS.md"
RESUMO=0

while [ $# -gt 0 ]; do
  case "$1" in
    --resumo) RESUMO=1; shift ;;
    --arquivo) ARQUIVO="$2"; shift 2 ;;
    *) echo "ERRO: argumento desconhecido: $1" >&2; exit 2 ;;
  esac
done

[ -f "$ARQUIVO" ] || { echo "ERRO: arquivo de status não encontrado: $ARQUIVO" >&2; exit 1; }

# Extrai só as linhas de dados da tabela principal: começam com "| " e a
# segunda linha da tabela (separador "|---|---|...") já foi descartada porque
# não bate com o padrão de ID esperado (primeira coluna != "---").
LINHAS="$(awk -F'|' '
  /^\| *ID *\|/ { in_table=1; next }
  in_table && /^\|[ -]*\|/ { next }
  in_table && /^\|/ {
    if ($0 ~ /^## /) { in_table=0; next }
    print
  }
  /^## Placar/ { in_table=0 }
' "$ARQUIVO")"

[ -n "$LINHAS" ] || { echo "ERRO: nenhuma linha de dados encontrada na tabela de $ARQUIVO" >&2; exit 1; }

ENUM_VALIDO="pendente em-andamento mesclado em-prod verificado"
declare -A VISTOS
ERROS=0
TOTAL=0
declare -A POR_STATUS
declare -A POR_FASE

while IFS='|' read -r _ id descricao fase issue status pr data _; do
  id="$(echo "$id" | xargs)"
  fase="$(echo "$fase" | xargs)"
  status="$(echo "$status" | xargs | sed -e 's/^\*\*//' -e 's/\*\*$//')"
  pr="$(echo "$pr" | xargs)"

  [ -n "$id" ] || continue
  TOTAL=$((TOTAL+1))

  if [ -n "${VISTOS[$id]:-}" ]; then
    echo "ERRO: ID duplicado no checklist-mestre: $id" >&2
    ERROS=$((ERROS+1))
  fi
  VISTOS[$id]=1

  case " $ENUM_VALIDO " in
    *" $status "*) ;;
    *)
      echo "ERRO: status inválido em $id: '$status' (esperado um de: $ENUM_VALIDO)" >&2
      ERROS=$((ERROS+1))
      ;;
  esac

  case "$status" in
    mesclado|em-prod|verificado)
      if [ -z "$pr" ] || [ "$pr" = "—" ] || [ "$pr" = "-" ]; then
        echo "ERRO: $id tem status '$status' mas coluna PR vazia — todo item mesclado+ precisa de PR" >&2
        ERROS=$((ERROS+1))
      fi
      ;;
  esac

  POR_STATUS["$status"]=$(( ${POR_STATUS[$status]:-0} + 1 ))
  POR_FASE["$fase"]=$(( ${POR_FASE[$fase]:-0} + 1 ))
done <<< "$LINHAS"

if [ "$RESUMO" -eq 1 ]; then
  echo "--- Plano-Mestre EJC — resumo ($TOTAL itens) ---"
  echo "Por status:"
  for k in $ENUM_VALIDO; do
    echo "  $k: ${POR_STATUS[$k]:-0}"
  done
  echo "Por fase:"
  for k in "${!POR_FASE[@]}"; do
    echo "  $k: ${POR_FASE[$k]}"
  done | sort
fi

if [ "$ERROS" -gt 0 ]; then
  echo "status_check: $ERROS erro(s) em $TOTAL item(ns) — corrija $ARQUIVO" >&2
  exit 1
fi

echo "status_check: OK — $TOTAL itens válidos em $ARQUIVO"
