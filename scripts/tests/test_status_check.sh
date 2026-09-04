#!/usr/bin/env bash
# Testes de paridade/recusa do scripts/status_check.sh — exercita os três
# defeitos que o script existe para pegar (ID duplicado, status fora do
# enum, item mesclado+ sem PR), mais o caminho feliz e o resumo por fase.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHECK="$ROOT/scripts/status_check.sh"
TMP="$(mktemp -d)"
cleanup_tmp() { rm -rf "$TMP"; }
trap cleanup_tmp EXIT

falhou=0
assert_ok() {
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "OK: $desc"
  else
    echo "FALHA (deveria passar): $desc" >&2
    falhou=1
  fi
}
assert_falha() {
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "FALHA (deveria recusar): $desc" >&2
    falhou=1
  else
    echo "OK: $desc"
  fi
}
assert_falha_com_texto() {
  local desc="$1" texto="$2"; shift 2
  local saida
  if saida="$("$@" 2>&1)"; then
    echo "FALHA (deveria recusar): $desc" >&2
    falhou=1
  elif [[ "$saida" == *"$texto"* ]]; then
    echo "OK: $desc"
  else
    echo "FALHA (recusou pelo motivo errado): $desc — saída: $saida" >&2
    falhou=1
  fi
}

HEADER='| ID | Descrição | Fase | Issue | Status | PR | Data |
|---|---|---|---|---|---|---|'

# 1) Caminho feliz
cat > "$TMP/ok.md" <<EOF
$HEADER
| X-1 | item um | F1 | — | pendente | — | — |
| X-2 | item dois | F1 | #10 | mesclado | #20 | 2026-08-24 |
EOF
assert_ok "caminho feliz (2 itens válidos)" bash "$CHECK" --arquivo "$TMP/ok.md"

# 2) ID duplicado
cat > "$TMP/dup.md" <<EOF
$HEADER
| X-1 | item um | F1 | — | pendente | — | — |
| X-1 | item repetido | F1 | — | pendente | — | — |
EOF
assert_falha_com_texto "recusa ID duplicado" "ID duplicado" bash "$CHECK" --arquivo "$TMP/dup.md"

# 3) status fora do enum
cat > "$TMP/status_invalido.md" <<EOF
$HEADER
| X-1 | item um | F1 | — | concluido | — | — |
EOF
assert_falha_com_texto "recusa status fora do enum" "status inválido" bash "$CHECK" --arquivo "$TMP/status_invalido.md"

# 4) mesclado sem PR (travessão)
cat > "$TMP/sem_pr.md" <<EOF
$HEADER
| X-1 | item um | F1 | #10 | mesclado | — | — |
EOF
assert_falha_com_texto "recusa mesclado sem PR" "coluna PR vazia" bash "$CHECK" --arquivo "$TMP/sem_pr.md"

# 5) em-prod sem PR (célula vazia, não só travessão)
cat > "$TMP/em_prod_vazio.md" <<EOF
$HEADER
| X-1 | item um | F1 | #10 | em-prod |  | — |
EOF
assert_falha_com_texto "recusa em-prod com PR vazio" "coluna PR vazia" bash "$CHECK" --arquivo "$TMP/em_prod_vazio.md"

# 6) status com ** (negrito markdown) é aceito — usado no arquivo real
cat > "$TMP/negrito.md" <<EOF
$HEADER
| X-1 | item resolvido | F1 | #10 | **verificado** | #20 | 2026-08-22 |
EOF
assert_ok "aceita status em negrito markdown" bash "$CHECK" --arquivo "$TMP/negrito.md"

# 7) --resumo não quebra e imprime contagem
assert_ok "--resumo roda sobre arquivo válido" bash "$CHECK" --arquivo "$TMP/ok.md" --resumo

# 8) o checklist-mestre real do repositório passa
assert_ok "valida docs/PLANO_MESTRE_STATUS.md real" bash "$CHECK"

if [ "$falhou" -ne 0 ]; then
  echo "test_status_check: FALHOU" >&2
  exit 1
fi
echo "test_status_check: todos os casos OK"
