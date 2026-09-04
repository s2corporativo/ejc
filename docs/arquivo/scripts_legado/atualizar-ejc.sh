#!/usr/bin/env bash
set -euo pipefail
cd /opt/ejc
log(){ echo ""; echo "===== $* ====="; }

log "1/6 Salvando o estado atual do codigo (branch de backup)"
git fetch origin main
git branch "backup-servidor-$(date +%Y%m%d_%H%M%S)" || true

log "2/6 Backup do banco de dados"
mkdir -p backups
docker exec ejc_db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "backups/pre_consolidacao_$(date +%Y%m%d_%H%M%S).sql.gz"
ls -lh backups/*.sql.gz | tail -1

log "3/6 Ajustando .env (chaves LGPD exigidas pelas migrations novas)"
cp .env ".env.bak.pre_consolidacao_$(date +%Y%m%d_%H%M%S)"
grep -q "^PII_ENCRYPTION_KEY=..*" .env || echo "PII_ENCRYPTION_KEY=$(openssl rand -base64 32 | tr '+/' '-_')" >> .env
grep -q "^PII_HASH_KEY=..*" .env || echo "PII_HASH_KEY=$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')" >> .env
sed -i 's/^EMBEDDINGS_ENABLED=true/EMBEDDINGS_ENABLED=false/' .env

log "4/6 Atualizando o codigo para a versao consolidada (origin/main)"
git reset --hard origin/main
git log --oneline -1

log "5/6 Reconstruindo as imagens (pode levar varios minutos)"
docker compose build backend frontend

log "6/6 Subindo a stack nova (migra o banco sozinha no boot; remove o embeddings orfao)"
docker compose up -d --remove-orphans
echo "Aguardando o backend migrar e subir (ate 3 min)..."
for i in $(seq 1 18); do
  st=$(docker inspect --format "{{.State.Health.Status}}" ejc_backend 2>/dev/null || echo starting)
  echo "  tentativa $i: $st"
  [ "$st" = "healthy" ] && break
  sleep 10
done
docker ps --filter name=ejc --format "table {{.Names}}\t{{.Status}}"
echo ""
echo "Ultimas linhas do log do backend:"
docker logs --tail 15 ejc_backend
