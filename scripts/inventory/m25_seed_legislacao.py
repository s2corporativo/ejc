"""M25 — Ingestão de CPC + CF88 (idempotente) para enriquecer a verificação de citações."""
from __future__ import annotations
import asyncio
import sys

sys.path.insert(0, "/home/ubuntu/ejc_repo/backend")

from scripts.seed_legislacao import executar_seed_legislacao  # noqa: E402
from app.core.database import AsyncSessionLocal


async def main():
    async with AsyncSessionLocal() as db:
        rel = await executar_seed_legislacao(db, apenas="cpc,cf88", embutir_vetores=False)
    print("sucessos:", rel.get("sucessos") and len(rel["sucessos"]))
    print("falhas:", rel.get("falhas"))


if __name__ == "__main__":
    asyncio.run(main())
