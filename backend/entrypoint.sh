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

# Se um comando explícito foi passado ao container (ex.: `celery -A ... worker`
# no serviço `worker` do compose), executa-o diretamente — SEM rodar migrations
# nem seed. Isso é intencional: migrations/seed são responsabilidade exclusiva
# do container da API (sem comando), evitando dois processos disputando o schema
# a cada boot. Sem este `exec "$@"`, o worker subia outro uvicorn e nenhum job
# Celery era processado (o container ainda ficava "healthy" pelo healthcheck HTTP).
if [ "$#" -gt 0 ]; then
    echo "[entrypoint] Comando explícito recebido — executando sem migrations/seed: $*"
    exec "$@"
fi

# Migrations no boot são OPT-IN: só rodam com RUN_MIGRATIONS=1|true (default:
# NÃO rodar). Antes rodavam em TODO boot, o que tornava placebo a trava
# RUN_MIGRATIONS do deploy seguro (scripts/deploy_vps_safe.sh): o deploy podia
# "decidir" não migrar, mas o próprio boot já aplicava `alembic upgrade head`
# sem backup prévio. Agora o deploy controla explicitamente e garante o backup
# antes. Dev local (docker-compose) seta RUN_MIGRATIONS=1 e segue funcionando.
# CI NÃO usa este entrypoint: o job db-validation roda `alembic upgrade head`
# num step próprio.
case "${RUN_MIGRATIONS:-}" in
    1|true|TRUE|True|yes|YES)
        echo "[entrypoint] RUN_MIGRATIONS ativo — aplicando migrations (alembic upgrade head)..."
        python -m alembic upgrade head
        ;;
    *)
        echo "[entrypoint] RUN_MIGRATIONS não setado (=${RUN_MIGRATIONS:-<vazio>}) — pulando migrations no boot."
        echo "[entrypoint] Em produção o deploy aplica as migrations de forma gated, com backup antes."
        ;;
esac

echo "[entrypoint] Semeando usuário admin (idempotente)..."
python seeds/seed_all.py

echo "[entrypoint] Semeando sócios advogados do escritório (idempotente)..."
python seeds/seed_socios_advogados.py

echo "[entrypoint] Iniciando uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
