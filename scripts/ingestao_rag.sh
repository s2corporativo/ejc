#!/usr/bin/env bash
# ── scripts/ingestao_rag.sh ───────────────────────────────────────────────────
# Dispara a ingestão de fontes jurídicas oficiais no RAG do EJC, contra a API
# (produção por default). Autentica, obtém o access token e chama os endpoints
# de ingestão. Idempotente — reexecutar não duplica (dedup por chave_origem).
#
# Rode no VPS ou em qualquer máquina com acesso de rede à API. Este script só
# fala com a API do EJC (não com as fontes .gov/.jus), então roda de qualquer
# lugar que alcance a URL base — quem baixa os sites é o backend, em produção.
#
# Credenciais por variável de ambiente OU prompt interativo (nunca hardcode):
#   EJC_BASE      URL base           (default https://ejc.depaulateixeira.adv.br)
#   EJC_EMAIL     e-mail de um usuário superadmin/admin/socio
#   EJC_PASSWORD  senha              (se ausente, é solicitada sem eco na tela)
#   EJC_TOTP      código 2FA 6 díg.  (só se a conta exigir; opcional)
#   EJC_SEED      "1" p/ também chamar POST /api/rag/seed?incluir_jurisprudencia=true
#
# Uso:
#   EJC_EMAIL=admin@dominio ./scripts/ingestao_rag.sh
#   EJC_EMAIL=admin@dominio EJC_SEED=1 ./scripts/ingestao_rag.sh
set -euo pipefail

BASE="${EJC_BASE:-https://ejc.depaulateixeira.adv.br}"

command -v curl    >/dev/null || { echo "erro: curl não encontrado" >&2; exit 1; }
command -v python3 >/dev/null || { echo "erro: python3 não encontrado (usado p/ ler JSON)" >&2; exit 1; }

# ── Credenciais (env ou prompt) ──────────────────────────────────────────────
EMAIL="${EJC_EMAIL:-}"
if [ -z "$EMAIL" ]; then read -r -p "E-mail (superadmin/admin/socio): " EMAIL; fi
PASSWORD="${EJC_PASSWORD:-}"
if [ -z "$PASSWORD" ]; then read -r -s -p "Senha: " PASSWORD; echo; fi
TOTP="${EJC_TOTP:-}"

# Monta o corpo do login como JSON (senha/totp vão por env p/ o python — nunca
# em argv, então não aparecem em `ps`). totp_code só entra se fornecido.
_login_body() {
  EMAIL="$EMAIL" PASSWORD="$PASSWORD" TOTP="$TOTP" python3 - <<'PY'
import json, os
body = {"email": os.environ["EMAIL"], "password": os.environ["PASSWORD"]}
totp = os.environ.get("TOTP", "").strip()
if totp:
    body["totp_code"] = totp
print(json.dumps(body))
PY
}

echo "→ autenticando em $BASE ..."
LOGIN_RESP="$(curl -sS -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "$(_login_body)")"

TOKEN="$(printf '%s' "$LOGIN_RESP" | python3 -c '
import sys, json
try:
    print(json.load(sys.stdin).get("access_token", ""), end="")
except Exception:
    pass
')"

if [ -z "$TOKEN" ]; then
  echo "erro: login não retornou access_token. Resposta da API:" >&2
  printf '%s\n' "$LOGIN_RESP" >&2
  echo "Dica: se a conta tiver 2FA ativo, exporte EJC_TOTP=<código de 6 dígitos>." >&2
  exit 1
fi
echo "✓ autenticado."

# ── Dispara a ingestão de fontes oficiais (ANPD + RFB + federação LexML) ──────
echo "→ POST /api/rag/ingest-fontes-oficiais ..."
curl -sS -X POST "$BASE/api/rag/ingest-fontes-oficiais" \
  -H "Authorization: Bearer $TOKEN" \
  -w '\n[HTTP %{http_code}]\n'

# ── Seed opcional (base do escritório + importação inicial de jurisprudência) ─
if [ "${EJC_SEED:-0}" = "1" ]; then
  echo "→ POST /api/rag/seed?incluir_jurisprudencia=true ..."
  curl -sS -X POST "$BASE/api/rag/seed?incluir_jurisprudencia=true" \
    -H "Authorization: Bearer $TOKEN" \
    -w '\n[HTTP %{http_code}]\n'
fi

echo
echo "✓ ingestão agendada em background (HTTP 202)."
echo "  Acompanhe pela tabela fontes_ingestao (painel de fontes): última"
echo "  execução, status (ok/parcial/erro) e contagem por fonte."
echo "  Detalhes e ingestão automática: docs/RUNBOOK_INGESTAO_RAG.md"
