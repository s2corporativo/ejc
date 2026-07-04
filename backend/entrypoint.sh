#!/bin/sh
# entrypoint.sh — inicialização do backend EJC no container.
#
# Antes de subir o servidor, garante o schema e o usuário admin:
#   1) alembic upgrade head  → cria/atualiza TODAS as tabelas (idempotente).
#   2) seeds/seed_all.py      → cria o admin inicial se ainda não existir
#                               (idempotente; lê ADMIN_EMAIL/ADMIN_PASSWORD).
# Só então executa o uvicorn. Sem este passo o container subia com o banco
# vazio (nenhuma tabela) e toda requisição falhava.
set -e

# Garante que o pacote `app` seja importável a partir do WORKDIR, tanto pelo
# alembic quanto pelo seed (rodar `python seeds/seed_all.py` sem isto coloca só
# o dir do script no path — não o WORKDIR — e o `import app` falha).
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"

echo "[entrypoint] Aplicando migrations (alembic upgrade head)..."
python -m alembic upgrade head

echo "[entrypoint] Semeando usuário admin (idempotente)..."
python seeds/seed_all.py

echo "[entrypoint] Iniciando uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
