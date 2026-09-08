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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=legacy_script_guard.sh
source "$SCRIPT_DIR/legacy_script_guard.sh"
ejc_legacy_script_guard "scripts/deploy-vps.sh" "infra/selfhosted/bootstrap.sh + RUNBOOK_DEPLOY_MANUAL.md"

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
# Implementação única em scripts/migrar_env_obsoletos.sh, compartilhada com o
# deploy real (deploy_vps_safe.sh). Antes a migração existia só aqui — e este
# script é um bootstrap MANUAL, fora do caminho do GitHub Actions, então a
# correção do modelo Groq nunca chegava à VPS.
bash "$(dirname "$0")/migrar_env_obsoletos.sh" .env

echo "== Subindo os serviços (build + up)... =="
docker compose up -d --build

echo
echo "== Status =="
docker compose ps
echo
echo "Pronto. Acompanhe o boot do backend (migrations + seed do admin):"
echo "  docker compose logs -f backend"
echo "Depois acesse a URL configurada e faça login com o admin acima."
