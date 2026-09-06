FROM rclone/rclone:1.75.0 AS rclone_runtime

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Libs de SISTEMA exigidas em runtime (a falta delas derruba o boot ou
# quebra features em produção):
#   libmagic1        → python-magic (documents.py importa no module load;
#                      sem ela o uvicorn nem sobe — ImportError no boot)
#   tesseract-ocr(+por) → pytesseract (OCR em português)
#   libpango*/gdk-pixbuf/fonts → weasyprint (PDFs: anexos, dossiês, relatórios)
#   antiword         → ocr_service._doc_legado (.doc binário; sem ele o texto
#                      não é extraído e o documento não entra no RAG)
#   postgresql-client → fornece o binário `pg_dump` que o backup agendado
#                      in-container (scheduler.py, job 02h00) invoca. `libpq-dev`
#                      traz só headers/libpq, NÃO o cliente — sem isto o backup
#                      era no-op (pg_dump: command not found).
#
# rclone NÃO vem mais do apt do Debian: a versão disponível no runtime de
# produção ficou defasada e deixou de autenticar no remote OneDrive, embora a
# mesma configuração funcionasse com rclone atual. O binário Go é copiado da
# imagem oficial e fixado em versão para build reproduzível.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential curl libpq-dev postgresql-client \
       libmagic1 \
       tesseract-ocr tesseract-ocr-por \
       libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
       shared-mime-info fonts-dejavu-core \
       antiword \
    && rm -rf /var/lib/apt/lists/*

COPY --from=rclone_runtime /usr/local/bin/rclone /usr/local/bin/rclone
RUN rclone version | grep -q '^rclone v1\.75\.0$'

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY seeds ./seeds
# scripts/ precisa entrar na imagem: o deploy roda `python scripts/seed_biblia_ejc.py`
# (seed idempotente do corpus RAG da Bíblia). Sem esta linha o container não tem o
# script (/app/scripts/...) e o seed falha com "No such file or directory".
COPY scripts ./scripts
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

RUN mkdir -p /app/uploads /app/backups

EXPOSE 8000

# O entrypoint aplica migrations (alembic upgrade head) + seed idempotente do
# admin e então sobe o uvicorn — o container antigo subia com o banco vazio.
#
# DÍVIDA DE SEGURANÇA ACEITA E RASTREADA (semgrep missing-user-entrypoint):
# este container roda como root. Não é falso positivo — é endurecimento real
# que falta. Não foi feito aqui porque `USER` sem mais nada QUEBRA produção:
# /app/uploads e /app/backups são volumes NOMEADOS (uploads_data,
# backups_data no docker-compose.yml) que já existem no VPS pertencendo ao
# root. O Docker só copia dono/permissão da imagem quando o volume nasce
# vazio — nos volumes já populados de produção ele não faz nada, e um usuário
# não-root perderia a escrita: upload de documento e o backup agendado das
# 02h00 (scheduler.py) parariam no primeiro deploy.
# Fechar isso exige, num PR próprio e com build de container exercitado:
#   1) `useradd` + `chown -R` de /app/uploads e /app/backups na imagem;
#   2) `chown` único dos volumes existentes no VPS, no runbook de deploy;
#   3) conferir que pg_dump/rclone do job de backup ainda escrevem.
# nosemgrep: dockerfile.security.missing-user-entrypoint.missing-user-entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]