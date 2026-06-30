#!/bin/sh
# ── entrypoint.sh ─────────────────────────────────────────────────────────────
# Sequência de startup do backend EJC:
#   1. Aguardar PostgreSQL ficar pronto (até 30 tentativas × 2s = 60s).
#   2. Aplicar migrations pendentes com Alembic (idempotente — noop se já aplicadas).
#   3. Rodar seed_all.py (admin + feriados 2026-2030 + súmulas iniciais).
#      seed_all é idempotente — pula registros já existentes.
#   4. Subir uvicorn com as flags do CMD.
#
# LGPD/OAB: seed nunca cria dados de cliente ou caso — apenas usuário admin,
# feriados, súmulas e fontes de ingestão. Seguro rodar em produção.
set -e

echo "[EJC] Aguardando PostgreSQL..."
MAX=30; N=0
until python -c "
import asyncio, asyncpg, os, sys
async def ping():
    url=os.environ.get('DATABASE_URL','').replace('+asyncpg','')
    conn=await asyncpg.connect(url, timeout=5)
    await conn.close()
try:
    asyncio.run(ping())
except:
    sys.exit(1)
" 2>/dev/null; do
  N=$((N+1))
  if [ $N -ge $MAX ]; then
    echo "[EJC] ❌ PostgreSQL não respondeu após ${MAX} tentativas. Abortando."
    exit 1
  fi
  echo "[EJC] PostgreSQL não disponível — aguardando 2s... ($N/$MAX)"
  sleep 2
done
echo "[EJC] ✅ PostgreSQL disponível"

echo "[EJC] Aplicando migrations Alembic..."
python -m alembic upgrade head
echo "[EJC] ✅ Migrations aplicadas"

echo "[EJC] Executando seed inicial (admin + feriados + súmulas)..."
python seeds/seed_all.py
echo "[EJC] ✅ Seed concluído"

echo "[EJC] Iniciando uvicorn..."
exec "$@"
