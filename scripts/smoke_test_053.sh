#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# EJC — Smoke-test pós-correção 053 (com autenticação)
# Valida que os endpoints antes quebrados (P0-1/P0-2/P0-3) respondem 2xx com token.
#
# USO (na VPS ou via túnel):
#   API=http://localhost:8000 TOKEN="<jwt_access>" bash scripts/smoke_test_053.sh
#   (obtenha o token logando: POST /api/auth/login)
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
API="${API:-http://localhost:8000}"
TOKEN="${TOKEN:-}"
[ -n "$TOKEN" ] || { echo "❌ Defina TOKEN=<jwt access>"; exit 1; }
H=(-H "Authorization: Bearer $TOKEN")
ok=0; fail=0

check() {  # $1=metodo $2=path $3=descricao  [4=body]
  local m="$1" p="$2" d="$3" body="${4:-}"
  local args=(-s -o /dev/null -w '%{http_code}' -X "$m" "${H[@]}" "$API$p")
  [ -n "$body" ] && args=(-s -o /dev/null -w '%{http_code}' -X "$m" "${H[@]}" -H 'Content-Type: application/json' -d "$body" "$API$p")
  local code; code="$(curl "${args[@]}" 2>/dev/null || echo 000)"
  if [ "$code" = "404" ] || [ "$code" = "500" ] || [ "$code" = "000" ]; then
    echo "  ✗ [$code] $d  ($m $p)"; fail=$((fail+1))
  else
    echo "  ✓ [$code] $d  ($m $p)"; ok=$((ok+1))
  fi
}

echo "── Health ──"
curl -fsS "$API/api/health" && echo

echo "── P0-1: rotas com duplo-prefixo corrigido (não devem dar 404) ──"
check GET  /api/v1/datajud/                         "DataJud"
check GET  /api/v1/despesas                         "Despesas (financeiro)"
check GET  /api/v1/partner-withdrawals              "Retiradas de sócios"
check GET  /api/v1/office-contracts                 "Contratos do escritório"
check GET  /api/v1/kanban-columns?legal_area=civel  "Kanban colunas"
check GET  /api/curadoria/                           "Curadoria"
check GET  /api/mediacao/                            "Mediação"

echo "── P0-2/P0-3: endpoints de IA (não devem dar 500 por método/import ausente) ──"
check POST /api/jurimetria/predicao-exito           "Jurimetria preditiva"      '{"contexto":"teste"}'
check POST /api/intelligence-v3/analise-impacto     "Intelligence v3"           '{"texto":"teste"}'
check POST /api/cerebro/analise-estrategica         "Cérebro (modo 2 IAs)"      '{"texto":"teste"}'

echo "── P1-1: Victory Vault agora exige auth (com token deve responder, sem token = 401) ──"
check GET  /api/victory_vault/teses                 "Victory Vault (autenticado)"

echo "── Fase 4: geração por template (engine religado) ──"
check GET  /api/document-templates/                 "Listar templates de documento"

echo ""
echo "Resultado: $ok OK · $fail com problema (404/500/000)."
[ "$fail" -eq 0 ] && echo "✅ Smoke-test PASSOU" || echo "⚠️  Revisar os itens marcados ✗"
