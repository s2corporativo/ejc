#!/usr/bin/env bash
# ── EJC v3.0 — Deploy no Contabo VPS (Ubuntu 22/24) ──────────────────────────
# Uso: bash scripts/deploy.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=legacy_script_guard.sh
source "$SCRIPT_DIR/legacy_script_guard.sh"
ejc_legacy_script_guard "scripts/deploy.sh" "/opt/s2-automation/host/ejc-deploy-approved.sh"

echo "═══ EJC v3.0 — Deploy ═══"

# 1. Pré-checagens
command -v docker >/dev/null || { echo "❌ Docker não instalado. Rode: curl -fsSL https://get.docker.com | sh"; exit 1; }
docker compose version >/dev/null || { echo "❌ Docker Compose v2 ausente"; exit 1; }
[ -f .env ] || { echo "❌ Crie o .env: cp .env.example .env (e preencha!)"; exit 1; }

grep -q "TROCAR" .env && {
  echo "⚠️  ATENÇÃO: ainda há valores 'TROCAR' no .env. Corrija antes de produção."
  read -p "Continuar mesmo assim? (s/N) " resp
  [ "$resp" = "s" ] || exit 1
}

# 2. Build + subida
echo "── Build das imagens..."
docker compose build

echo "── Subindo containers..."
docker compose up -d

echo "── Aguardando banco..."
sleep 8

# 3. Migrations
echo "── Aplicando migrations Alembic..."
docker compose exec -T backend alembic upgrade head

# 4. Seed (idempotente)
echo "── Rodando seed (admin + feriados + súmulas)..."
docker compose exec -T backend python seeds/seed_all.py

# 5. Health
echo "── Verificando health..."
sleep 3
curl -fsS http://127.0.0.1:8000/api/health && echo ""

echo ""
echo "═══ Deploy concluído ═══"
echo "Próximos passos (uma vez só):"
echo "  1. Configurar Nginx do host:  sudo cp nginx/ejc.conf /etc/nginx/sites-available/ejc.conf"
echo "     (edite SEU_DOMINIO antes), depois:"
echo "     sudo ln -s /etc/nginx/sites-available/ejc.conf /etc/nginx/sites-enabled/"
echo "     sudo nginx -t && sudo systemctl reload nginx"
echo "  2. SSL: sudo certbot --nginx -d SEU_DOMINIO"
echo "  3. Firewall: sudo ufw allow 22,80,443/tcp && sudo ufw enable"
echo "  4. Backup diário: crontab -e →"
echo "     0 3 * * * cd $(pwd) && bash scripts/backup.sh >> /var/log/ejc_backup.log 2>&1"
echo "  5. Login inicial: \$ADMIN_EMAIL / \$ADMIN_PASSWORD (TROQUE no primeiro acesso)"
