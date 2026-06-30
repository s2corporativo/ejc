# EJC Backend - multi-stage, non-root
FROM python:3.11-slim AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 gcc libpq-dev \
    tesseract-ocr tesseract-ocr-por \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libcairo2 \
    libgdk-pixbuf-2.0-0 libffi8 shared-mime-info fonts-dejavu-core \
    libmagic1 \
    rclone \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt \
    && apt-get purge -y gcc libpq-dev \
    && apt-get autoremove -y

COPY . .

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN useradd -m -u 1000 ejc \
    && mkdir -p /app/uploads /opt/hf-cache \
    && chown -R ejc:ejc /app /opt/hf-cache \
    && chown root:root /entrypoint.sh
USER ejc

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

# Optional local semantic RAG image. Production default uses runtime-base.
FROM runtime-base AS ml
USER root
RUN pip install torch==2.3.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements-ml.txt \
    && mkdir -p /opt/hf-cache \
    && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base')" \
    && chown -R ejc:ejc /opt/hf-cache
USER ejc
