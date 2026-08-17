"""M25 — Limpeza idempotente de resíduos de dados sintéticos QA da bateria M25.

Escopo estrito: legal_docs com título 'EJC_QA_M25 peça teste'.
Motivo: o INSERT sintético da seção de correspondência falhou no commit em
runs anteriores com erro de enum/coluna, deixando órfãos ativos que devem
ser removidos (soft delete).
"""
from __future__ import annotations
import asyncio
import sys

sys.path.insert(0, "/home/ubuntu/ejc_repo/backend")

from app.core.database import AsyncSessionLocal
from sqlalchemy import text

TITULO = "EJC_QA_M25 peça teste"


async def main():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text(
            "UPDATE legal_docs SET deleted_at = now() "
            "WHERE titulo = :t AND deleted_at IS NULL"), {"t": TITULO})
        await db.commit()
        print(f"soft-deleted: {r.rowcount}")

asyncio.run(main())
