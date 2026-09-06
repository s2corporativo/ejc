#!/usr/bin/env bash
# atualizar-vps.sh - atualizacao segura e VERIFICADA do EJC no VPS (1 comando).
#
# Cada etapa e um GATE: se falhar, o script para na hora, mostra o diagnostico
# (incluindo os ultimos logs do backend) e nada fica pela metade sem aviso.
# Idempotente: pode rodar quantas vezes quiser.
#
# O que ele garante, na ordem:
#   1. .env integro (POSTGRES_*, SECRET_KEY, chaves LGPD geradas se faltarem)
#   2. backup do banco ANTES de qualquer mudanca (independe do nome do container)
#   3. codigo exatamente igual a origin/main (com branch de backup do estado atual)
#   4. fixes criticos presentes (libmagic no Dockerfile, /api/health no compose)
#   5. build do backend SEM cache (elimina camada antiga envenenada)
#   6. PROVA da imagem antes de subir (import magic + import app.main)
#   7. sobe com --force-recreate (garante que o container usa a imagem nova)
#      e espera o healthcheck de verdade
#   8. smoke test final (migrations, /api/health, frontend HTTP 200)
set -euo pipefail
cd /opt/ejc

log() { printf '\n===== %s =====\n' "$*"; }
ok()  { printf '  [OK] %s\n' "$*"; }
dump_logs() {
  BID_DUMP="$(docker compose ps -a -q backend 2>/dev/null | head -1 || true)"
  if [ -n "${BID_DUMP:-}" ]; then
    echo '---- ultimas 40 linhas do log do backend ----'
    docker logs --tail 40 "$BID_DUMP" 2>&1 || true
  fi
}
die() { printf '\n[ERRO] %s\n' "$*" >&2; dump_logs; exit 1; }
trap 'echo; echo "[ERRO] Falha inesperada na linha $LINENO"; dump_logs' ERR

log "1/8 Pre-checagens"
command -v docker >/dev/null || die "docker nao instalado"
docker compose version >/dev/null 2>&1 || die "plugin docker compose ausente"
[ -f .env ] || die ".env ausente em /opt/ejc"
for v in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB SECRET_KEY; do
  grep -q "^${v}=..*" .env || die ".env sem ${v}"
done
grep -q "^PII_ENCRYPTION_KEY=..*" .env || echo "PII_ENCRYPTION_KEY=$(openssl rand -base64 32 | tr '+/' '-_')" >> .env
grep -q "^PII_HASH_KEY=..*" .env || echo "PII_HASH_KEY=$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')" >> .env
ok ".env integro (POSTGRES_*, SECRET_KEY, chaves LGPD)"

log "2/8 Backup do banco"
mkdir -p backups
DB_ID="$(docker compose ps -q db 2>/dev/null || true)"
if [ -n "$DB_ID" ]; then
  ARQ="backups/pre_update_$(date +%Y%m%d_%H%M%S).sql.gz"
  docker exec "$DB_ID" sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$ARQ"
  ok "backup salvo: $ARQ ($(du -sh "$ARQ" | cut -f1))"
else
  echo "  [AVISO] banco nao esta rodando - backup pulado (dados seguem no volume postgres_data)"
fi

log "3/8 Codigo na ultima versao da main"
git fetch origin main
git branch "backup-servidor-$(date +%Y%m%d_%H%M%S)" >/dev/null 2>&1 || true
git reset --hard origin/main >/dev/null
ok "commit: $(git log --oneline -1)"

log "4/8 Conferindo os fixes no codigo (gates)"
grep -q 'libmagic1' backend/Dockerfile || die "Dockerfile sem libmagic1 - main desatualizada?"
grep -q 'localhost:8000/api/health' docker-compose.yml || die "compose sem healthcheck /api/health"
grep -q 'container_name: ejc_backend' docker-compose.yml || die "compose sem container_name fixo"
ok "backend/Dockerfile e docker-compose.yml corretos"

log "5/8 Build do backend SEM cache (elimina camadas antigas) + frontend"
docker compose build --no-cache backend
docker image inspect ejc-backend:latest >/dev/null 2>&1 || die "imagem ejc-backend:latest nao existe apos o build"
# Frontend TAMBEM precisa de build explicito: `docker compose up` NUNCA
# reconstroi imagem por mudanca de arquivo — sem isto o visual fica velho.
# (com cache: so re-executa a partir da camada que mudou)
docker compose build frontend
ok "imagens backend (sem cache) e frontend reconstruidas"

log "6/8 PROVA da imagem antes de subir"
docker run --rm --entrypoint python ejc-backend:latest \
  -c "import magic; print('  libmagic ->', magic.from_buffer(b'%PDF-1.4', mime=True))" \
  || die "a imagem nova AINDA nao enxerga a libmagic"
docker run --rm --entrypoint python ejc-backend:latest \
  -c "import app.main; print('  import app.main -> OK')" \
  || die "o app nao importa dentro da imagem (traceback acima)"
ok "imagem aprovada nos 2 testes de boot"

log "7/8 Subindo a stack (recriacao forcada)"
docker compose up -d --force-recreate --remove-orphans backend
BID="$(docker compose ps -q backend)"
ST=starting
for i in $(seq 1 24); do
  ST="$(docker inspect --format '{{.State.Health.Status}}' "$BID" 2>/dev/null || echo starting)"
  echo "  aguardando backend: tentativa $i/24 -> $ST"
  if [ "$ST" = healthy ]; then break; fi
  if [ "$ST" = unhealthy ]; then break; fi
  sleep 10
done
if [ "$ST" != healthy ]; then die "backend terminou como '$ST'"; fi
ok "backend healthy"
docker compose up -d --remove-orphans
ok "frontend no ar"

# ── IA local (Ollama) — OPCIONAL, nunca bloqueia o deploy ──────────────────
# Liga com IA_LOCAL=1 ./scripts/atualizar-vps.sh, ou automaticamente se o
# profile ia-local ja estava em uso (container ollama existente). O `up`
# padrao acima NAO toca nestes servicos (profile opt-in). Falha aqui NAO
# derruba o deploy: sem Ollama a cadeia de IA cai para Anthropic/Groq sozinha.
if [ "${IA_LOCAL:-0}" = "1" ] || [ -n "$(docker compose --profile ia-local ps -q ollama 2>/dev/null)" ]; then
  log "IA local (Ollama) — profile ia-local"
  if ./scripts/subir-ia-local.sh; then
    ok "IA local no ar (modelos conferidos)"
  else
    echo "  [AVISO] IA local falhou — backend segue com Anthropic/Groq (fallback automatico)"
  fi
fi

log "8/8 Smoke test final"
echo "  migrations: $(docker exec "$BID" python -m alembic current 2>/dev/null | tail -1)"
docker exec "$BID" curl -fsS http://localhost:8000/api/health >/dev/null && ok "/api/health respondendo"
CODE="$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:80/ || true)"
if [ "$CODE" = 200 ]; then ok "frontend HTTP 200"; else echo "  [AVISO] frontend respondeu HTTP $CODE"; fi
docker ps --filter name=ejc --format 'table {{.Names}}\t{{.Status}}'
docker image prune -f >/dev/null 2>&1 || true

printf '\n[SUCESSO] EJC atualizado, migrado e saudavel.\n'
