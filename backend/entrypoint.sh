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
    # O worker não precisa conhecer a credencial bootstrap do PostgreSQL nem a
    # credencial DDL. Mantém apenas DATABASE_URL/APP_DATABASE_URL de runtime.
    unset POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB MIGRATION_DATABASE_URL
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

echo "[entrypoint] Iniciando uvicorn..."
# Após migrations/seeds, a API não precisa conhecer credenciais bootstrap/DDL.
# Remover do ambiente do PID 1 reduz o impacto de eventual comprometimento do app.
unset POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB MIGRATION_DATABASE_URL
# ATENÇÃO (item 11 — auditoria pré-produção): NÃO adicionar --workers N sem
# antes migrar TODOS os contadores de segurança para armazenamento compartilhado:
#   • anti-brute-force do login (services/security_service.py: dict em memória)
#   • slowapi @limiter.limit (core/rate_limit.py: storage em memória)
# Ambos são POR PROCESSO: com N workers, o atacante ganha N× o limite (cada
# worker conta suas próprias falhas). RATE_LIMIT_REDIS_ENABLED cobre apenas a
# dependency consumir()/rate_limit() — não cobre os dois itens acima.
#
# --forwarded-allow-ips (Onda 1 da refatoração): `--proxy-headers` sozinho NÃO
# bastava. O default do uvicorn é confiar só em 127.0.0.1, mas o Nginx roda no
# HOST e chega aqui pela porta publicada — o Docker reescreve a origem para o
# gateway da bridge (172.x.0.1), NUNCA 127.0.0.1. Resultado: o
# `X-Forwarded-Proto: https` que o Nginx envia era DESCARTADO, o app enxergava
# esquema `http` e todo redirect absoluto que o Starlette gera saía como
# `Location: http://...`. Numa página https o browser bloqueia o downgrade e a
# chamada morre em "Failed to fetch" — o sintoma que a auditoria reproduziu na
# Sala Jurídica com barra final (`/api/sala-juridica/` → 307 → bloqueado;
# `/api/sala-juridica` → 200), e que valia para QUALQUER rota cuja barra final
# divergisse da declarada (163 routers, uns com "", outros com "/").
#
# FRONTEIRA DE CONFIANÇA com `*` — o que ela realmente é: todo mundo que abre
# TCP para este processo. Isso são (a) o Nginx do host, pela porta publicada só
# no loopback (docker-compose.yml), (b) os demais containers das redes `default`
# e `ia` — worker, frontend (que faz proxy_pass para backend:8000), e os perfis
# opt-in — e (c) qualquer processo local do VPS. NÃO é "só o Nginx".
#
# O risco residual é aceito porque nada que decide segurança no EJC lê
# `request.client`: rate limit, anti-brute-force do login e trilha de auditoria
# passam todos por `parse_client_ip` (app/core/request_context.py), que lê o
# header cru e pega o ÚLTIMO salto — a parte que o Nginx anexa, não a que o
# cliente controla. O que fica exposto a forja é o access log do uvicorn.
#
# Para apertar, use FORWARDED_ALLOW_IPS no .env — mas note que esta versão do
# uvicorn compara IP por STRING EXATA, sem CIDR (ver o aviso no .env.example).
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}"
