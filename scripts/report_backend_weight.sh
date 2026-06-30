#!/usr/bin/env bash
set -euo pipefail

echo "== Imagens EJC =="
docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}' | grep -E 'ejc|REPOSITORY' || true

echo
echo "== Uso de disco Docker =="
docker system df

echo
echo "== Maiores diretorios no backend =="
docker exec ejc_backend sh -lc "du -h -d 1 /usr/local/lib/python3.11/site-packages /app 2>/dev/null | sort -h | tail -30"

cat <<'TXT'

Sugestao tecnica:
- separar dependencias ML/RAG em imagem ou worker proprio quando o deploy frequente nao alterar IA;
- manter backend juridico/API menor para rebuilds rapidos;
- usar cache de build e constraints de dependencias para evitar reinstalacao completa.
TXT
