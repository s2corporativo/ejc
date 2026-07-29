#!/usr/bin/env bash
# deploy-vps.sh — sobe o EJC (novo design) numa VPS com Docker, em 1 comando.
#
# Uso na VPS (dentro do repositório clonado):
#   bash scripts/deploy-vps.sh
#
# O que faz:
#   1) Cria .env a partir do .env.example se ainda não existir, gerando
#      automaticamente segredos fortes (SECRET_KEY, PII_ENCRYPTION_KEY,
#      PII_HASH_KEY) e a senha do Postgres — via openssl (não exige Python).
#   2) Pergunta o domínio/IP público e o e-mail do admin (com defaults).
#   3) Sobe db + backend + frontend com `docker compose up -d --build`.
#      O backend aplica as migrations e cria o admin no primeiro boot.
#
# Idempotente: se o .env já existir, ele é preservado (edite à mão se precisar).
set -euo pipefail

cd "$(dirname "$0")/.."

command -v docker >/dev/null || { echo "ERRO: Docker não encontrado. Instale o Docker primeiro."; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "ERRO: plugin 'docker compose' não encontrado."; exit 1; }
command -v openssl >/dev/null || { echo "ERRO: openssl não encontrado (apt install openssl)."; exit 1; }

fernet_key() { openssl rand -base64 32 | tr '+/' '-_'; }            # 32 bytes url-safe b64 (formato Fernet)
rand_key()   { openssl rand -base64 "${1:-48}" | tr '+/' '-_' | tr -d '='; }

if [ ! -f .env ]; then
  echo "== Configuração inicial (.env não existe, criando) =="
  read -rp "Domínio ou IP público da VPS (ex.: http://203.0.113.10): " PUB
  PUB="${PUB:-http://localhost}"
  read -rp "E-mail do admin (NÃO use .local): " ADMIN_EMAIL
  ADMIN_EMAIL="${ADMIN_EMAIL:-admin@ejc.adv.br}"

  PG_PASS="$(rand_key 24)"
  ADMIN_PASS="$(rand_key 12)"
  SECRET="$(rand_key 64)"
  PII_ENC="$(fernet_key)"
  PII_HASH="$(rand_key 32)"

  cp .env.example .env
  # Substituições seguras (| como separador; valores não contêm |)
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${PG_PASS}|"       .env
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|"                      .env
  sed -i "s|^PII_ENCRYPTION_KEY=.*|PII_ENCRYPTION_KEY=${PII_ENC}|"     .env
  sed -i "s|^PII_HASH_KEY=.*|PII_HASH_KEY=${PII_HASH}|"                .env
  sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=${PUB}|"                     .env
  sed -i "s|^FRONTEND_URL=.*|FRONTEND_URL=${PUB}|"                     .env
  sed -i "s|^ADMIN_EMAIL=.*|ADMIN_EMAIL=${ADMIN_EMAIL}|"              .env
  sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=${ADMIN_PASS}|"          .env

  echo
  echo "==================== GUARDE ESTAS CREDENCIAIS ===================="
  echo " URL:            ${PUB}"
  echo " Admin (login):  ${ADMIN_EMAIL}"
  echo " Admin (senha):  ${ADMIN_PASS}   (troca obrigatória no 1º acesso)"
  echo " Segredos (SECRET_KEY/PII_*) gravados em .env — NÃO os perca."
  echo "================================================================="
  echo
else
  echo "== .env já existe — preservado. Editando manualmente se necessário. =="
fi

# ── Migrações de valores OBSOLETOS no .env preservado ────────────────────────
# O .env sobrevive ao deploy (por desenho), então trocar um default no código ou
# no .env.example NÃO alcança as instalações existentes. Estes ajustes são
# idempotentes: só agem se o valor antigo ainda estiver lá.

# AI-043: llama-3.3-70b-versatile foi DEPRECIADO pela Groq (deixa de ser servido
# em ago/2026). Migra para o substituto oficial recomendado.
if grep -qE '^GROQ_MODEL(_LARGE)?=llama-3\.3-70b-versatile' .env 2>/dev/null; then
  cp .env ".env.bak.$(date +%Y%m%d%H%M%S)"
  sed -i 's|^GROQ_MODEL=llama-3\.3-70b-versatile|GROQ_MODEL=openai/gpt-oss-120b|' .env
  sed -i 's|^GROQ_MODEL_LARGE=llama-3\.3-70b-versatile|GROQ_MODEL_LARGE=openai/gpt-oss-120b|' .env
  echo "!! .env: modelo Groq depreciado migrado para openai/gpt-oss-120b (backup .env.bak.*)"
fi

# AI-033/AI-034: agente com write-tools não deve ficar ligado sem decisão
# explícita. Só AVISA — desligar em produção é decisão do titular, não do script.
if grep -qE '^AI_AGENT_ENABLED=true' .env 2>/dev/null; then
  echo "!! ATENÇÃO: AI_AGENT_ENABLED=true neste .env — o agente de IA com"
  echo "   ferramentas de ESCRITA está habilitado. A auditoria 2026-07-26"
  echo "   recomenda AI_AGENT_ENABLED=false até a homologação do HITL."
fi

echo "== Subindo os serviços (build + up)... =="
docker compose up -d --build

echo
echo "== Status =="
docker compose ps
echo
echo "Pronto. Acompanhe o boot do backend (migrations + seed do admin):"
echo "  docker compose logs -f backend"
echo "Depois acesse a URL configurada e faça login com o admin acima."
