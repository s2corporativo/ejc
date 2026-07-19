#!/usr/bin/env bash
# ── EJC — Popular a base de conhecimento (turnkey, pós-deploy) ────────────────
#
# Roda DENTRO do container backend, na VPS (precisa de rede para o Planalto e,
# na primeira vez, para baixar o modelo de embeddings do HuggingFace):
#
#   docker exec -it ejc_backend bash scripts/popular_base_conhecimento.sh
#
# Etapas (todas idempotentes — pode rodar de novo sem duplicar nada):
#   1. Bíblia EJC       — 398 docs didáticos (situações, modelos, governança)
#   2. Legislação       — 14 leis compiladas do Planalto, chunk por artigo
#   3. Súmulas curadas  — 27 verbetes STF/STJ/TST conferidos contra fonte oficial
#   4. Re-embed         — vetoriza chunks órfãos (busca semântica completa)
#
# Falha de uma etapa NÃO aborta as demais; o resumo final lista o que falhou e
# o script sai com código != 0 se algo falhou (o operador decide re-rodar).
set -uo pipefail

FALHAS=()

etapa() {  # etapa "nome" comando...
    local nome="$1"; shift
    echo ""
    echo "══════════════════════════════════════════════════════════"
    echo "▶ ${nome}"
    echo "══════════════════════════════════════════════════════════"
    if "$@"; then
        echo "✔ ${nome}: OK"
    else
        echo "✘ ${nome}: FALHOU (código $?)"
        FALHAS+=("${nome}")
    fi
}

etapa "1/4 Bíblia EJC (seed_biblia_ejc)" \
    python scripts/seed_biblia_ejc.py

etapa "2/4 Legislação do Planalto (seed_legislacao)" \
    python -m scripts.seed_legislacao

etapa "3/4 Súmulas curadas (ingerir_sumulas_seed)" \
    python -c "
import asyncio
from app.core.database import AsyncSessionLocal
from app.services.sumulas_ingestion import ingerir_sumulas_seed

async def main():
    async with AsyncSessionLocal() as db:
        r = await ingerir_sumulas_seed(db)
        print('Resultado:', r)

asyncio.run(main())
"

etapa "4/4 Re-embed dos chunks órfãos (busca semântica)" \
    python -m scripts.reembedar_chunks_orfaos --batch-size 20

echo ""
echo "══════════════════════════════════════════════════════════"
if [ ${#FALHAS[@]} -eq 0 ]; then
    echo "✅ Base de conhecimento populada com sucesso (4/4 etapas)."
    echo "   Smoke sugerido: uma busca em /api/rag/buscar e uma citação de"
    echo "   artigo/súmula numa peça (o gate deve marcar 'verificada')."
    exit 0
else
    echo "⚠️  Etapas com falha: ${FALHAS[*]}"
    echo "   Re-rode este script após corrigir (todas as etapas são idempotentes)."
    exit 1
fi
