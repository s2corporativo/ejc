FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Libs de SISTEMA exigidas em runtime (a falta delas derruba o boot ou
# quebra features em produção):
#   libmagic1        → python-magic (documents.py importa no module load;
#                      sem ela o uvicorn nem sobe — ImportError no boot)
#   poppler-utils    → pdf2image (OCR de PDF escaneado)
#   tesseract-ocr(+por) → pytesseract (OCR em português)
#   libpango*/gdk-pixbuf/fonts → weasyprint (PDFs: anexos, dossiês, relatórios)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential curl libpq-dev \
       libmagic1 \
       poppler-utils \
       tesseract-ocr tesseract-ocr-por \
       libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
       shared-mime-info fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY seeds ./seeds
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

RUN mkdir -p /app/uploads /app/backups

EXPOSE 8000

# O entrypoint aplica migrations (alembic upgrade head) + seed idempotente do
# admin e então sobe o uvicorn — o container antigo subia com o banco vazio.
ENTRYPOINT ["/app/entrypoint.sh"]
