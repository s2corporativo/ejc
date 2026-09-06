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
echo "[2/8] Configurando UFW firewall (aditivo)..."
# NUNCA `ufw --force reset` aqui: a VPS é COMPARTILHADA com outros sistemas
# (Verde Limp, S2, Evolution API, Woodpecker, Uptime Kuma) e o reset apagava
# as regras deles (INF-03). Só garante as regras que o EJC precisa; `ufw allow`
# é idempotente. Se o UFW ainda estiver inativo, o operador decide ativar.
ufw allow 22/tcp   comment "SSH"
ufw allow 80/tcp   comment "HTTP"
ufw allow 443/tcp  comment "HTTPS"
if ufw status | grep -q "^Status: active"; then
    echo "  UFW ativo — regras do EJC garantidas."
else
    echo "  AVISO: UFW inativo. Ative manualmente após conferir as regras dos outros sistemas: ufw enable"
fi

# ── 3. Verificar .env ──────────────────────────────────────────────────────────
echo "[3/8] Verificando .env..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    echo "⚠️  .env criado a partir do exemplo. EDITE e rode este script de novo:"
    echo "   nano $APP_DIR/.env"
    echo ""
    echo "   Campos obrigatórios:"
    echo "   - SECRET_KEY (python3 -c \"import secrets; print(secrets.token_urlsafe(64))\")"
    echo "   - POSTGRES_PASSWORD, PII_ENCRYPTION_KEY, PII_HASH_KEY"
    echo "   - ADMIN_EMAIL / ADMIN_PASSWORD"
    echo "   - CORS_ORIGINS=https://$DOMAIN"
    echo "   - FRONTEND_URL=https://$DOMAIN"
    # Não interativo (INF-03): este script pode ser chamado por automação.
    exit 1
fi
if grep -q "TROCAR" "$APP_DIR/.env"; then
    echo "ERRO: ainda há valores TROCAR em $APP_DIR/.env — corrija antes de continuar." >&2
    exit 1
fi

# Injetar domínio no .env se ainda genérico
sed -i "s|CORS_ORIGINS=https://SEU_DOMINIO|CORS_ORIGINS=https://$DOMAIN|g" "$APP_DIR/.env"
sed -i "s|FRONTEND_URL=https://SEU_DOMINIO|FRONTEND_URL=https://$DOMAIN|g" "$APP_DIR/.env"

# Migração de valores OBSOLETOS no .env preservado — implementação única em
# scripts/migrar_env_obsoletos.sh, compartilhada com deploy_vps_safe.sh (o
# bootstrap manual antigo, deploy-vps.sh, foi arquivado; esta chamada mantém
# o caminho manual coberto — tests/test_migrar_env_obsoletos.py).
bash "$APP_DIR/scripts/migrar_env_obsoletos.sh" "$APP_DIR/.env"

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
# Primeira instalação = banco vazio: o schema é criado aqui, uma única vez,
# sob a flag explícita FIRST_INSTALL=1. Em instalação já existente, migrations
# só pela esteira (scripts/deploy_manual.sh / ejc-deploy-approved.sh), que
# faz backup e classificação expand-only antes (INF-03).
if [ "${FIRST_INSTALL:-0}" = "1" ]; then
    echo "[6/8] Primeira instalação: aplicando migrations Alembic..."
    docker compose exec -T backend alembic upgrade head
    echo "  Rodando seed (admin + feriados + súmulas)..."
    docker compose exec -T backend python seeds/seed_all.py
else
    echo "[6/8] Migrations NÃO aplicadas (instalação existente). Use a esteira de deploy;"
    echo "      para banco novo rode com FIRST_INSTALL=1."
fi

# ── 7. Nginx + SSL ─────────────────────────────────────────────────────────────
echo "[7/8] Configurando Nginx e SSL..."
# O template de produção agora existe versionado no repo (nginx/ejc.conf).
# `cp -f` sobrescreve o destino sem abortar se já existir (idempotência: este
# script pode ser reexecutado). Falha explícita e clara se o fonte sumir.
if [ ! -f "$APP_DIR/nginx/ejc.conf" ]; then
    echo "ERRO: $APP_DIR/nginx/ejc.conf não encontrado — o repositório está incompleto." >&2
    exit 1
fi
cp -f "$APP_DIR/nginx/ejc.conf" /etc/nginx/sites-available/ejc.conf

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
    cp -f "$APP_DIR/nginx/ejc.conf" /etc/nginx/sites-available/ejc.conf
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