"""scripts/seed_conhecimento.py — seed idempotente da Base de Conhecimento.

Popula o RAG com o conhecimento inicial do escritório (README de uso,
checklist de curadoria, padrão-ouro de peças, diretrizes por área e modelos
de estrutura de documento). Rodar várias vezes é seguro: dedup por
chave_origem (ejc_seed:*); conteúdo alterado gera nova versão (histórico
preservado).

Equivalente ao endpoint POST /api/rag/seed (role sócio+). Jurisprudência real
NÃO entra por aqui — use o importador oficial (página Conhecimento →
Importar Jurisprudência, fontes LexML/STJ) ou o próprio endpoint com
?incluir_jurisprudencia=true.

Uso (dentro do container, WORKDIR /app):  python scripts/seed_conhecimento.py
  --sem-vetores    adia a vetorização (docs ficam "pendente"; a busca textual
                   já os encontra; vetorize depois com scripts/vetorizar_documentos.py)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# backend/ no sys.path quando rodado como script avulso.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main(embutir_vetores: bool) -> None:
    from app.core.database import AsyncSessionLocal
    from app.services.seed_conhecimento import executar_seed_conhecimento

    async with AsyncSessionLocal() as db:
        resumo = await executar_seed_conhecimento(db, embutir_vetores=embutir_vetores)
        await db.commit()
    print(
        f"[seed-conhecimento] total={resumo['total']} novos={resumo['novos']} "
        f"atualizados={resumo['atualizados']} inalterados={resumo['inalterados']}"
    )
    for d in resumo["documentos"]:
        print(f"  - {d['chave_origem']}: {d['resultado']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed da Base de Conhecimento (idempotente)")
    parser.add_argument(
        "--sem-vetores", action="store_true",
        help="não gera embeddings agora (docs ficam pendentes de vetorização)",
    )
    args = parser.parse_args()
    asyncio.run(main(embutir_vetores=not args.sem_vetores))
