#!/usr/bin/env bash
# ── EJC v3.0 — Setup inicial no VPS Contabo ───────────────────────────────────
# Executar como root após upload do projeto:
#   bash /opt/ejc/scripts/vps_setup.sh
#
# Idempotente — pode ser reexecutado para atualizar.
set -euo pipefail
DOMAIN="ejc.depaulateixeira.adv.br"
APP_DIR="/opt/ejc"

echo "═══════════════════════════════════════════════"
echo " EJC v3.0 — Setup VPS | $DOMAIN"
echo "═══════════════════════════════════════════════"

# ── 1. Dependências do sistema ─────────────────────────────────────────────────
echo "[1/8] Instalando dependências do sistema..."
apt-get update -qq
apt-get install -y -qq docker.io docker-compose-v2 nginx certbot python3-certbot-nginx \
    curl git unzip ufw 2>/dev/null || true

systemctl enable --now docker
usermod -aG docker "$USER" 2>/dev/null || true

# ── 2. Firewall ────────────────────────────────────────────────────────────────
echo "[2/8] Configurando UFW firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   comment "SSH"
ufw allow 80/tcp   comment "HTTP"
ufw allow 443/tcp  comment "HTTPS"
ufw --force enable

# ── 3. Verificar .env ──────────────────────────────────────────────────────────
echo "[3/8] Verificando .env..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo "⚠️  .env criado a partir do exemplo. EDITE ANTES DE CONTINUAR:"
    echo "   nano $APP_DIR/.env"
    echo ""
    echo "   Campos obrigatórios:"
    echo "   - SECRET_KEY (python3 -c \"import secrets; print(secrets.token_urlsafe(64))\")"
    echo "   - POSTGRES_PASSWORD"
    echo "   - ADMIN_EMAIL / ADMIN_PASSWORD"
    echo "   - CORS_ORIGINS=https://$DOMAIN"
    echo "   - FRONTEND_URL=https://$DOMAIN"
    echo ""
    read -p "Pressione ENTER após editar o .env para continuar..." _
fi

# Injetar domínio no .env se ainda genérico
sed -i "s|CORS_ORIGINS=https://ejc.depaulateixeira.adv.br|CORS_ORIGINS=https://$DOMAIN|g" "$APP_DIR/.env"
sed -i "s|FRONTEND_URL=https://ejc.depaulateixeira.adv.br|FRONTEND_URL=https://$DOMAIN|g" "$APP_DIR/.env"

# ── 4. Build Docker ────────────────────────────────────────────────────────────
echo "[4/8] Build das imagens Docker..."
cd "$APP_DIR"
docker compose build --parallel

# ── 5. Subir containers ────────────────────────────────────────────────────────
echo "[5/8] Subindo containers..."
docker compose up -d

echo "  Aguardando PostgreSQL ficar saudável..."
for i in $(seq 1 30); do
    if docker compose exec -T db pg_isready -U ejc_user -d ejc_db >/dev/null 2>&1; then
        echo "  ✅ Banco disponível"
        break
    fi
    sleep 2
done

# ── 6. Migrations + Seed ───────────────────────────────────────────────────────
echo "[6/8] Aplicando migrations Alembic..."
docker compose exec -T backend alembic upgrade head

echo "  Rodando seed (admin + feriados + súmulas)..."
docker compose exec -T backend python seeds/seed_all.py

# ── 7. Nginx + SSL ─────────────────────────────────────────────────────────────
echo "[7/8] Configurando Nginx e SSL..."
cp "$APP_DIR/nginx/ejc.conf" /etc/nginx/sites-available/ejc.conf

# Desabilitar default se existir
rm -f /etc/nginx/sites-enabled/default

# Habilitar EJC
ln -sf /etc/nginx/sites-available/ejc.conf /etc/nginx/sites-enabled/ejc.conf

# Teste de configuração
nginx -t

# Se ainda não tem SSL, usar configuração temporária HTTP para certbot funcionar
if [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    echo "  Obtendo certificado SSL para $DOMAIN..."
    # Temporariamente servir HTTP para validação do certbot
    cat > /etc/nginx/sites-available/ejc.conf << 'NGINX_HTTP'
server {
    listen 80;
    server_name ejc.depaulateixeira.adv.br;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX_HTTP
    systemctl reload nginx
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
        --email "adm@vetmg.com.br" --redirect || {
        echo "⚠️  Certbot falhou. Verifique que o DNS $DOMAIN aponta para este IP."
        echo "   Após corrigir, rode: certbot --nginx -d $DOMAIN"
    }
    # Restaurar configuração completa com SSL
    cp "$APP_DIR/nginx/ejc.conf" /etc/nginx/sites-available/ejc.conf
fi

systemctl reload nginx

# ── 8. Health check ────────────────────────────────────────────────────────────
echo "[8/8] Verificando saúde do sistema..."
sleep 5
if curl -fsS "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
    echo "  ✅ Backend respondendo"
else
    echo "  ⚠️  Backend ainda iniciando — verifique: docker compose logs backend"
fi

echo ""
echo "═══════════════════════════════════════════════"
echo " ✅ Deploy concluído!"
echo "═══════════════════════════════════════════════"
echo ""
echo " Sistema: https://$DOMAIN"
echo " Login:   use ADMIN_EMAIL e ADMIN_PASSWORD do .env"
echo ""
echo " Comandos úteis:"
echo "   docker compose logs -f backend      # logs em tempo real"
echo "   docker compose exec backend bash    # shell no container"
echo "   docker compose restart backend      # reiniciar backend"
echo ""
